from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from mynews.application.collector import PipelineCollector
from mynews.domain.models import Candidate, CollectionRequest, SourceError
from mynews.sources.protocol import SourceCollection, SourceHealth
from mynews.storage.json_store import JsonNewsStore


class SequenceClock:
    def __init__(self, values: list[datetime]) -> None:
        self.values = iter(values)

    def now(self) -> datetime:
        return next(self.values)


class FakeRegistry:
    http = object()

    def __init__(self, health: tuple[SourceHealth, ...]) -> None:
        self.health = health
        self.source_roles = {item.source_id: item.role for item in health}

    def collect_all(
        self, context: object, source_ids: object = None
    ) -> SourceCollection:
        if any(item.health == "healthy" for item in self.health):
            source_id = next(
                item.source_id for item in self.health if item.health == "healthy"
            )
            candidate = Candidate(
                source_id=source_id,
                title_original="Qwen update",
                url="https://example.test/item",
                published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
                excerpt="A factual update",
            )
            return SourceCollection((candidate,), self.health)
        return SourceCollection((), self.health)


def request() -> CollectionRequest:
    return CollectionRequest.model_validate(
        {
            "from": "2026-08-01T00:00:00+00:00",
            "to": "2026-08-03T00:00:00+00:00",
        }
    )


def health(status: str = "healthy", source_id: str = "fixture") -> SourceHealth:
    return SourceHealth(
        source_id=source_id,
        role="primary",
        health=status,
        fetched_count=1 if status == "healthy" else 0,
        accepted_count=1 if status == "healthy" else 0,
        duration_ms=1,
        checked_at=datetime(2026, 8, 2, tzinfo=UTC),
        error=(
            SourceError(code="fixture_failed", message="fixture failed")
            if status != "healthy"
            else None
        ),
    )


def test_pipeline_collects_normalizes_stores_and_never_verifies(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    collector = PipelineCollector(
        FakeRegistry((health(),)),
        JsonNewsStore(tmp_path),
        clock=SequenceClock([now, now + timedelta(seconds=1)]),
    )

    report = collector.collect(request())

    assert report.status == "complete"
    assert report.stats["candidate_count"] == 1
    assert report.stats["item_count"] == 1
    assert report.items[0].verification_status == "unverified"
    assert report.items[0].source_roles == ["primary"]
    assert (tmp_path / "output/latest.json").exists()


def test_pipeline_partial_is_stored_but_all_failed_does_not_replace_latest(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    store = JsonNewsStore(tmp_path)
    complete = PipelineCollector(
        FakeRegistry((health(),)),
        store,
        clock=SequenceClock([now, now + timedelta(seconds=1)]),
    ).collect(request())
    latest_before = (tmp_path / "output/latest.json").read_bytes()

    partial = PipelineCollector(
        FakeRegistry((health("failed"),)),
        store,
        clock=SequenceClock(
            [now + timedelta(days=1), now + timedelta(days=1, seconds=1)]
        ),
    ).collect(request())

    assert complete.status == "complete"
    assert partial.status == "failed"
    assert (tmp_path / "output/latest.json").read_bytes() == latest_before


def test_pipeline_keeps_usable_items_when_one_source_is_partial(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    report = PipelineCollector(
        FakeRegistry((health("healthy", "good"), health("failed", "bad"))),
        JsonNewsStore(tmp_path),
        clock=SequenceClock([now, now + timedelta(seconds=1)]),
    ).collect(request())

    assert report.status == "partial"
    assert len(report.items) == 1
    assert {item.source_id for item in report.sources} == {"good", "bad"}


def test_pipeline_recovers_dedup_state_across_runs(tmp_path: Path) -> None:
    store = JsonNewsStore(tmp_path)
    first_now = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    second_now = first_now + timedelta(days=1)

    first = PipelineCollector(
        FakeRegistry((health(),)),
        store,
        clock=SequenceClock([first_now, first_now + timedelta(seconds=1)]),
    ).collect(request())
    second = PipelineCollector(
        FakeRegistry((health(),)),
        store,
        clock=SequenceClock([second_now, second_now + timedelta(seconds=1)]),
    ).collect(request())

    assert len(first.items) == 1
    assert second.items == []
    assert len(list((tmp_path / "output/runs").glob("*.json"))) == 2
