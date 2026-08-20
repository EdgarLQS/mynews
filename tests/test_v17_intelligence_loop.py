from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import mynews.application.automation as automation_module
import mynews.application.editorial_io as editorial_io_module
from mynews.application.automation import (
    commit_automation_output,
    empty_automation_state,
    validate_automation_state,
)
from mynews.application.feedback import record_weekly_feedback
from mynews.application.publication import add_publication
from mynews.cli import main
from mynews.storage.json_store import JsonNewsStore
from mynews.verification.codex import SubprocessCodexRunner


def _candidate_file(tmp_path: Path) -> Path:
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "date": "2026-08-11",
                "generatedAt": "2026-08-11T12:00:00Z",
                "candidates": [
                    {
                        "id": "candidate-a",
                        "candidateRef": "2026-08-11:candidate-a",
                        "title": "第一条",
                        "url": "https://example.com/a",
                        "source": "Example",
                        "firstSeenAt": "2026-08-11T08:00:00Z",
                        "duplicateGroupId": "event-a",
                    },
                    {
                        "id": "candidate-b",
                        "candidateRef": "2026-08-11:candidate-b",
                        "title": "第二条",
                        "url": "https://example.com/b",
                        "source": "Example",
                        "firstSeenAt": "2026-08-11T08:00:00Z",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_publication_add_matches_group_then_fallback_and_is_idempotent(
    tmp_path: Path,
) -> None:
    candidate = _candidate_file(tmp_path)
    ledger = tmp_path / "publication-ledger.csv"
    first = add_publication(
        candidate,
        ["event-a", "2026-08-11:candidate-b"],
        title="公开帖子",
        platform="平台 A",
        url="https://social.example/posts/1",
        published_at="2026-08-11T18:00:00+08:00",
        output_path=ledger,
    )
    assert first.status == "created"
    previous = ledger.read_bytes()
    assert previous.count(b"social.example") == 2

    second = add_publication(
        candidate,
        ["event-a", "2026-08-11:candidate-b"],
        title="修改后的标题不会覆盖",
        platform="平台 A",
        url="https://social.example/posts/1",
        published_at="2026-08-11T19:00:00+08:00",
        output_path=ledger,
    )
    assert second.status == "unchanged"
    assert ledger.read_bytes() == previous

    with pytest.raises(ValueError, match="输出安全检查失败"):
        add_publication(
            candidate,
            ["event-a"],
            title="API_KEY=do-not-leak",
            platform="平台 A",
            url="https://social.example/posts/1",
            published_at="2026-08-11T19:00:00+08:00",
            output_path=ledger,
        )
    assert ledger.read_bytes() == previous


def test_publication_mismatch_and_missing_timezone_do_not_write(
    tmp_path: Path,
) -> None:
    candidate = _candidate_file(tmp_path)
    ledger = tmp_path / "ledger.csv"
    with pytest.raises(ValueError, match="事件 ID"):
        add_publication(
            candidate,
            ["not-found"],
            title="标题",
            platform="平台",
            url="https://social.example/post",
            published_at="2026-08-11T18:00:00+08:00",
            output_path=ledger,
        )
    assert not ledger.exists()

    with pytest.raises(ValueError, match="必须包含时区"):
        add_publication(
            candidate,
            ["event-a"],
            title="标题",
            platform="平台",
            url="https://social.example/post",
            published_at="2026-08-11T18:00:00",
            output_path=ledger,
        )
    assert not ledger.exists()


def test_publication_output_cannot_overwrite_candidate(tmp_path: Path) -> None:
    candidate = _candidate_file(tmp_path)
    previous = candidate.read_bytes()

    with pytest.raises(ValueError, match="不能覆盖 Candidate"):
        add_publication(
            candidate,
            ["event-a"],
            title="标题",
            platform="平台",
            url="https://social.example/post",
            published_at="2026-08-11T18:00:00+08:00",
            output_path=candidate,
        )

    assert candidate.read_bytes() == previous


def test_publication_atomic_failure_preserves_old_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate_file(tmp_path)
    ledger = tmp_path / "ledger.csv"
    add_publication(
        candidate,
        ["event-a"],
        title="旧记录",
        platform="平台",
        url="https://social.example/old",
        published_at="2026-08-11T18:00:00+08:00",
        output_path=ledger,
    )
    previous = ledger.read_bytes()

    def fail_replace(source: str, target: str) -> None:
        del source, target
        raise OSError("replace fixture failure")

    monkeypatch.setattr(editorial_io_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace fixture failure"):
        add_publication(
            candidate,
            ["event-a"],
            title="新记录",
            platform="平台",
            url="https://social.example/new",
            published_at="2026-08-11T19:00:00+08:00",
            output_path=ledger,
        )
    assert ledger.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_publication_preserves_legacy_ledger_columns(tmp_path: Path) -> None:
    candidate = _candidate_file(tmp_path)
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "date,event_id,title,platform,url,published_at,legacy_note\n"
        "2026-08-10,event-old,旧标题,平台,https://social.example/old,"
        "2026-08-10T18:00:00+08:00,保留值\n",
        encoding="utf-8",
    )

    result = add_publication(
        candidate,
        ["event-a"],
        title="新记录",
        platform="平台",
        url="https://social.example/new",
        published_at="2026-08-11T18:00:00+08:00",
        output_path=ledger,
    )

    content = ledger.read_text(encoding="utf-8")
    assert result.status == "created"
    assert content.splitlines()[0].endswith(",legacy_note")
    assert "保留值" in content


def test_publication_cli_reports_argument_error_in_chinese(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "publication",
                "add",
                "--candidate-file",
                str(_candidate_file(tmp_path)),
                "--event-id",
                "event-a",
                "--title",
                "标题",
                "--platform",
                "平台",
                "--url",
                "https://social.example/post",
                "--published-at",
                "2026-08-11T18:00:00",
            ]
        )
    assert raised.value.code == 2
    assert "参数错误" in capsys.readouterr().err


def test_feedback_create_idempotent_conflict_and_replace(tmp_path: Path) -> None:
    output = tmp_path / "weekly-feedback.md"
    first = record_weekly_feedback(
        week="2026-W32",
        platform="平台 A",
        reads=10,
        favorites=2,
        shares=1,
        new_followers=3,
        note="读者希望增加示例",
        output_path=output,
    )
    assert first.status == "created"
    previous = output.read_bytes()

    unchanged = record_weekly_feedback(
        week="2026-W32",
        platform="平台 A",
        reads=10,
        favorites=2,
        shares=1,
        new_followers=3,
        note="读者希望增加示例",
        output_path=output,
    )
    assert unchanged.status == "unchanged"
    assert output.read_bytes() == previous

    with pytest.raises(ValueError, match="--replace"):
        record_weekly_feedback(
            week="2026-W32",
            platform="平台 A",
            reads=11,
            favorites=2,
            shares=1,
            new_followers=3,
            output_path=output,
        )
    assert output.read_bytes() == previous

    replaced = record_weekly_feedback(
        week="2026-W32",
        platform="平台 A",
        reads=11,
        favorites=2,
        shares=1,
        new_followers=3,
        output_path=output,
        replace=True,
    )
    assert replaced.status == "created"
    assert "阅读：11" in output.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".*.tmp"))


def test_feedback_cli_rejects_negative_metric(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "feedback",
                "record",
                "--week",
                "2026-W32",
                "--platform",
                "平台",
                "--reads",
                "-1",
                "--favorites",
                "0",
                "--shares",
                "0",
                "--new-followers",
                "0",
            ]
        )
    assert raised.value.code == 2
    assert "非负整数" in capsys.readouterr().err


def test_feedback_privacy_gate_does_not_write_or_echo_secret(tmp_path: Path) -> None:
    output = tmp_path / "weekly-feedback.md"
    with pytest.raises(ValueError) as raised:
        record_weekly_feedback(
            week="2026-W32",
            platform="平台",
            reads=1,
            favorites=0,
            shares=0,
            new_followers=0,
            note="API_KEY=do-not-leak",
            output_path=output,
        )
    assert "do-not-leak" not in str(raised.value)
    assert not output.exists()


def test_feedback_atomic_failure_preserves_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "weekly-feedback.md"
    record_weekly_feedback(
        week="2026-W32",
        platform="平台",
        reads=1,
        favorites=0,
        shares=0,
        new_followers=0,
        output_path=output,
    )
    previous = output.read_bytes()

    def fail_replace(source: str, target: str) -> None:
        del source, target
        raise OSError("replace fixture failure")

    monkeypatch.setattr(editorial_io_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace fixture failure"):
        record_weekly_feedback(
            week="2026-W33",
            platform="平台",
            reads=2,
            favorites=0,
            shares=0,
            new_followers=0,
            output_path=output,
        )
    assert output.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_feedback_rejects_internal_markers_before_writing(tmp_path: Path) -> None:
    output = tmp_path / "weekly-feedback.md"
    marker = "<!-- mynews:weekly-feedback:end week=2026-W32 platform=平台 -->"

    with pytest.raises(ValueError, match="Markdown 注释标记"):
        record_weekly_feedback(
            week="2026-W32",
            platform="平台",
            reads=1,
            favorites=0,
            shares=0,
            new_followers=0,
            note=marker,
            output_path=output,
        )

    assert not output.exists()


def test_feedback_cli_rejects_arbitrary_output_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "feedback",
                "record",
                "--week",
                "2026-W32",
                "--platform",
                "平台",
                "--reads",
                "1",
                "--favorites",
                "0",
                "--shares",
                "0",
                "--new-followers",
                "0",
                "--out",
                str(tmp_path / "unrelated.md"),
            ]
        )

    assert raised.value.code == 2
    assert "无法识别的参数" in capsys.readouterr().err
    assert not (tmp_path / "unrelated.md").exists()


def test_manual_records_do_not_use_network_store_or_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("manual record attempted a forbidden side effect")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(JsonNewsStore, "__init__", forbidden)
    monkeypatch.setattr(SubprocessCodexRunner, "run", forbidden)
    candidate = _candidate_file(tmp_path)
    candidate_before = candidate.read_bytes()

    add_publication(
        candidate,
        ["event-a"],
        title="标题",
        platform="平台",
        url="https://social.example/post",
        published_at="2026-08-11T18:00:00+08:00",
        output_path=tmp_path / "ledger.csv",
    )
    record_weekly_feedback(
        week="2026-W32",
        platform="平台",
        reads=1,
        favorites=0,
        shares=0,
        new_followers=0,
        output_path=tmp_path / "feedback.md",
    )

    assert candidate.read_bytes() == candidate_before
    assert {path.name for path in tmp_path.iterdir()} == {
        "candidates.json",
        "feedback.md",
        "ledger.csv",
    }


def test_automation_commits_report_before_state_and_validates_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "reports/2026-08-11-0900.md"
    state_path = tmp_path / "state/state.json"
    state = empty_automation_state()
    state.update(
        {
            "lastAttemptAt": "2026-08-11T09:00:00+08:00",
            "lastSuccessAt": "2026-08-11T09:05:00+08:00",
            "lastCompletedSlot": "2026-08-11 09:00",
            "lastReport": "output/editorial/automation/reports/2026-08-11-0900.md",
            "reportedEvents": {
                "event-a": {
                    "lastReportedAt": "2026-08-11T09:05:00+08:00",
                    "contentHash": "sha256:test",
                    "reportPath": (
                        "output/editorial/automation/reports/2026-08-11-0900.md"
                    ),
                }
            },
        }
    )
    validate_automation_state(state)
    original_state_write = automation_module.atomic_write_json

    def fail_state(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("state fixture failure")

    monkeypatch.setattr(automation_module, "atomic_write_json", fail_state)
    with pytest.raises(OSError, match="state fixture failure"):
        commit_automation_output(report, "# 报告\n", state_path, state)
    assert report.read_text(encoding="utf-8") == "# 报告\n"
    assert not state_path.exists()
    monkeypatch.setattr(automation_module, "atomic_write_json", original_state_write)

    invalid = dict(state)
    invalid["lastReport"] = "/Users/private/report.md"
    with pytest.raises(ValueError, match="相对路径"):
        validate_automation_state(invalid)


def test_automation_rejects_extra_fields_and_sensitive_event_keys(
    tmp_path: Path,
) -> None:
    extra = empty_automation_state()
    extra["unexpected"] = "value"
    with pytest.raises(ValueError, match="字段无效"):
        validate_automation_state(extra)

    sensitive = empty_automation_state()
    sensitive["reportedEvents"] = {
        "API_KEY=do-not-leak": {
            "lastReportedAt": "2026-08-11T09:05:00+08:00",
            "contentHash": "sha256:test",
            "reportPath": "output/editorial/automation/reports/report.md",
        }
    }
    report = tmp_path / "report.md"
    state_path = tmp_path / "state.json"
    with pytest.raises(ValueError) as raised:
        commit_automation_output(report, "# 报告\n", state_path, sensitive)
    assert "do-not-leak" not in str(raised.value)
    assert not report.exists()
    assert not state_path.exists()
