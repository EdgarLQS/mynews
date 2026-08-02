"""阶段 2 原始来源采集应用层。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from mynews.domain.deduplication import Deduplicator, DedupState
from mynews.domain.models import (
    CollectionRequest,
    NewsItem,
    RunReport,
    SourceResult,
)
from mynews.domain.normalization import Normalizer, normalize_source_role
from mynews.infrastructure.clock import Clock, SystemClock
from mynews.sources.protocol import (
    ProbeContext,
    SourceCollection,
    SourceContext,
    SourceHealth,
)
from mynews.sources.registry import SourceRegistry
from mynews.storage.protocol import NewsStore


class SourceCollector:
    """在 CLI 与 SourceRegistry 之间隐藏阶段 2 的运行编排。"""

    def __init__(
        self, registry: SourceRegistry, *, clock: Clock | None = None
    ) -> None:
        self._registry = registry
        self._clock = clock or SystemClock()

    def collect(
        self, request: CollectionRequest, source_ids: Sequence[str] | None = None
    ) -> SourceCollection:
        return self._registry.collect_all(
            SourceContext(request=request, http=self._registry.http, clock=self._clock),
            source_ids,
        )

    def probe(
        self, source_ids: Sequence[str] | None = None
    ) -> tuple[SourceHealth, ...]:
        return self._registry.probe(
            ProbeContext(http=self._registry.http, clock=self._clock), source_ids
        )

    @staticmethod
    def collection_json(result: SourceCollection) -> str:
        payload = {
            "status": _health_status(result.health),
            "sources": [item.model_dump(mode="json") for item in result.health],
            "candidates": [item.model_dump(mode="json") for item in result.candidates],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def probe_json(health: Sequence[SourceHealth]) -> str:
        payload = {
            "status": _health_status(health),
            "sources": [item.model_dump(mode="json") for item in health],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def exit_code(health: Sequence[SourceHealth]) -> int:
        return {"complete": 0, "partial": 3, "failed": 1}[_health_status(health)]


class PipelineCollector:
    """阶段 3 的流水线：采集、规范化、去重和提交 RunReport。"""

    def __init__(
        self,
        registry: SourceRegistry,
        store: NewsStore,
        *,
        clock: Clock | None = None,
        normalizer: Normalizer | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._clock = clock or SystemClock()
        self._normalizer = normalizer

    def collect(
        self, request: CollectionRequest, source_ids: Sequence[str] | None = None
    ) -> RunReport:
        started_at = self._clock.now()
        raw = SourceCollector(self._registry, clock=self._clock).collect(
            request, source_ids
        )
        finished_at = self._clock.now()
        status = _health_status(raw.health)
        effective_request = _request_with_sources(request, source_ids)
        items, dedup_state, normalized_count = self._process_items(
            raw, started_at, status
        )
        report = RunReport(
            run_id=started_at.isoformat(),
            status=status,
            requested_range=effective_request,
            started_at=started_at,
            finished_at=finished_at,
            sources=[_source_result(item) for item in raw.health],
            stats={
                "candidate_count": len(raw.candidates),
                "normalized_count": normalized_count,
                "item_count": len(items),
                "deduplicated_count": normalized_count - len(items),
                "verified_count": 0,
                "unverified_count": len(items),
            },
            items=list(items),
        )
        self._store.commit(
            report,
            dedup_state=dedup_state if status in {"complete", "partial"} else None,
        )
        return report

    def _process_items(
        self,
        raw: SourceCollection,
        observed_at: datetime,
        status: str,
    ) -> tuple[tuple[NewsItem, ...], DedupState | None, int]:
        if status == "failed":
            return (), None, 0
        roles = getattr(self._registry, "source_roles", {})
        normalizer = self._normalizer or Normalizer(roles)
        normalized = normalizer.normalize(raw.candidates, observed_at=observed_at)
        deduplicator = Deduplicator(self._store.load_dedup_state())
        return (
            deduplicator.deduplicate(normalized),
            deduplicator.state,
            len(normalized),
        )


Collector = PipelineCollector


def _health_status(
    health: Sequence[SourceHealth],
) -> Literal["complete", "partial", "failed"]:
    if health and all(item.health == "healthy" for item in health):
        return "complete"
    if any(item.health in {"healthy", "degraded"} for item in health):
        return "partial"
    return "failed"


def _source_result(health: SourceHealth) -> SourceResult:
    return SourceResult(
        source_id=health.source_id,
        role=normalize_source_role(health.role),
        health=health.health,
        fetched_count=health.fetched_count,
        accepted_count=health.accepted_count,
        duration_ms=health.duration_ms,
        error=health.error,
    )


def _request_with_sources(
    request: CollectionRequest, source_ids: Sequence[str] | None
) -> CollectionRequest:
    if source_ids is None:
        return request
    return request.model_copy(update={"source_ids": list(dict.fromkeys(source_ids))})
