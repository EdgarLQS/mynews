"""阶段 2 原始来源采集应用层。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Literal

from mynews.domain.deduplication import Deduplicator, DedupState
from mynews.domain.models import (
    Candidate,
    CollectionRequest,
    NewsItem,
    PriceSnapshot,
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
    SourceMetadata,
)
from mynews.sources.registry import SourceRegistry
from mynews.storage.protocol import NewsStore
from mynews.verification.codex import CodexVerifier
from mynews.verification.protocol import (
    EvidenceVerifier,
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)


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
            "price_snapshots": [
                item.model_dump(mode="json") for item in result.price_snapshots
            ],
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
    """阶段 3/4 的流水线：采集、规范化、去重、核验和提交 RunReport。"""

    def __init__(
        self,
        registry: SourceRegistry,
        store: NewsStore,
        *,
        clock: Clock | None = None,
        normalizer: Normalizer | None = None,
        verifier: EvidenceVerifier | None = None,
        verification_config: VerificationConfig | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._clock = clock or SystemClock()
        self._normalizer = normalizer
        self._verifier = verifier or CodexVerifier(registry.http, clock=self._clock)
        self._verification_config = verification_config or VerificationConfig()

    def collect(
        self, request: CollectionRequest, source_ids: Sequence[str] | None = None
    ) -> RunReport:
        started_at = self._clock.now()
        raw = SourceCollector(self._registry, clock=self._clock).collect(
            request, source_ids
        )
        finished_at = self._clock.now()
        status = _health_status(raw.health)
        raw = self._observe_price_snapshots(raw, status)
        verification_config = _config_for_request(
            request, self._verification_config
        )
        effective_request = _request_with_sources(
            request, source_ids, verification_config
        )
        items, dedup_state, normalized_count = self._process_items(
            raw, started_at, status, verification_config
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
                "verified_count": sum(
                    item.verification_status == "verified" for item in items
                ),
                "unverified_count": sum(
                    item.verification_status == "unverified" for item in items
                ),
            },
            items=list(items),
        )
        self._store.commit(
            report,
            dedup_state=dedup_state if status in {"complete", "partial"} else None,
        )
        return report

    def _observe_price_snapshots(
        self, raw: SourceCollection, status: str
    ) -> SourceCollection:
        if status == "failed" or not raw.price_snapshots:
            return raw
        changes: list[Candidate] = []
        for snapshot in raw.price_snapshots:
            previous = self._store.load_price_snapshot(snapshot.source_id)
            stored = self._store.save_price_snapshot(snapshot)
            if previous is not None and _price_changed(previous, stored):
                changes.append(_pricing_candidate(previous, stored))
        return replace(raw, candidates=raw.candidates + tuple(changes))

    def _process_items(
        self,
        raw: SourceCollection,
        observed_at: datetime,
        status: str,
        verification_config: VerificationConfig,
    ) -> tuple[tuple[NewsItem, ...], DedupState | None, int]:
        if status == "failed":
            return (), None, 0
        roles = getattr(self._registry, "source_roles", {})
        normalizer = self._normalizer or Normalizer(roles)
        normalized = normalizer.normalize(raw.candidates, observed_at=observed_at)
        candidates_by_key: dict[str, list[Candidate]] = {}
        for item, candidate in zip(normalized, raw.candidates, strict=True):
            candidates_by_key.setdefault(item.event_key, []).append(candidate)
        deduplicator = Deduplicator(self._store.load_dedup_state())
        deduplicated = deduplicator.deduplicate(normalized)
        targets = _verification_targets(
            deduplicated,
            candidates_by_key,
            getattr(self._registry, "source_metadata", {}),
        )
        verified = _verify_items(
            deduplicated, targets, self._verifier, verification_config
        )
        return (
            verified,
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


def _price_changed(previous: PriceSnapshot, current: PriceSnapshot) -> bool:
    return (
        previous.content_hash != current.content_hash
        or previous.url != current.url
    )


def _pricing_candidate(
    previous: PriceSnapshot, current: PriceSnapshot
) -> Candidate:
    return Candidate.model_validate(
        {
            "source_id": current.source_id,
            "title_original": f"{current.source_id} 官方价格页发生变化",
            "url": current.url,
            "published_at": current.published_at,
            "excerpt": (
                f"规范化快照由 {previous.content_hash} 变为 {current.content_hash}"
            ),
            "heat_signals": {"official_price_page": 1.0},
            "event_type": "pricing_change",
            "source_role": "monitor",
        }
    )


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
    request: CollectionRequest,
    source_ids: Sequence[str] | None,
    config: VerificationConfig,
) -> CollectionRequest:
    updates: dict[str, object] = {
        "verification_budget": (
            request.verification_budget
            if request.verification_budget is not None
            else config.budget
        )
    }
    if source_ids is not None:
        updates["source_ids"] = list(dict.fromkeys(source_ids))
    return request.model_copy(update=updates)


def _config_for_request(
    request: CollectionRequest, config: VerificationConfig
) -> VerificationConfig:
    if request.verification_budget is None:
        return config
    return replace(config, budget=request.verification_budget)


def _verification_targets(
    items: Sequence[NewsItem],
    candidates_by_key: Mapping[str, Sequence[Candidate]],
    source_metadata: Mapping[str, SourceMetadata] | object,
) -> tuple[VerificationTarget, ...]:
    metadata_by_source = (
        source_metadata if isinstance(source_metadata, Mapping) else {}
    )
    targets: list[VerificationTarget] = []
    for item in items:
        candidates = candidates_by_key.get(item.event_key, ())
        candidate = _preferred_candidate(candidates, metadata_by_source)
        source_id = (
            getattr(candidate, "source_id", None)
            or (item.discovery_sources[0] if item.discovery_sources else "unknown")
        )
        metadata = metadata_by_source.get(source_id)
        targets.append(
            VerificationTarget(
                item=item,
                source_id=source_id,
                publisher=getattr(metadata, "name", source_id),
                excerpt=(
                    getattr(candidate, "excerpt", None)
                    or getattr(candidate, "content", None)
                ),
                official_domains=getattr(metadata, "official_domains", ()),
                official_github_organizations=getattr(
                    metadata, "official_github_organizations", ()
                ),
                source_role=getattr(
                    metadata,
                    "role",
                    item.source_roles[0] if item.source_roles else "discovery",
                ),
            )
        )
    return tuple(targets)


def _preferred_candidate(
    candidates: Sequence[Candidate],
    source_metadata: Mapping[str, SourceMetadata],
) -> Candidate | None:
    for candidate in candidates:
        metadata = source_metadata.get(candidate.source_id)
        if metadata is not None and metadata.role in {"primary", "monitor"}:
            return candidate
    return candidates[0] if candidates else None


def _verify_items(
    items: Sequence[NewsItem],
    targets: Sequence[VerificationTarget],
    verifier: EvidenceVerifier,
    config: VerificationConfig,
) -> tuple[NewsItem, ...]:
    try:
        decisions = verifier.verify(targets, config=config)
    except Exception:
        return tuple(
            item.model_copy(
                update={
                    "verification_status": "unverified",
                    "verification_reason": "verifier_failed",
                    "primary_evidence": [],
                }
            )
            for item in items
        )
    by_id = {decision.item_id: decision for decision in decisions}
    return tuple(
        _apply_decision(item, by_id.get(item.event_key))
        for item in items
    )


def _apply_decision(
    item: NewsItem, decision: VerificationDecision | None
) -> NewsItem:
    if decision is None or decision.status == "unverified":
        return item.model_copy(
            update={
                "verification_status": "unverified",
                "verification_reason": (
                    decision.reason if decision else "verifier_no_decision"
                ),
                "primary_evidence": [],
            }
        )
    return item.model_copy(
        update={
            "verification_status": "verified",
            "verification_reason": decision.reason,
            "primary_evidence": [decision.evidence],
        }
    )
