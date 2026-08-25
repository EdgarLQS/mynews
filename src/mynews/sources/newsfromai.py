"""newsFromAI datacollection 的 25 个自动来源配置适配。

这里仅保存来源配置和 SourcePlugin 组装逻辑；事实仍由 mynews 的
SourceCollection、RunReport 和 JSON Store 承载。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mynews.domain.models import SourceError
from mynews.infrastructure.http import HttpClient
from mynews.sources.feed import RssFeedPlugin
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceBlockedError,
    SourceContext,
    SourceHealth,
    SourceMetadata,
    SourcePlugin,
)
from mynews.sources.registry import SourceRegistry

_SOURCE_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "newsfromai-feeds.json"
)
_PACKAGED_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "newsfromai-feeds.json"
)
DEFAULT_CONFIG_PATH = (
    _SOURCE_CONFIG_PATH if _SOURCE_CONFIG_PATH.is_file() else _PACKAGED_CONFIG_PATH
)


@dataclass(slots=True)
class ManualSourcePlugin:
    metadata: SourceMetadata
    reason: str

    def collect(self, context: SourceContext) -> SourceBatch:
        del context
        raise SourceBlockedError("manual_source", self.reason)

    def probe(self, context: ProbeContext) -> SourceHealth:
        return SourceHealth(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            stability=self.metadata.stability,
            health="blocked",
            fetched_count=0,
            accepted_count=0,
            duration_ms=0,
            checked_at=context.clock.now(),
            error=SourceError(code="manual_source", message=self.reason),
        )


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("无法读取 newsFromAI Feed 配置") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("feeds"), list):
        raise ValueError("newsFromAI Feed 配置缺少 feeds")
    feeds = payload["feeds"]
    if (
        len(feeds) != 25
        or len({str(item.get("id")) for item in feeds if isinstance(item, dict)}) != 25
    ):
        raise ValueError("newsFromAI Feed 配置必须包含 25 个唯一来源")
    return payload


def newsfromai_registry(
    *,
    http: HttpClient | None = None,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> SourceRegistry:
    config = load_config(config_path)
    plugins = [
        _plugin_from_config(item) for item in config["feeds"] if isinstance(item, dict)
    ]
    return SourceRegistry(plugins, http=http)


def _plugin_from_config(feed: dict[str, object]) -> SourcePlugin:
    source_id = str(feed["id"])
    url = str(feed["url"])
    role = str(feed.get("source_role") or "primary")
    host = urlsplit(url).hostname or ""
    official_domains: tuple[str, ...] = (host,)
    if source_id == "anthropic-status":
        official_domains = (host, "status.claude.com")
    github_orgs: tuple[str, ...] = ()
    if host == "github.com":
        parts = urlsplit(url).path.strip("/").split("/")
        github_orgs = (parts[0],) if parts else ()
    metadata = SourceMetadata(
        source_id=source_id,
        name=str(feed["name"]),
        role=role,
        homepage=url,
        official_domains=official_domains,
        official_github_organizations=github_orgs,
        capabilities=("rss", "atom")
        if source_id != "paperswithcode-daily"
        else ("manual",),
        region="cn" if str(feed.get("lang")) == "zh" else "global",
        stability="experimental"
        if str(feed.get("tier")) == "temporary"
        else "stable-planned",
        publication_time_semantics="manual-check"
        if source_id == "paperswithcode-daily"
        else "feed-date",
        freshness_days=int(str(feed.get("max_age_days") or 2)),
    )
    if source_id == "paperswithcode-daily":
        return ManualSourcePlugin(
            metadata, "当前没有可确认的官方 RSS/Atom daily 入口，需人工检查官方页面"
        )
    return RssFeedPlugin(
        metadata,
        url,
        allow_empty=True,
        allow_external_links=role == "discovery",
    )


__all__ = ["DEFAULT_CONFIG_PATH", "load_config", "newsfromai_registry"]
