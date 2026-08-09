from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mynews.application.digest import DigestBuildConfig, DigestBuilder
from mynews.domain.models import CollectionRequest, RunReport
from mynews.storage import digest_store as digest_store_module
from mynews.storage.digest_store import DigestFileStore, DigestStoreError

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _report(run_id: str) -> RunReport:
    return RunReport(
        run_id=run_id,
        status="complete",
        requested_range=CollectionRequest(
            **{
                "from": NOW - timedelta(days=1),
                "to": NOW,
                "timezone": "UTC",
                "verification_budget": 30,
            }
        ),
        started_at=NOW,
        finished_at=NOW,
    )


def _digest(run_id: str):
    return DigestBuilder().build(
        _report(run_id),
        config=DigestBuildConfig(use_codex=False),
        now=NOW,
    )


def test_digest_store_writes_history_latest_json_and_markdown_atomically(
    tmp_path: Path,
) -> None:
    store = DigestFileStore(tmp_path)
    digest = _digest("run-1")

    history, latest_json, latest_markdown = store.write(digest)

    assert history.is_file()
    assert latest_json.is_file()
    assert latest_markdown.is_file()
    assert store.load_latest() == digest
    assert "## 主榜" in latest_markdown.read_text(encoding="utf-8")
    assert not list(tmp_path.rglob("*.tmp"))


def test_digest_store_failure_restores_previous_latest_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DigestFileStore(tmp_path)
    old_digest = _digest("run-old")
    store.write(old_digest)
    latest_before = (tmp_path / "digest-latest.json").read_bytes()
    new_digest = _digest("run-new")
    original_replace = digest_store_module.os.replace
    calls = 0

    def fail_second_replace(source: str, target: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replace failure")
        original_replace(source, target)

    monkeypatch.setattr(digest_store_module.os, "replace", fail_second_replace)

    with pytest.raises(DigestStoreError, match="已恢复"):
        store.write(new_digest)

    assert (tmp_path / "digest-latest.json").read_bytes() == latest_before
    assert store.load_latest() == old_digest
    assert not list((tmp_path / "digests").glob(f"{new_digest.digest_id}*.json"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_digest_history_collision_does_not_overwrite_existing_file(
    tmp_path: Path,
) -> None:
    store = DigestFileStore(tmp_path)
    digest = _digest("run-same")
    store.write(digest)
    before = (tmp_path / "digest-latest.json").read_bytes()

    with pytest.raises(DigestStoreError, match="已存在"):
        store.write(digest)

    assert (tmp_path / "digest-latest.json").read_bytes() == before
