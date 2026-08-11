"""可复用的 RSS/Atom SourcePlugin 辅助接口。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from mynews.domain.models import Candidate
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceContext,
    SourceHealth,
    SourceMetadata,
    SourcePluginError,
)


class RssFeedPlugin:
    """同时接受 RSS 2.0 和 Atom 的通用 Feed Adapter。"""

    def __init__(
        self,
        metadata: SourceMetadata,
        feed_url: str,
        *,
        allow_empty: bool = True,
    ) -> None:
        self.metadata = metadata
        self.feed_url = feed_url
        self.allow_empty = allow_empty

    def collect(self, context: SourceContext) -> SourceBatch:
        entries = self._entries(context.http.get_text(self.feed_url))
        candidates = [
            candidate
            for candidate in (
                _candidate_from_entry(entry, self.metadata, self.feed_url)
                for entry in entries[: context.limit]
            )
            if _in_requested_range(candidate, context)
        ]
        return SourceBatch(
            self.metadata.source_id,
            tuple(candidates),
            fetched_count=min(len(entries), context.limit),
        )

    def probe(self, context: ProbeContext) -> SourceHealth:
        entries = self._entries(context.http.get_text(self.feed_url))
        selected = entries[: context.limit]
        for entry in selected:
            _candidate_from_entry(entry, self.metadata, self.feed_url)
        count = len(selected)
        return SourceHealth.healthy_result(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            fetched_count=count,
            accepted_count=count,
            checked_at=context.clock.now(),
        )

    def _entries(self, payload: str) -> list[ET.Element]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise SourcePluginError("invalid_feed", "官方 Feed 不是有效 XML") from error
        entries = [
            element
            for element in root.iter()
            if _local_name(element.tag) in {"item", "entry"}
        ]
        if (
            not entries
            and (
                not self.allow_empty
                or _local_name(root.tag) not in {"rss", "feed", "rdf"}
            )
        ):
            raise SourcePluginError("invalid_feed", "官方 Feed 没有 item 或 entry")
        return entries


def _candidate_from_entry(
    entry: ET.Element, metadata: SourceMetadata, feed_url: str
) -> Candidate:
    title = _child_text(entry, "title")
    raw_link = _entry_link(entry)
    if not title or not raw_link:
        raise SourcePluginError(
            "invalid_entry", f"{metadata.source_id} Feed 条目缺少官方标题或链接"
        )
    link = urljoin(feed_url, raw_link)
    if not _is_official_url(
        link,
        metadata.official_domains,
        metadata.official_github_organizations,
    ):
        raise SourcePluginError(
            "invalid_entry", f"{metadata.source_id} Feed 条目缺少官方标题或链接"
        )
    return Candidate.model_validate(
        {
            "source_id": metadata.source_id,
            "title_original": title,
            "url": link,
            "published_at": _entry_date(entry),
            "excerpt": _child_text(entry, "description")
            or _child_text(entry, "summary"),
            "heat_signals": {"official_feed": 1.0},
        }
    )


def _child_text(entry: ET.Element, name: str) -> str | None:
    for child in entry:
        if _local_name(child.tag) == name:
            text = " ".join("".join(child.itertext()).split())
            return text or None
    return None


def _entry_link(entry: ET.Element) -> str | None:
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return None


def _entry_date(entry: ET.Element) -> datetime | None:
    for name in ("pubDate", "published", "updated", "date"):
        value = _child_text(entry, name)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise SourcePluginError(
                    "invalid_entry", "Feed 条目日期无法解析"
                ) from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise SourcePluginError("invalid_entry", "Feed 条目日期缺少时区")
        return parsed
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_official_url(
    url: str,
    domains: Iterable[str],
    github_organizations: Iterable[str] = (),
) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    allowed_domains = tuple(domains)
    if not any(
        host == domain or host.endswith(f".{domain}")
        for domain in allowed_domains
    ):
        return False
    organizations = {value.casefold() for value in github_organizations}
    if organizations:
        if host != "github.com":
            return False
        organization = parsed.path.strip("/").split("/", 1)[0]
        return organization.casefold() in organizations
    return True


def _in_requested_range(candidate: Candidate, context: SourceContext) -> bool:
    published_at = candidate.published_at
    return (
        published_at is None
        or context.request.from_ <= published_at < context.request.to
    )


__all__ = ["RssFeedPlugin"]
