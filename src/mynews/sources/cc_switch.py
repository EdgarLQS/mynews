"""CC Switch 官方更新日志来源 Adapter。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, cast
from urllib.parse import urlsplit

from mynews.domain.models import Candidate

CC_SWITCH_SOURCE_ID = "cc-switch"
CC_SWITCH_CHANGELOG_BASE = "https://ccswitch.io/zh/changelog"
CC_SWITCH_RELEASES_API = (
    "https://api.github.com/repos/farion1231/cc-switch/releases"
)
RELEASE_TAG_PATTERN = re.compile(r"^v(\d+\.\d+\.\d+)$")


class JsonFetcher(Protocol):
    """可替换的 JSON 网络边界。"""

    def get_json(self, url: str, *, timeout: float) -> object: ...


class CcSwitchPayloadError(ValueError):
    """CC Switch 官方 Release 返回内容不符合契约。"""


class CcSwitchReleaseAdapter:
    """将官方 Release 的“新功能”条目转换为候选。"""

    source_id = CC_SWITCH_SOURCE_ID

    def collect(
        self,
        fetcher: JsonFetcher,
        *,
        timeout: float = 10.0,
        limit: int = 20,
    ) -> list[Candidate]:
        if limit <= 0:
            raise ValueError("limit 必须是正整数")
        payload = fetcher.get_json(CC_SWITCH_RELEASES_API, timeout=timeout)
        if not isinstance(payload, list):
            raise CcSwitchPayloadError("官方 Release 返回值不是数组")

        candidates: list[Candidate] = []
        for raw_release in payload[:limit]:
            if not isinstance(raw_release, Mapping):
                raise CcSwitchPayloadError("官方 Release 条目不是对象")
            release = cast(Mapping[str, object], raw_release)
            if not self._is_stable_release(release):
                continue
            candidates.extend(self._parse_release(release))
        return candidates

    @staticmethod
    def _is_stable_release(release: Mapping[str, object]) -> bool:
        for field in ("draft", "prerelease"):
            value = release.get(field)
            if not isinstance(value, bool):
                raise CcSwitchPayloadError(
                    f"官方 Release 缺少稳定 Release 标志：{field}"
                )
            if value:
                return False
        return True

    def _parse_release(self, release: Mapping[str, object]) -> list[Candidate]:
        tag = self._required_text(release, "tag_name")
        tag_match = RELEASE_TAG_PATTERN.fullmatch(tag)
        if tag_match is None:
            raise CcSwitchPayloadError(f"无法识别的 Release 版本：{tag}")
        version = tag_match.group(1)

        release_url = self._required_text(release, "html_url")
        self._require_official_release_url(release_url, tag)
        published_at = self._parse_published_at(release)
        body = self._required_text(release, "body")
        feature_sections = self._new_feature_sections(body)
        changelog_url = f"{CC_SWITCH_CHANGELOG_BASE}/{version}"
        return [
            Candidate.model_validate(
                {
                    "source_id": self.source_id,
                    "title_original": f"CC Switch v{version}：{title}",
                    "url": changelog_url,
                    "published_at": published_at,
                    "excerpt": excerpt,
                    "heat_signals": {"official_release": 1.0},
                }
            )
            for title, excerpt in feature_sections
        ]

    @staticmethod
    def _required_text(release: Mapping[str, object], field: str) -> str:
        value = release.get(field)
        if not isinstance(value, str) or not value.strip():
            raise CcSwitchPayloadError(f"官方 Release 缺少 {field}")
        return value.strip()

    @staticmethod
    def _require_official_release_url(url: str, tag: str) -> None:
        parsed = urlsplit(url)
        expected_path = f"/farion1231/cc-switch/releases/tag/{tag}"
        if (
            parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or parsed.path != expected_path
        ):
            raise CcSwitchPayloadError("官方 Release URL 未通过域名和仓库校验")

    @staticmethod
    def _parse_published_at(release: Mapping[str, object]) -> datetime | None:
        value = release.get("published_at")
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise CcSwitchPayloadError("官方 Release published_at 不是文本")
        try:
            published_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise CcSwitchPayloadError(
                "官方 Release published_at 不是 ISO 时间"
            ) from error
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            raise CcSwitchPayloadError("官方 Release published_at 缺少时区")
        return published_at

    @staticmethod
    def _new_feature_sections(body: str) -> list[tuple[str, str]]:
        in_new_features = False
        current_title: str | None = None
        current_lines: list[str] = []
        sections: list[tuple[str, str]] = []

        def flush() -> None:
            if current_title is None:
                return
            excerpt = " ".join(line.strip() for line in current_lines if line.strip())
            sections.append((current_title, excerpt[:1000]))

        for line in body.splitlines():
            if line.startswith("## "):
                flush()
                current_title = None
                current_lines = []
                in_new_features = line[3:].strip() == "新功能"
            elif in_new_features and line.startswith("### "):
                flush()
                current_title = line[4:].strip()
                current_lines = []
            elif in_new_features and current_title is not None:
                current_lines.append(line)
        flush()
        return [(title, excerpt or title) for title, excerpt in sections]
