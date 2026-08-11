"""可复用的 RSS/Atom SourcePlugin 辅助接口。

解析器只处理 Feed 返回的内容，不主动抓取文章页面；这保留了 mynews 的
robots、登录和第一方核验边界，同时吸收 newsFromAI 的清洗和元数据语义。
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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

MAX_TITLE = 500
MAX_SUMMARY = 2000
MAX_CONTENT = 6000


class RssFeedPlugin:
    """同时接受 RSS 2.0 和 Atom，并产生清洗后的 Candidate。"""

    def __init__(
        self,
        metadata: SourceMetadata,
        feed_url: str,
        *,
        allow_empty: bool = True,
        allow_external_links: bool = False,
    ) -> None:
        self.metadata = metadata
        self.feed_url = feed_url
        self.allow_empty = allow_empty
        self.allow_external_links = allow_external_links

    def collect(self, context: SourceContext) -> SourceBatch:
        entries = self._entries(context.http.get_text(self.feed_url))
        candidates = []
        for entry in entries[: context.limit]:
            candidate = _candidate_from_entry(
                entry,
                self.metadata,
                self.feed_url,
                allow_external_links=self.allow_external_links,
            )
            if _in_requested_range(candidate, context, self.metadata.freshness_days):
                candidates.append(candidate)
        return SourceBatch(
            self.metadata.source_id,
            tuple(candidates),
            fetched_count=min(len(entries), context.limit),
        )

    def probe(self, context: ProbeContext) -> SourceHealth:
        entries = self._entries(context.http.get_text(self.feed_url))
        selected = entries[: context.limit]
        for entry in selected:
            _candidate_from_entry(
                entry,
                self.metadata,
                self.feed_url,
                allow_external_links=self.allow_external_links,
            )
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
        if not entries and (
            not self.allow_empty or _local_name(root.tag) not in {"rss", "feed", "rdf"}
        ):
            raise SourcePluginError("invalid_feed", "官方 Feed 没有 item 或 entry")
        return entries


def _candidate_from_entry(
    entry: ET.Element,
    metadata: SourceMetadata,
    feed_url: str,
    *,
    allow_external_links: bool = False,
) -> Candidate:
    title = _limit(_clean_html(_child_text(entry, "title") or ""), MAX_TITLE)
    raw_link = _entry_link(entry)
    if not title or not raw_link:
        raise SourcePluginError(
            "invalid_entry", f"{metadata.source_id} Feed 条目缺少标题或链接"
        )
    link = urljoin(feed_url, raw_link)
    if not _is_http_url(link) or (
        not allow_external_links
        and not _is_official_url(
            link, metadata.official_domains, metadata.official_github_organizations
        )
    ):
        raise SourcePluginError(
            "invalid_entry", f"{metadata.source_id} Feed 条目缺少官方标题或链接"
        )
    summary = _limit(
        _clean_html(
            _clean_summary(_first_child_text(entry, ("description", "summary")))
        ),
        MAX_SUMMARY,
    )
    content = _extract_content(entry, summary)
    authors = _unique(_children_text(entry, ("author", "creator")), 20)
    tags = _unique(_children_text(entry, ("category", "tag")), 30)
    external_links = _external_links(entry, link)
    images = _images(entry)
    return Candidate.model_validate(
        {
            "source_id": metadata.source_id,
            "source_name": metadata.name,
            "title_original": title,
            "url": link,
            "published_at": _entry_date(entry),
            "excerpt": summary or None,
            "content": content,
            "authors": authors,
            "tags": tags,
            "external_links": external_links,
            "image_candidates": images,
            "language": "zh" if _has_cjk(f"{title} {summary}") else "en",
            "source_role": metadata.role,
            "heat_signals": {"official_feed": 1.0},
            "extraction_status": "complete" if content or summary else "partial",
        }
    )


def _extract_content(entry: ET.Element, summary: str) -> str | None:
    values = _children_text(entry, ("encoded", "content", "content:encoded"))
    content = _limit(_clean_html(" ".join(values)), MAX_CONTENT)
    if not content or content.casefold() == summary.casefold():
        return None
    return content if len(content) > max(40, len(summary) * 1.2) else None


def _external_links(entry: ET.Element, main_url: str) -> list[str]:
    result: list[str] = []
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        rel = child.attrib.get("rel", "").casefold()
        href = child.attrib.get("href") or (child.text or "")
        if rel in {"self", "hub", "alternate"} or not _is_http_url(href):
            continue
        if href != main_url and href not in result:
            result.append(href)
    return result[:5]


def _images(entry: ET.Element) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for child in entry.iter():
        local = _local_name(child.tag)
        url = child.attrib.get("url") or child.attrib.get("href") or ""
        mime = child.attrib.get("type", "")
        if (
            local in {"content", "thumbnail", "enclosure"}
            and url
            and (mime.startswith("image/") or local == "thumbnail")
        ):
            value = {"url": url, "type": mime or "image/unknown"}
            if value not in result:
                result.append(value)
    return result[:3]


def _child_text(entry: ET.Element, name: str) -> str | None:
    for child in entry:
        if _local_name(child.tag) == name or child.tag == name:
            return "".join(child.itertext()).strip() or None
    return None


def _first_child_text(entry: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        value = _child_text(entry, name)
        if value:
            return value
    return ""


def _children_text(entry: ET.Element, names: tuple[str, ...]) -> list[str]:
    wanted = set(names)
    return [
        "".join(child.itertext()).strip()
        for child in entry.iter()
        if (_local_name(child.tag) in wanted or child.tag in wanted)
        and "".join(child.itertext()).strip()
    ]


def _entry_link(entry: ET.Element) -> str | None:
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
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


def _clean_html(value: str) -> str:
    parser = _TextParser()
    try:
        parser.feed(html.unescape(value))
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return " ".join(text.split())


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _clean_summary(value: str) -> str:
    cleaned = re.sub(r"(?:Article|Comments?)\s*URL:\s*\S+", "", value, flags=re.I)
    cleaned = re.sub(r"(?:Points?|Comments?):\s*\d+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"https?://\S+", "", cleaned, flags=re.I)
    return " ".join(cleaned.split())


def _limit(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    clipped = value[:limit].rstrip()
    boundary = max(clipped.rfind("。"), clipped.rfind(". "), clipped.rfind(" "))
    if boundary >= int(limit * 0.7):
        clipped = clipped[:boundary].rstrip()
    return f"{clipped}..."


def _unique(values: Iterable[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = _clean_html(value)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:limit]


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_http_url(url: str) -> bool:
    parsed = urlsplit(url.strip())
    return parsed.scheme == "https" and bool(parsed.hostname)


def _is_official_url(
    url: str, domains: Iterable[str], github_organizations: Iterable[str] = ()
) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if not any(host == domain or host.endswith(f".{domain}") for domain in domains):
        return False
    organizations = {value.casefold() for value in github_organizations}
    if organizations:
        organization = parsed.path.strip("/").split("/", 1)[0]
        return host == "github.com" and organization.casefold() in organizations
    return True


def _in_requested_range(
    candidate: Candidate, context: SourceContext, freshness_days: int = 2
) -> bool:
    published_at = candidate.published_at
    if published_at is None:
        return True
    start = context.request.from_
    if context.request.freshness_filter:
        start = max(start, context.request.to - timedelta(days=freshness_days))
    return start <= published_at < context.request.to


__all__ = ["MAX_CONTENT", "MAX_SUMMARY", "MAX_TITLE", "RssFeedPlugin"]
