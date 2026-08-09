"""来源采集、规范化、增量核验与提交 RunReport。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Literal

from mynews.application.verification import (
    CoordinatedVerification,
    VerificationCoordinator,
)
from mynews.domain.deduplication import Deduplicator, DedupState
from mynews.domain.models import (
    Candidate,
    CollectionRequest,
    NewsItem,
    PendingVerificationEntry,
    PendingVerificationState,
    PriceSnapshot,
    RunReport,
    SourceResult,
    VerificationStats,
)
from mynews.domain.normalization import Normalizer, normalize_source_role
from mynews.domain.relevance import AiTechnologyRelevanceFilter
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
from mynews.verification.pending import PendingVerificationManager, RetryPolicy
from mynews.verification.protocol import (
    EvidenceVerifier,
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)


class SourceCollector:
    """在 CLI 与 SourceRegistry 之间隐藏来源运行编排。"""

    def __init__(
        self,
        registry: SourceRegistry,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._registry = registry
        self._clock = clock or SystemClock()

    def collect(
        self,
        request: CollectionRequest,
        source_ids: Sequence[str] | None = None,
    ) -> SourceCollection:
        return self._registry.collect_all(
            SourceContext(
                request=request,
                http=self._registry.http,
                clock=self._clock,
            ),
            source_ids,
        )

    def probe(
        self,
        source_ids: Sequence[str] | None = None,
    ) -> tuple[SourceHealth, ...]:
        return self._registry.probe(
            ProbeContext(http=self._registry.http, clock=self._clock),
            source_ids,
        )

    @staticmethod
    def collection_json(result: SourceCollection) -> str:
        payload = {
            "status": _health_status(result.health),
            "sources": [item.model_dump(mode="json") for item in result.health],
            "candidates": [
                item.model_dump(mode="json") for item in result.candidates
            ],
            "price_snapshots": [
                item.model_dump(mode="json")
                for item in result.price_snapshots
            ],
            "source_snapshots": [
                item.model_dump(mode="json") for item in result.snapshots
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
        return {"complete": 0, "partial": 3, "failed": 1}[
            _health_status(health)
        ]


class PipelineCollector:
    """采集、规范化、去重、增量核验并事务化提交。"""

    def __init__(
        self,
        registry: SourceRegistry,
        store: NewsStore,
        *,
        clock: Clock | None = None,
        normalizer: Normalizer | None = None,
        verifier: EvidenceVerifier | None = None,
        verification_config: VerificationConfig | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._clock = clock or SystemClock()
        self._normalizer = normalizer
        self._verifier = verifier or CodexVerifier(
            registry.http,
            clock=self._clock,
        )
        self._verification_config = (
            verification_config or VerificationConfig()
        )
        self._retry_policy = retry_policy

    def collect(
        self,
        request: CollectionRequest,
        source_ids: Sequence[str] | None = None,
    ) -> RunReport:
        started_at = self._clock.now()
        raw = SourceCollector(self._registry, clock=self._clock).collect(
            request,
            source_ids,
        )
        finished_at = self._clock.now()
        status = _health_status(raw.health)
        raw = self._observe_price_snapshots(raw, status)
        self._observe_source_snapshots(raw, status)
        config = _config_for_request(request, self._verification_config)
        effective_request = _request_with_sources(
            request,
            source_ids,
            config,
        )
        filtered_raw, filtered_count, filter_reasons = _filter_discovery(
            raw,
            getattr(self._registry, "source_roles", {}),
        )
        (
            items,
            dedup_state,
            pending_state,
            normalized_count,
            deduplicated_count,
            discovery_attempted,
            verification_stats,
        ) = self._process_items(
            filtered_raw,
            started_at,
            status,
            config,
        )
        no_primary_evidence = sum(
            item.verification_status == "unverified"
            and not item.primary_evidence
            for item in items
        )
        reason_counts = dict(filter_reasons)
        reason_counts["no_primary_evidence"] = no_primary_evidence
        for item in items:
            if item.verification_status == "unverified":
                key = f"verification:{item.verification_reason}"
                reason_counts[key] = reason_counts.get(key, 0) + 1
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
                "deduplicated_count": deduplicated_count,
                "filtered": filtered_count,
                "filtered_irrelevant": filtered_count,
                "verification_attempted": verification_stats.attempted,
                "verification_retried": verification_stats.retried,
                "verification_pending": verification_stats.pending,
                "verification_expired": verification_stats.expired,
                "discovery_verification_attempted": discovery_attempted,
                "no_primary_evidence": no_primary_evidence,
                "verified_count": sum(
                    item.verification_status == "verified" for item in items
                ),
                "unverified_count": sum(
                    item.verification_status == "unverified" for item in items
                ),
            },
            reason_counts=reason_counts,
            verification_stats=verification_stats,
            items=list(items),
        )
        successful = status in {"complete", "partial"}
        self._store.commit(
            report,
            dedup_state=dedup_state if successful else None,
            pending_state=pending_state if successful else None,
        )
        return report

    def _observe_price_snapshots(
        self,
        raw: SourceCollection,
        status: str,
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

    def _observe_source_snapshots(
        self,
        raw: SourceCollection,
        status: str,
    ) -> None:
        if status == "failed":
            return
        for snapshot in raw.snapshots:
            self._store.save_source_snapshot(snapshot)

    def _process_items(
        self,
        raw: SourceCollection,
        observed_at: datetime,
        status: str,
        config: VerificationConfig,
    ) -> tuple[
        tuple[NewsItem, ...],
        DedupState | None,
        PendingVerificationState | None,
        int,
        int,
        int,
        VerificationStats,
    ]:
        if status == "failed":
            return (
                (),
                None,
                None,
                0,
                0,
                0,
                VerificationStats(),
            )
        roles = getattr(self._registry, "source_roles", {})
        normalizer = self._normalizer or Normalizer(roles)
        normalized = normalizer.normalize(
            raw.candidates,
            observed_at=observed_at,
        )
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
        manager = PendingVerificationManager(
            self._store.load_pending_verifications(),
            self._retry_policy,
        )
        coordinated = VerificationCoordinator(
            self._verifier,
            manager,
        ).verify(
            targets,
            now=observed_at,
            config=config,
        )
        items = _coordinated_items(coordinated)
        discovery_attempted = sum(
            target.source_role == "discovery"
            for target in coordinated.targets
        )
        return (
            items,
            deduplicator.state,
            manager.state,
            len(normalized),
            len(normalized) - len(deduplicated),
            discovery_attempted,
            coordinated.stats,
        )


Collector = PipelineCollector


def _coordinated_items(
    coordinated: CoordinatedVerification,
) -> tuple[NewsItem, ...]:
    pending_by_key = {
        entry.event_key: entry for entry in coordinated.pending
    }
    items: list[NewsItem] = []
    seen: set[str] = set()
    for target, decision in zip(
        coordinated.targets,
        coordinated.decisions,
        strict=True,
    ):
        entry = pending_by_key.get(target.item.event_key)
        if entry is not None:
            items.append(_pending_item(entry))
        else:
            items.append(_apply_decision(target.item, decision))
        seen.add(target.item.event_key)
    items.extend(
        _pending_item(entry)
        for entry in coordinated.pending
        if entry.event_key not in seen
    )
    return tuple(items)


def _pending_item(entry: PendingVerificationEntry) -> NewsItem:
    return entry.item.model_copy(
        update={
            "verification_status": "unverified",
            "verification_reason": (
                entry.terminal_reason or entry.last_reason
            ),
            "primary_evidence": [],
            "verification_retry": entry.retry_view(),
        }
    )


def _health_status(
    health: Sequence[SourceHealth],
) -> Literal["complete", "partial", "failed"]:
    stable_health = tuple(
        item for item in health if item.stability != "experimental"
    )
    if not stable_health:
        return "complete"
    if all(item.health == "healthy" for item in stable_health):
        return "complete"
    if any(
        item.health in {"healthy", "degraded"}
        for item in stable_health
    ):
        return "partial"
    return "failed"


def _price_changed(
    previous: PriceSnapshot,
    current: PriceSnapshot,
) -> bool:
    return (
        previous.content_hash != current.content_hash
        or previous.url != current.url
    )


def _pricing_candidate(
    previous: PriceSnapshot,
    current: PriceSnapshot,
) -> Candidate:
    return Candidate.model_validate(
        {
            "source_id": current.source_id,
            "title_original": f"{current.source_id} 官方价格页发生变化",
            "url": current.url,
            "published_at": current.published_at,
            "excerpt": (
                f"规范化快照由 {previous.content_hash} "
                f"变为 {current.content_hash}"
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
        stability=health.stability,
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
        ),
        "verification_reasoning_effort": (
            request.verification_reasoning_effort
            if request.verification_reasoning_effort is not None
            else config.reasoning_effort
        ),
    }
    if source_ids is not None:
        updates["source_ids"] = list(dict.fromkeys(source_ids))
    return request.model_copy(update=updates)


def _config_for_request(
    request: CollectionRequest,
    config: VerificationConfig,
) -> VerificationConfig:
    if request.verification_budget is None:
        if request.verification_reasoning_effort is None:
            return config
        return replace(
            config,
            reasoning_effort=request.verification_reasoning_effort,
        )
    return replace(
        config,
        budget=request.verification_budget,
        reasoning_effort=(
            request.verification_reasoning_effort or config.reasoning_effort
        ),
    )


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
        source_id = getattr(candidate, "source_id", None) or (
            item.discovery_sources[0]
            if item.discovery_sources
            else "unknown"
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
                official_domains=getattr(
                    metadata,
                    "official_domains",
                    (),
                ),
                official_github_organizations=getattr(
                    metadata,
                    "official_github_organizations",
                    (),
                ),
                source_role=getattr(
                    metadata,
                    "role",
                    item.source_roles[0]
                    if item.source_roles
                    else "discovery",
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


def _filter_discovery(
    raw: SourceCollection,
    source_roles: Mapping[str, str] | object,
) -> tuple[SourceCollection, int, dict[str, int]]:
    roles = source_roles if isinstance(source_roles, Mapping) else {}
    policy = AiTechnologyRelevanceFilter()
    kept: list[Candidate] = []
    reasons: dict[str, int] = {}
    filtered = 0
    for candidate in raw.candidates:
        role = normalize_source_role(
            candidate.source_role or roles.get(candidate.source_id)
        )
        if role != "discovery":
            kept.append(candidate)
            continue
        decision = policy.evaluate(candidate)
        if decision.relevant:
            kept.append(
                candidate.model_copy(
                    update={"relevance_score": decision.score}
                )
            )
            continue
        filtered += 1
        key = f"filtered:{decision.reason}"
        reasons[key] = reasons.get(key, 0) + 1
    return replace(raw, candidates=tuple(kept)), filtered, reasons


def _apply_decision(
    item: NewsItem,
    decision: VerificationDecision | None,
) -> NewsItem:
    if decision is None or decision.status == "unverified":
        return item.model_copy(
            update={
                "verification_status": "unverified",
                "verification_reason": (
                    decision.reason if decision else "verifier_no_decision"
                ),
                "primary_evidence": [],
                "verification_retry": None,
            }
        )
    evidence = decision.evidence
    if evidence is None:
        raise ValueError("verified 判定缺少证据")
    return item.model_copy(
        update={
            "verification_status": "verified",
            "verification_reason": decision.reason,
            "primary_evidence": [evidence],
            "verification_retry": None,
        }
    )
