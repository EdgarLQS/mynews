from pathlib import Path

import pytest

from mynews.storage import artifact_committer as artifact_module
from mynews.storage.artifact_committer import ArtifactCommitter, ArtifactWrite


def test_committer_writes_one_artifact_atomically(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.md"

    ArtifactCommitter().commit((ArtifactWrite.text(target, "报告\n"),))

    assert target.read_text(encoding="utf-8") == "报告\n"
    assert not list(target.parent.glob(".*.tmp"))


def test_committer_batch_restores_replaced_files_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "state" / "first.json"
    second = tmp_path / "output" / "second.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("old-first", encoding="utf-8")
    second.write_text("old-second", encoding="utf-8")
    original_replace = artifact_module.os.replace
    calls = 0

    def fail_second_replace(source: str, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("replace blocked")
        original_replace(source, target)

    monkeypatch.setattr(artifact_module.os, "replace", fail_second_replace)
    with pytest.raises(artifact_module.ArtifactCommitError) as raised:
        ArtifactCommitter().commit(
            (
                ArtifactWrite.text(first, "new-first"),
                ArtifactWrite.text(second, "new-second"),
            )
        )

    error = raised.value
    assert error.phase == "replace"
    assert error.target_path == second
    assert error.rollback_status == "succeeded"
    assert first.read_text(encoding="utf-8") == "old-first"
    assert second.read_text(encoding="utf-8") == "old-second"
    assert not list(tmp_path.rglob(".*.tmp"))


def test_committer_reports_stage_failure_and_cleans_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "report.md"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync blocked")

    monkeypatch.setattr(artifact_module.os, "fsync", fail_fsync)
    with pytest.raises(artifact_module.ArtifactCommitError) as raised:
        ArtifactCommitter().commit((ArtifactWrite.text(target, "报告\n"),))

    error = raised.value
    assert error.phase == "stage"
    assert error.target_path == target
    assert error.rollback_status == "not_needed"
    assert not target.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_committer_reports_rollback_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("old-first", encoding="utf-8")
    second.write_text("old-second", encoding="utf-8")
    original_replace = artifact_module.os.replace
    calls = 0

    def fail_replace_after_first(source: str, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise OSError("replace blocked")
        original_replace(source, target)

    monkeypatch.setattr(artifact_module.os, "replace", fail_replace_after_first)
    with pytest.raises(artifact_module.ArtifactCommitError) as raised:
        ArtifactCommitter().commit(
            (
                ArtifactWrite.text(first, "new-first"),
                ArtifactWrite.text(second, "new-second"),
            )
        )

    error = raised.value
    assert error.phase == "replace"
    assert error.rollback_status == "failed"
    assert error.rollback_errors
    assert first.read_text(encoding="utf-8") == "new-first"
    assert not list(tmp_path.glob(".*.tmp"))
