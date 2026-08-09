from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest

from mynews.application.collector import PipelineCollector
from mynews.application.verification import VerificationCoordinator
from mynews.domain.models import (
    Candidate,
    CollectionRequest,
    Evidence,
    EvidenceValidation,
    PendingVerificationState,
    RunReport,
    SourceError,
)
from mynews.domain.normalization import Normalizer
from mynews.sources.protocol import SourceCollection, SourceHealth, SourceMetadata
from mynews.storage.json_store import JsonNewsStore, JsonStoreError
from mynews.verification.pending import PendingVerificationManager, RetryPolicy
from mynews.verification.protocol import (
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)

NOW = datetime(2026, 8, 5, 1, 30, tzinfo=UTC)


class NullHttp:
    def get(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("unexpected network request")


class SequenceClock:
    def __init__(self, values: Sequence[datetime]) -> None:
        self._values = iter(values)

    def now(self) -> datetime:
        return next(self._values)


class Registry:
    def __init__(
        self,
        candidate: Candidate | None,
        *,
        health: Literal["healthy", "failed"] = "healthy",
    ) -> None:
        self.http = NullHttp()
        self._candidate = candidate
        self._health = health
        self.source_roles = {"hn": "discovery"}
        self.source_metadata = {
            "hn": SourceMetadata(
                source_id="hn",
                name="HN",
                role="discovery",
                homepage="https://news.ycombinator.com",
                official_domains=("openai.com",),
                official_github_organizations=("openai",),
            )
        }

    def collect_all(
        self,
        context: object,
        source_ids: Sequence[str] | None = None,
    ) -> SourceCollection:
        del context, source_ids
        candidates = (self._candidate,) if self._candidate is not None else ()
        return SourceCollection(
            candidates=candidates,
            health=(
                SourceHealth(
                    source_id="hn",
                    role="discovery",
                    health=self._health,
                    fetched_count=len(candidates),
                    accepted_count=len(candidates),
                    duration_ms=1,
                    checked_at=NOW,
                    error=(
                        None
                        if self._health == "healthy"
                        else SourceError(
                            code="fixture_failed",
                            message="fixture failed",
                        )
                    ),
                ),
            ),
        )

    def probe(
        self,
        context: object,
        source_ids: object = None,
    ) -> tuple[SourceHealth, ...]:
        del context, source_ids
        return ()


def candidate() -> Candidate:
    return Candidate(
        source_id="hn",
        title_original="OpenAI AI model release",
        url="https://media.example/story",
        published_at=NOW,
        excerpt="Official AI release",
        source_role="discovery",
        relevance_score=90,
    )


def item_target() -> VerificationTarget:
    raw = candidate()
    item = Normalizer(source_roles={"hn": "discovery"}).normalize(
        [raw], observed_at=NOW
    )[0]
    return VerificationTarget(
        item=item,
        source_id="hn",
        publisher="OpenAI",
        excerpt="Official AI release",
        official_domains=("openai.com",),
        official_github_organizations=("openai",),
        source_role="discovery",
    )


def strict_evidence(target: VerificationTarget) -> Evidence:
    return Evidence(
        url="https://openai.com/index/release",
        publisher="OpenAI",
        title="Release",
        published_at=target.item.published_at,
        retrieved_at=NOW,
        excerpt="Official AI release",
        content_hash="sha256:verified",
        validation=EvidenceValidation(
            reachable=True,
            official_domain=True,
            redirect_safe=True,
            excerpt_matched=True,
            date_matched=True,
            content_hash_matched=True,
            lifecycle_status="current",
        ),
    )


def request(start: datetime, end: datetime) -> CollectionRequest:
    return CollectionRequest.model_validate(
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "verification_budget": 5,
        }
    )


def empty_report(run_id: str) -> RunReport:
    return RunReport.model_validate(
        {
            "run_id": run_id,
            "status": "complete",
            "requested_range": {
                "from": "2026-08-04T00:00:00+00:00",
                "to": "2026-08-05T00:00:00+00:00",
                "verification_budget": 5,
            },
            "started_at": "2026-08-05T00:00:00+00:00",
            "finished_at": "2026-08-05T00:01:00+00:00",
            "sources": [],
            "stats": {},
            "items": [],
        }
    )


def test_first_failure_enters_pending_and_next_run_retries_without_candidate() -> None:
    target = item_target()

    class SequenceVerifier:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def verify(
            self,
            targets: Sequence[VerificationTarget],
            *,
            config: VerificationConfig,
        ) -> tuple[VerificationDecision, ...]:
            del config
            self.calls.append([entry.item.event_key for entry in targets])
            if len(self.calls) == 1:
                return tuple(
                    VerificationDecision.unverified(
                        entry.item.event_key,
                        "codex_timeout",
                    )
                    for entry in targets
                )
            return tuple(
                VerificationDecision.verified(
                    entry.item.event_key,
                    strict_evidence(entry),
                )
                for entry in targets
            )

    verifier = SequenceVerifier()
    manager = PendingVerificationManager(PendingVerificationState())
    coordinator = VerificationCoordinator(verifier, manager)

    first = coordinator.verify(
        [target], now=NOW, config=VerificationConfig()
    )
    second = coordinator.verify(
        [], now=NOW + timedelta(seconds=1), config=VerificationConfig()
    )

    assert first.stats.pending == 1
    assert second.stats.retried == 1
    assert second.pending == ()
    assert second.decisions[0].status == "verified"
    assert verifier.calls == [[target.item.event_key], [target.item.event_key]]


def test_attempt_limit_and_ttl_have_stable_terminal_reasons() -> None:
    target = item_target()
    attempts = PendingVerificationManager(
        PendingVerificationState(),
        RetryPolicy(
            max_attempts=2,
            base_delay=timedelta(),
            ttl=timedelta(days=2),
        ),
    )
    attempts.record_failure(target, "codex_timeout", now=NOW)
    capped = attempts.record_failure(
        target,
        "codex_timeout",
        now=NOW + timedelta(seconds=1),
    )

    ttl = PendingVerificationManager(
        PendingVerificationState(),
        RetryPolicy(
            max_attempts=5,
            base_delay=timedelta(),
            ttl=timedelta(seconds=1),
        ),
    )
    ttl.record_failure(target, "codex_timeout", now=NOW)
    ttl.due(NOW + timedelta(seconds=2))
    expired = ttl.entries()[0]

    assert capped is not None
    assert capped.status == "expired"
    assert capped.terminal_reason == "verification_attempt_limit_reached"
    assert expired.status == "expired"
    assert expired.terminal_reason == "verification_ttl_expired"


def test_second_collection_retries_pending_after_cross_run_dedup(
    tmp_path: Path,
) -> None:
    raw = candidate()

    class SequenceVerifier:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def verify(
            self,
            targets: Sequence[VerificationTarget],
            *,
            config: VerificationConfig,
        ) -> tuple[VerificationDecision, ...]:
            del config
            self.calls.append([entry.item.event_key for entry in targets])
            if len(self.calls) == 1:
                return tuple(
                    VerificationDecision.unverified(
                        entry.item.event_key,
                        "codex_timeout",
                    )
                    for entry in targets
                )
            return tuple(
                VerificationDecision.verified(
                    entry.item.event_key,
                    strict_evidence(entry),
                )
                for entry in targets
            )

    verifier = SequenceVerifier()
    collector = PipelineCollector(
        Registry(raw),
        JsonNewsStore(tmp_path),
        clock=SequenceClock(
            [
                NOW,
                NOW + timedelta(seconds=1),
                NOW + timedelta(minutes=1),
                NOW + timedelta(minutes=1, seconds=1),
            ]
        ),
        verifier=verifier,
        verification_config=VerificationConfig(),
    )

    first = collector.collect(request(NOW - timedelta(days=1), NOW))
    second = collector.collect(
        request(NOW, NOW + timedelta(minutes=2))
    )

    assert first.verification_stats.pending == 1
    assert second.stats["deduplicated_count"] == 1
    assert second.verification_stats.retried == 1
    assert second.verification_stats.pending == 0
    assert second.items[0].verification_status == "verified"
    assert JsonNewsStore(tmp_path).load_pending_verifications().entries == {}


def test_failed_source_run_does_not_mutate_pending_state(tmp_path: Path) -> None:
    store = JsonNewsStore(tmp_path)
    manager = PendingVerificationManager(PendingVerificationState())
    manager.record_failure(item_target(), "codex_timeout", now=NOW)
    store.save_pending_verifications(manager.state)
    before = (tmp_path / "state/pending_verifications.json").read_bytes()

    class NoCallVerifier:
        def verify(
            self,
            targets: Sequence[VerificationTarget],
            *,
            config: VerificationConfig,
        ) -> tuple[VerificationDecision, ...]:
            del targets, config
            raise AssertionError("failed source run must not verify pending")

    report = PipelineCollector(
        Registry(None, health="failed"),
        store,
        clock=SequenceClock([NOW, NOW + timedelta(seconds=1)]),
        verifier=NoCallVerifier(),
    ).collect(request(NOW - timedelta(days=1), NOW))

    assert report.status == "failed"
    assert (tmp_path / "state/pending_verifications.json").read_bytes() == before


def test_commit_failure_rolls_back_run_latest_dedup_and_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = JsonNewsStore(tmp_path)
    baseline_pending = PendingVerificationManager(PendingVerificationState())
    baseline_pending.record_failure(item_target(), "codex_timeout", now=NOW)
    store.commit(
        empty_report("baseline"),
        pending_state=baseline_pending.state,
    )
    before = {
        path: path.read_bytes()
        for path in (
            tmp_path / "output/latest.json",
            tmp_path / "state/pending_verifications.json",
        )
    }
    original_replace = os.replace
    failed = False

    def fail_once(source: object, destination: object) -> None:
        nonlocal failed
        if not failed and str(destination).endswith("latest.json"):
            failed = True
            raise OSError("simulated replace failure")
        original_replace(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr("mynews.storage.json_store.os.replace", fail_once)
    changed = PendingVerificationManager(
        baseline_pending.state.model_copy(deep=True)
    )
    changed.record_failure(
        item_target(),
        "codex_timeout",
        now=NOW + timedelta(seconds=1),
    )

    with pytest.raises(JsonStoreError):
        store.commit(empty_report("failed-commit"), pending_state=changed.state)

    assert not (tmp_path / "output/runs/failed-commit.json").exists()
    for path, payload in before.items():
        assert path.read_bytes() == payload
