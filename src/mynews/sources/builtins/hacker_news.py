"""Hacker News 官方 API 来源插件。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlsplit

from mynews.domain.models import Candidate
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceContext,
    SourceHealth,
    SourceMetadata,
    SourcePluginError,
)

HN_SOURCE_ID = "hacker-news"
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_TOP_STORIES_URL = f"{HN_API_BASE}/topstories.json"
HN_ITEM_URL = f"{HN_API_BASE}/item/{{item_id}}.json"


class HackerNewsPlugin:
    metadata = SourceMetadata(
        source_id=HN_SOURCE_ID,
        name="Hacker News",
        role="discovery",
        homepage="https://news.ycombinator.com/",
        official_domains=("hacker-news.firebaseio.com", "news.ycombinator.com"),
        capabilities=("api",),
    )

    def collect(self, context: SourceContext) -> SourceBatch:
        story_ids = _story_ids(context.http.get_json(HN_TOP_STORIES_URL))
        candidates: list[Candidate] = []
        fetched_count = 0
        for story_id in story_ids[: context.limit]:
            raw_item = context.http.get_json(HN_ITEM_URL.format(item_id=story_id))
            if raw_item is None:
                continue
            fetched_count += 1
            candidate = _candidate_from_item(raw_item, story_id)
            if _in_requested_range(candidate, context):
                candidates.append(candidate)
        return SourceBatch(HN_SOURCE_ID, tuple(candidates), fetched_count=fetched_count)

    def probe(self, context: ProbeContext) -> SourceHealth:
        story_ids = _story_ids(context.http.get_json(HN_TOP_STORIES_URL))
        count = min(len(story_ids), context.limit)
        return SourceHealth.healthy_result(
            source_id=HN_SOURCE_ID,
            role=self.metadata.role,
            fetched_count=count,
            accepted_count=count,
        )


def _story_ids(payload: object) -> list[int]:
    if not isinstance(payload, list) or not all(
        isinstance(item, int) for item in payload
    ):
        raise SourcePluginError(
            "invalid_payload", "Hacker News top stories 不是整数数组"
        )
    return payload


def _candidate_from_item(payload: object, story_id: int) -> Candidate:
    if not isinstance(payload, Mapping):
        raise SourcePluginError("invalid_payload", "Hacker News story 不是对象")
    item = cast(Mapping[str, object], payload)
    title = item.get("title")
    timestamp = item.get("time")
    if not isinstance(title, str) or not title.strip():
        raise SourcePluginError("invalid_payload", "Hacker News story 缺少标题")
    if not isinstance(timestamp, int):
        raise SourcePluginError("invalid_payload", "Hacker News story 缺少发布时间")
    published_at = datetime.fromtimestamp(timestamp, tz=UTC)
    raw_url = item.get("url")
    url = (
        raw_url
        if isinstance(raw_url, str) and _is_http_url(raw_url)
        else _item_url(story_id)
    )
    excerpt = item.get("text")
    return Candidate.model_validate(
        {
            "source_id": HN_SOURCE_ID,
            "title_original": title.strip(),
            "url": url,
            "published_at": published_at,
            "excerpt": (
                excerpt.strip()
                if isinstance(excerpt, str) and excerpt.strip()
                else None
            ),
            "heat_signals": {
                key: float(value)
                for key in ("score", "descendants")
                if isinstance(value := item.get(key), int)
            },
        }
    )


def _item_url(story_id: int) -> str:
    return f"https://news.ycombinator.com/item?id={story_id}"


def _is_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _in_requested_range(candidate: Candidate, context: SourceContext) -> bool:
    published_at = candidate.published_at
    return (
        published_at is not None
        and context.request.from_ <= published_at < context.request.to
    )
