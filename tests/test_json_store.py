from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mynews.domain.deduplication import DedupState
from mynews.domain.models import (
    CollectionRequest,
    PriceSnapshot,
    RunReport,
    SourceError,
    SourceResult,
    SourceSnapshot,
)
from mynews.storage.json_store import JsonNewsStore

NOW = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)


def request() -> CollectionRequest:
    return CollectionRequest.model_validate(
        {
            "from": "2026-08-01T00:00:00+00:00",
            "to": "2026-08-02T00:00:00+00:00",
            "verification_budget": 30,
        }
    )


def report(run_id: str, status: str = "complete") -> RunReport:
    source = SourceResult(
        source_id="fixture",
        role="primary",
        health="healthy" if status != "failed" else "failed",
        fetched_count=1,
        accepted_count=1,
        duration_ms=1,
        error=(
            SourceError(code="fixture_failed", message="fixture failed")
            if status == "failed"
            else None
        ),
    )
    return RunReport(
        run_id=run_id,
        status=status,
        requested_range=request(),
        started_at=NOW,
        finished_at=NOW,
        sources=[source],
        stats={"item_count": 0},
        items=[],
    )


def test_store_appends_runs_and_failed_run_does_not_replace_latest(
    tmp_path: Path,
) -> None:
    store = JsonNewsStore(tmp_path)

    store.commit(report("run-1"))
    latest_before = (tmp_path / "output/latest.json").read_bytes()
    store.commit(report("run-2", "failed"))

    run_files = sorted((tmp_path / "output/runs").glob("*.json"))
    assert [path.stem for path in run_files] == ["run-1", "run-2"]
    assert json.loads(latest_before) == json.loads(
        (tmp_path / "output/latest.json").read_text(encoding="utf-8")
    )
    assert json.loads(run_files[1].read_text(encoding="utf-8"))["status"] == "failed"


def test_store_serializes_collection_request_with_json_aliases(
    tmp_path: Path,
) -> None:
    store = JsonNewsStore(tmp_path)

    store.commit(report("run-alias"))

    payload = json.loads(
        (tmp_path / "output/runs/run-alias.json").read_text(encoding="utf-8")
    )
    requested_range = payload["requested_range"]
    assert "from" in requested_range
    assert "from_" not in requested_range


def test_store_recovers_dedup_state_and_tracks_first_price_observation(
    tmp_path: Path,
) -> None:
    store = JsonNewsStore(tmp_path)
    state = DedupState()
    store.save_dedup_state(state)

    recovered = store.load_dedup_state()
    snapshot = PriceSnapshot(
        source_id="provider",
        url="https://EXAMPLE.test/pricing/?utm_source=feed#top",
        observed_at=NOW,
        first_observed_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        content_hash="sha256:new",
        values={"model": "1.00"},
    )
    stored = store.save_price_snapshot(snapshot)
    stored_again = store.save_price_snapshot(
        snapshot.model_copy(
            update={
                "url": "https://example.test/pricing",
                "observed_at": datetime(2026, 8, 3, tzinfo=UTC),
            }
        )
    )

    assert recovered == state
    assert stored.url == "https://example.test/pricing"
    assert stored.first_observed_at == datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    assert stored_again.first_observed_at == datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    assert (tmp_path / "state/dedup.json").exists()
    assert (tmp_path / "state/price_snapshots/provider.json").exists()
    assert isinstance(
        json.loads((tmp_path / "state/price_snapshots/provider.json").read_text()),
        dict,
    )


def test_store_persists_source_directory_snapshot(tmp_path: Path) -> None:
    snapshot = SourceSnapshot(
        source_id="openai",
        url="https://developers.openai.com/api/docs/models/",
        observed_at=NOW,
        content_hash="sha256:directory",
        values={"entry_count": 2},
    )

    store = JsonNewsStore(tmp_path)
    stored = store.save_source_snapshot(snapshot)

    assert stored.url == "https://developers.openai.com/api/docs/models"
    assert store.load_source_snapshot("openai") == stored
    assert (tmp_path / "state/source_snapshots/openai.json").exists()
