"""受显式选择控制的 Python entry-point 来源插件加载。"""

from __future__ import annotations

import inspect
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from importlib.metadata import EntryPoint
from typing import Literal
from urllib.parse import urlparse

from mynews.sources.protocol import SourceMetadata, SourcePlugin

ENTRY_POINT_GROUP = "mynews.source_plugins"
PluginStatus = Literal["complete", "failed"]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class PluginIssue:
    """外部插件发现或加载失败的稳定结构。"""

    plugin_id: str
    code: str
    message: str
    source_id: str | None = None

    def as_payload(self) -> dict[str, str]:
        payload = {
            "plugin_id": self.plugin_id,
            "code": self.code,
            "message": self.message,
        }
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        return payload


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    """尚未执行工厂的 entry-point 元数据。"""

    plugin_id: str
    value: str

    def as_payload(self) -> dict[str, str]:
        return {"id": self.plugin_id, "value": self.value}


@dataclass(frozen=True, slots=True)
class LoadedExternalPlugin:
    """已通过协议校验的外部插件。"""

    plugin_id: str
    plugin: SourcePlugin

    def as_payload(self) -> dict[str, str]:
        return {
            "id": self.plugin_id,
            "source_id": self.plugin.metadata.source_id,
            "name": self.plugin.metadata.name,
        }


@dataclass(frozen=True, slots=True)
class PluginLoadReport:
    """显式加载的结果；失败时不应交给 SourceRegistry。"""

    loaded: tuple[LoadedExternalPlugin, ...] = ()
    issues: tuple[PluginIssue, ...] = ()

    @property
    def status(self) -> PluginStatus:
        return "complete" if not self.issues else "failed"

    @property
    def plugins(self) -> tuple[SourcePlugin, ...]:
        return tuple(item.plugin for item in self.loaded)

    def as_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "group": ENTRY_POINT_GROUP,
            "loaded": [item.as_payload() for item in self.loaded],
            "errors": [item.as_payload() for item in self.issues],
        }


class ExternalPluginLoader:
    """发现 entry-point，并只加载调用者明确选择的 ID。"""

    def __init__(self, entry_points: Iterable[EntryPoint] | None = None) -> None:
        self._entry_points = tuple(entry_points) if entry_points is not None else None

    def discover(self) -> tuple[EntryPoint, ...]:
        if self._entry_points is not None:
            return tuple(sorted(self._entry_points, key=_entry_point_key))
        points = importlib_metadata.entry_points(group=ENTRY_POINT_GROUP)
        return tuple(sorted(points, key=_entry_point_key))

    def list_report(self) -> dict[str, object]:
        try:
            points = self.discover()
        except Exception as error:
            issue = PluginIssue("*", "entry_point_discovery_failed", _error_text(error))
            return {
                "status": "failed",
                "group": ENTRY_POINT_GROUP,
                "loaded": False,
                "plugins": [],
                "errors": [issue.as_payload()],
            }
        issues = _duplicate_entry_point_issues(points)
        return {
            "status": "failed" if issues else "complete",
            "group": ENTRY_POINT_GROUP,
            "loaded": False,
            "plugins": [
                DiscoveredPlugin(point.name, point.value).as_payload()
                for point in points
            ],
            "errors": [issue.as_payload() for issue in issues],
        }

    def load(
        self,
        plugin_ids: Sequence[str],
        *,
        occupied_source_ids: Iterable[str] = (),
    ) -> PluginLoadReport:
        try:
            points = self.discover()
        except Exception as error:
            return PluginLoadReport(
                issues=(
                    PluginIssue(
                        "*", "entry_point_discovery_failed", _error_text(error)
                    ),
                )
            )
        issues = list(_duplicate_entry_point_issues(points))
        requested = tuple(plugin_ids)
        issues.extend(_duplicate_request_issues(requested))
        by_id = _unique_entry_points(points)
        loaded: list[LoadedExternalPlugin] = []
        builtin_source_ids = set(occupied_source_ids)
        occupied = set(builtin_source_ids)
        for plugin_id in requested:
            if _has_issue(issues, plugin_id, "duplicate_plugin_id"):
                continue
            point = by_id.get(plugin_id)
            if point is None:
                issues.append(
                    PluginIssue(plugin_id, "plugin_not_found", "未发现该外部插件")
                )
                continue
            if _has_issue(issues, plugin_id, "duplicate_entry_point_id"):
                continue
            result = _load_entry_point(plugin_id, point)
            if isinstance(result, PluginIssue):
                issues.append(result)
                continue
            source_id = result.plugin.metadata.source_id
            if source_id in builtin_source_ids:
                issues.append(
                    PluginIssue(
                        plugin_id,
                        "builtin_source_id_conflict",
                        f"外部来源 ID 与已注册来源冲突：{source_id}",
                        source_id,
                    )
                )
                continue
            if any(item.plugin.metadata.source_id == source_id for item in loaded):
                issues.append(
                    PluginIssue(
                        plugin_id,
                        "duplicate_source_id",
                        f"外部插件返回了重复来源 ID：{source_id}",
                        source_id,
                    )
                )
                continue
            occupied.add(source_id)
            loaded.append(result)
        return PluginLoadReport(tuple(loaded), tuple(issues))


def _entry_point_key(point: EntryPoint) -> tuple[str, str]:
    return (point.name, point.value)


def _duplicate_entry_point_issues(
    points: Sequence[EntryPoint],
) -> tuple[PluginIssue, ...]:
    counts = Counter(point.name for point in points)
    return tuple(
        PluginIssue(plugin_id, "duplicate_entry_point_id", "entry-point ID 重复")
        for plugin_id, count in sorted(counts.items())
        if count > 1
    )


def _duplicate_request_issues(plugin_ids: Sequence[str]) -> tuple[PluginIssue, ...]:
    counts = Counter(plugin_ids)
    return tuple(
        PluginIssue(plugin_id, "duplicate_plugin_id", "显式插件 ID 重复")
        for plugin_id, count in sorted(counts.items())
        if count > 1
    )


def _unique_entry_points(points: Sequence[EntryPoint]) -> dict[str, EntryPoint]:
    result: dict[str, EntryPoint] = {}
    for point in points:
        result.setdefault(point.name, point)
    return result


def _has_issue(issues: Sequence[PluginIssue], plugin_id: str, code: str) -> bool:
    return any(issue.plugin_id == plugin_id and issue.code == code for issue in issues)


def _load_entry_point(
    plugin_id: str, point: EntryPoint
) -> LoadedExternalPlugin | PluginIssue:
    try:
        factory = point.load()
    except Exception as error:
        return PluginIssue(plugin_id, "factory_import_failed", _error_text(error))
    if not callable(factory):
        return PluginIssue(
            plugin_id, "factory_not_callable", "entry-point 必须解析为工厂"
        )
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError) as error:
        return PluginIssue(plugin_id, "factory_signature_invalid", _error_text(error))
    if signature.parameters:
        return PluginIssue(
            plugin_id, "factory_must_be_no_argument", "插件工厂不能接受参数"
        )
    try:
        plugin = factory()
    except Exception as error:
        return PluginIssue(plugin_id, "factory_runtime_error", _error_text(error))
    issue = validate_external_plugin(plugin_id, plugin)
    if issue is not None:
        return issue
    return LoadedExternalPlugin(plugin_id, plugin)


def validate_external_plugin(plugin_id: str, plugin: object) -> PluginIssue | None:
    """严格验证外部对象；不执行 collect/probe。"""
    try:
        protocol_ok = isinstance(plugin, SourcePlugin)
        metadata = getattr(plugin, "metadata", None)
    except Exception as error:
        return PluginIssue(plugin_id, "invalid_plugin_protocol", _error_text(error))
    if not protocol_ok:
        return PluginIssue(
            plugin_id, "invalid_plugin_protocol", "工厂未返回 SourcePlugin 1.0 对象"
        )
    if not isinstance(metadata, SourceMetadata):
        return PluginIssue(
            plugin_id, "invalid_source_metadata", "metadata 必须是 SourceMetadata"
        )
    issue = _validate_metadata(plugin_id, metadata)
    if issue is not None:
        return issue
    if not callable(getattr(plugin, "collect", None)) or not callable(
        getattr(plugin, "probe", None)
    ):
        return PluginIssue(
            plugin_id,
            "invalid_plugin_protocol",
            "SourcePlugin 必须提供 collect 和 probe",
        )
    return None


def _validate_metadata(plugin_id: str, metadata: SourceMetadata) -> PluginIssue | None:
    if not _valid_identifier(metadata.source_id):
        return PluginIssue(
            plugin_id,
            "invalid_source_id",
            "source_id 必须是无空白的非空标识符",
            _safe_source_id(metadata),
        )
    if metadata.plugin_api_version != "1.0":
        return PluginIssue(
            plugin_id,
            "protocol_incompatible",
            f"不支持的来源插件协议版本：{metadata.plugin_api_version}",
            metadata.source_id,
        )
    if not isinstance(metadata.role, str) or metadata.role not in {
        "primary",
        "monitor",
        "discovery",
        "research",
        "incident",
        "benchmark",
    }:
        return PluginIssue(
            plugin_id,
            "invalid_role",
            f"不支持的来源角色：{metadata.role}",
            metadata.source_id,
        )
    if not _valid_label(metadata.name) or not _valid_https_url(metadata.homepage):
        return PluginIssue(
            plugin_id,
            "invalid_source_metadata",
            "SourceMetadata 的 name/homepage 无效",
            metadata.source_id,
        )
    if not _valid_domains(metadata.official_domains):
        return PluginIssue(
            plugin_id,
            "invalid_official_domains",
            "official_domains 必须是精确的小写域名数组",
            metadata.source_id,
        )
    if not _valid_capabilities(metadata.capabilities):
        return PluginIssue(
            plugin_id,
            "empty_capabilities",
            "capabilities 必须是非空且唯一的能力数组",
            metadata.source_id,
        )
    if not _valid_string_tuple(metadata.official_github_organizations):
        return PluginIssue(
            plugin_id,
            "invalid_source_metadata",
            "官方 GitHub 组织列表无效",
            metadata.source_id,
        )
    for field_name in ("region", "stability", "publication_time_semantics"):
        if not _valid_text(getattr(metadata, field_name)):
            return PluginIssue(
                plugin_id,
                "invalid_source_metadata",
                f"SourceMetadata.{field_name} 无效",
                metadata.source_id,
            )
    return None


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def _valid_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(char.isspace() for char in value)
    )


def _valid_label(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _valid_domains(values: object) -> bool:
    if not isinstance(values, tuple) or not values:
        return False
    if not all(
        isinstance(value, str)
        and value == value.lower()
        and bool(_DOMAIN.fullmatch(value))
        and ".." not in value
        for value in values
    ):
        return False
    return len(values) == len(set(values))


def _valid_capabilities(values: object) -> bool:
    if not isinstance(values, tuple) or not values:
        return False
    if not all(_valid_text(value) for value in values):
        return False
    return len(values) == len(set(values))


def _valid_string_tuple(values: object) -> bool:
    return isinstance(values, tuple) and all(_valid_text(value) for value in values)


def _valid_https_url(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username


def _safe_source_id(metadata: SourceMetadata) -> str | None:
    return metadata.source_id if isinstance(metadata.source_id, str) else None


def _error_text(error: Exception) -> str:
    return str(error) or error.__class__.__name__
