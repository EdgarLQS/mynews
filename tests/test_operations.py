from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mynews.application.operations import (
    OperationsError,
    build_retention_plan,
    diagnose,
    recovery_check,
    write_operations_report,
)
from mynews.domain.operations import OperationsReport

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _write_report(
    path: Path,
    *,
    run_id: str,
    status: str = "partial",
    source_health: str = "healthy",
    source_code: str | None = None,
    reason_counts: dict[str, int] | None = None,
    finished_at: str = "2026-08-26T10:00:00+00:00",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_error = (
        {"code": source_code, "message": "source failure"}
        if source_code is not None
        else None
    )
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": status,
        "requested_range": {
            "from": "2026-08-25T10:00:00+00:00",
            "to": "2026-08-26T10:00:00+00:00",
            "timezone": "UTC",
            "source_ids": ["fixture-source"],
            "verification_budget": 30,
        },
        "started_at": finished_at,
        "finished_at": finished_at,
        "sources": [
            {
                "source_id": "fixture-source",
                "role": "primary",
                "health": source_health,
                "fetched_count": 0,
                "accepted_count": 0,
                "duration_ms": 1,
                "error": source_error,
            }
        ],
        "stats": {"candidate_count": 0, "verified_count": 0},
        "reason_counts": reason_counts or {},
        "items": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_automation_state(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "lastAttemptAt": "2026-08-26T11:00:00+00:00",
                "lastSuccessAt": "2026-08-26T10:00:00+00:00",
                "lastCompletedSlot": "2026-08-26 09:00",
                "lastReport": "output/editorial/automation/reports/referenced.md",
                "reportedEvents": {},
            }
        ),
        encoding="utf-8",
    )


def _age_file(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def test_diagnose_classifies_failures_and_does_not_echo_log_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime"
    _write_report(
        root / "output/runs/failed.json",
        run_id="failed",
        status="failed",
        source_health="failed",
        source_code="network_timeout",
        reason_counts={"codex_timeout": 2, "no_primary_evidence": 3},
        finished_at="2026-08-20T10:00:00+00:00",
    )
    _write_report(
        root / "output/latest.json",
        run_id="latest",
        finished_at="2026-08-20T10:00:00+00:00",
    )
    _write_automation_state(root / "state/editorial/automation/state.json")
    (root / "state/pending_verifications.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (root / "state/pending_verifications.json").write_text(
        '{"schema_version":"1.0","entries":{"event-a":{}}}',
        encoding="utf-8",
    )
    secret = "API_KEY=must-not-appear"
    (root / "logs").mkdir(parents=True)
    (root / "logs/collect.log").write_text(
        f"{secret}\ncodex_timeout\n", encoding="utf-8"
    )

    report = diagnose(root, days=3, now=NOW)

    assert report.status == "partial"
    categories = {issue.category for issue in report.issues}
    assert {"source", "network", "codex", "evidence", "storage"} <= categories
    assert report.summary.pending_count == 1
    assert report.summary.latest_age_days == 6
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    assert secret not in rendered
    assert "output/runs/failed.json" in {file.path for file in report.files}


def test_retention_plan_only_lists_unprotected_old_files(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    old_timestamp = datetime(2026, 7, 1, tzinfo=UTC).timestamp()
    _write_report(
        root / "output/latest.json",
        run_id="keep-run",
        finished_at="2026-07-01T10:00:00+00:00",
    )
    _write_report(
        root / "output/runs/keep-run.json",
        run_id="keep-run",
        finished_at="2026-07-01T10:00:00+00:00",
    )
    old_candidate = root / "output/runs/old-run.json"
    _write_report(old_candidate, run_id="old-run")
    referenced = root / "output/editorial/automation/reports/referenced.md"
    referenced.parent.mkdir(parents=True, exist_ok=True)
    referenced.write_text("report", encoding="utf-8")
    unreferenced = root / "output/editorial/automation/reports/unreferenced.md"
    unreferenced.write_text("report", encoding="utf-8")
    referenced_run = root / "output/runs/referenced-by-digest.json"
    _write_report(referenced_run, run_id="referenced-by-digest")
    digest = root / "output/digests/digest-old.json"
    digest.parent.mkdir(parents=True, exist_ok=True)
    digest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "digest_id": "digest-old",
                "run_id": "referenced-by-digest",
                "generated_at": "2026-08-26T10:00:00+00:00",
                "status": "complete",
                "main_items": [],
                "lead_items": [],
                "stats": {},
                "summary_errors": [],
            }
        ),
        encoding="utf-8",
    )
    _write_automation_state(root / "state/editorial/automation/state.json")
    ledger = root / "output/editorial/publication-ledger.csv"
    ledger.write_text(
        "date,event_id,title,platform,url,published_at\n", encoding="utf-8"
    )
    for path in (old_candidate, referenced, unreferenced, ledger, referenced_run):
        _age_file(path, old_timestamp)

    report = build_retention_plan(root, older_than_days=30, now=NOW)

    candidates = {candidate.path for candidate in report.candidates}
    assert candidates == {
        "output/runs/old-run.json",
        "output/editorial/automation/reports/unreferenced.md",
    }
    assert "output/latest.json" in report.protected_paths
    assert "output/runs/keep-run.json" in report.protected_paths
    assert "output/runs/referenced-by-digest.json" in report.protected_paths
    assert "output/editorial/automation/reports/referenced.md" in report.protected_paths
    assert ledger.exists()
    assert report.status == "complete"


def test_recovery_check_copies_only_whitelist_and_validates_schemas(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_report(source / "output/runs/run.json", run_id="run")
    _write_report(source / "output/latest.json", run_id="run")
    (source / "state").mkdir(parents=True, exist_ok=True)
    (source / "state/dedup.json").write_text(
        '{"schema_version":"1.0","events":{}}', encoding="utf-8"
    )
    (source / "state/pending_verifications.json").write_text(
        '{"schema_version":"1.0","entries":{}}', encoding="utf-8"
    )
    _write_automation_state(source / "state/editorial/automation/state.json")
    report_path = source / "output/editorial/automation/reports/referenced.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# report\n", encoding="utf-8")
    ledger = source / "output/editorial/publication-ledger.csv"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "date,event_id,title,platform,url,published_at\n", encoding="utf-8"
    )
    (source / "secret.txt").write_text("not copied", encoding="utf-8")

    report = recovery_check(source, target)

    assert report.status == "complete"
    assert (target / "output/latest.json").is_file()
    assert (target / "output/runs/run.json").is_file()
    assert (target / "state/dedup.json").is_file()
    assert (target / "state/pending_verifications.json").is_file()
    assert (target / "state/editorial/automation/state.json").is_file()
    assert (target / "output/editorial/publication-ledger.csv").is_file()
    assert not (target / "secret.txt").exists()
    assert report.summary.copied_count == len(report.files)
    assert all(check.status == "passed" for check in report.checks)

    empty_target = tmp_path / "empty-target"
    empty_target.mkdir()
    second_report = recovery_check(source, empty_target)
    assert second_report.status == "complete"
    assert (empty_target / "output/latest.json").is_file()


def test_recovery_check_rejects_nonempty_target_without_overwriting(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(OperationsError, match="目标目录必须为空"):
        recovery_check(source, target)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_recovery_check_rejects_symlink_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    symlink_target = tmp_path / "target"
    symlink_target.symlink_to(real_target, target_is_directory=True)

    with pytest.raises(OperationsError, match="符号链接"):
        recovery_check(source, symlink_target)


def test_recovery_check_rejects_empty_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(OperationsError, match="缺少可恢复数据"):
        recovery_check(source, tmp_path / "target")


def test_operations_outputs_are_atomic_and_schema_valid(tmp_path: Path) -> None:
    report = OperationsReport.empty("diagnose")
    paths = write_operations_report(report, tmp_path)

    assert paths == (
        tmp_path / "operations.json",
        tmp_path / "operations.md",
    )
    assert (
        OperationsReport.model_validate_json(paths[0].read_text(encoding="utf-8"))
        == report
    )
    assert "# mynews 运行可靠性" in paths[1].read_text(encoding="utf-8")


def test_operations_file_rejects_absolute_path() -> None:
    with pytest.raises(ValueError, match="相对路径"):
        OperationsReport(
            operation="diagnose",
            status="complete",
            files=[
                {
                    "path": "/private/absolute.json",
                    "size_bytes": 0,
                    "sha256": "sha256:" + "0" * 64,
                }
            ],
        )


def test_operations_output_failure_keeps_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = OperationsReport.empty("diagnose")
    write_operations_report(report, tmp_path)
    before = (tmp_path / "operations.json").read_bytes()

    def fail_commit(self: object, writes: object) -> None:
        del self, writes
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(
        "mynews.application.operations.ArtifactCommitter.commit", fail_commit
    )

    with pytest.raises(OperationsError, match="运行可靠性报告提交失败"):
        write_operations_report(report, tmp_path)
    assert (tmp_path / "operations.json").read_bytes() == before
