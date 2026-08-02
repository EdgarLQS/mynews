"""基于稳定事件键的批内和跨运行去重。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pydantic import Field, field_validator

from mynews.domain.models import ContractModel, NewsItem


class DedupRecord(ContractModel):
    """一个已观察事件的最小可恢复状态。"""

    first_seen_at: datetime
    last_seen_at: datetime

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("去重状态时间必须包含时区")
        return value


class DedupState(ContractModel):
    """可写入 state/dedup.json 的跨运行去重状态。"""

    schema_version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+$")
    events: dict[str, DedupRecord] = Field(default_factory=dict)


class Deduplicator:
    """只依赖 NewsItem 公共字段的去重器。"""

    def __init__(self, state: DedupState | None = None) -> None:
        self._state = (state or DedupState()).model_copy(deep=True)

    @property
    def state(self) -> DedupState:
        return self._state

    def deduplicate(
        self, items: Iterable[NewsItem]
    ) -> tuple[NewsItem, ...]:
        accepted: dict[str, NewsItem] = {}
        for item in items:
            if item.event_key in self._state.events:
                self._touch(item)
                continue
            previous = accepted.get(item.event_key)
            accepted[item.event_key] = (
                _merge_items(previous, item) if previous is not None else item
            )
        for event_key, item in accepted.items():
            self._state.events[event_key] = DedupRecord(
                first_seen_at=item.first_seen_at,
                last_seen_at=item.first_seen_at,
            )
        return tuple(accepted.values())

    def _touch(self, item: NewsItem) -> None:
        record = self._state.events[item.event_key]
        if item.first_seen_at > record.last_seen_at:
            record.last_seen_at = item.first_seen_at


def _merge_items(first: NewsItem, second: NewsItem) -> NewsItem:
    first_seen_at = min(first.first_seen_at, second.first_seen_at)
    published_at = _earliest(first.published_at, second.published_at)
    return first.model_copy(
        update={
            "published_at": published_at,
            "first_seen_at": first_seen_at,
            "heat_score": max(first.heat_score, second.heat_score),
            "relevance_score": max(first.relevance_score, second.relevance_score),
            "discovery_sources": sorted(
                set(first.discovery_sources) | set(second.discovery_sources)
            ),
            "source_roles": sorted(set(first.source_roles) | set(second.source_roles)),
            "entities": sorted(set(first.entities) | set(second.entities)),
        }
    )


def _earliest(
    first: datetime | None, second: datetime | None
) -> datetime | None:
    if first is None:
        return second
    if second is None:
        return first
    return min(first, second)
