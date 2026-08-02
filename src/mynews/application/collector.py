"""阶段 2 原始来源采集应用层。"""

from __future__ import annotations

import json
from collections.abc import Sequence

from mynews.domain.models import CollectionRequest
from mynews.infrastructure.clock import Clock, SystemClock
from mynews.sources.protocol import (
    ProbeContext,
    SourceCollection,
    SourceContext,
    SourceHealth,
)
from mynews.sources.registry import SourceRegistry


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


def _health_status(health: Sequence[SourceHealth]) -> str:
    if health and all(item.health == "healthy" for item in health):
        return "complete"
    if any(item.health in {"healthy", "degraded"} for item in health):
        return "partial"
    return "failed"
