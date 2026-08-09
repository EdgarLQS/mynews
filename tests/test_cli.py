from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mynews.cli import build_collection_request, main
from mynews.domain.models import RunReport

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_collect_help_is_chinese(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["collect", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "用法：" in output
    assert "收集" in output
    assert "--verification-model" in output
    assert "--verification-batch-size" in output


@pytest.mark.parametrize(
    "arguments",
    [["--help"], ["probe", "--help"], ["validate", "--help"], ["digest", "--help"]],
)
def test_global_and_probe_help_are_available(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "用法：" in output
    assert "选项：" in output


@pytest.mark.parametrize(
    "arguments, message",
    [
        (["unknown"], "无效选项"),
        (["collect", "--days"], "需要一个参数"),
    ],
)
def test_argparse_errors_are_chinese(
    arguments: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2
    error = capsys.readouterr().err
    assert message in error
    assert "invalid choice" not in error
    assert "expected one argument" not in error


def test_days_request_uses_shanghai_day_boundary() -> None:
    request = build_collection_request(["--days", "7"], now=NOW)

    assert request.from_.isoformat() == "2026-07-26T12:00:00+08:00"
    assert request.to.isoformat() == "2026-08-02T12:00:00+08:00"
    assert request.timezone == "Asia/Shanghai"


def test_date_request_covers_one_local_calendar_day() -> None:
    request = build_collection_request(["--date", "2026-08-01"], now=NOW)

    assert request.from_.isoformat() == "2026-08-01T00:00:00+08:00"
    assert request.to.isoformat() == "2026-08-02T00:00:00+08:00"


@pytest.mark.parametrize(
    "arguments, message",
    [
        (["--days", "0"], "--days 必须是正整数"),
        (["--date", "2026/08/01"], "--date 必须使用 YYYY-MM-DD"),
        (["--from", "2026-08-01"], "--from 与 --to 必须同时提供"),
        (["--from", "2026-08-02", "--to", "2026-08-01"], "开始时间必须早于结束时间"),
    ],
)
def test_invalid_date_arguments_are_reported_in_chinese(
    arguments: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_collection_request(arguments, now=NOW)

    assert raised.value.code == 2
    assert message in capsys.readouterr().err


def test_collect_script_exposes_help() -> None:
    result = __import__("subprocess").run(
        ["./scripts/collect.sh", "--help"], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    assert "用法：" in result.stdout


def test_validate_checks_run_report_schema_and_exports_the_same_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "run-report-v1.json"
    run_path = tmp_path / "run.json"
    schema_path = tmp_path / "run.schema.json"
    run_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    result = main(
        [
            "validate",
            "--run",
            str(run_path),
            "--schema-out",
            str(schema_path),
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "passed",
        "run": str(run_path),
        "schema_valid": True,
        "verified_count": 0,
        "evidence_count": 0,
        "evidence_checked": False,
        "errors": [],
    }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema == RunReport.model_json_schema()


def test_validate_rejects_unknown_schema_major(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "run-report-v1.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0"
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(payload), encoding="utf-8")

    result = main(["validate", "--run", str(run_path)])

    assert result == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed"
    assert output["schema_valid"] is False
    assert output["errors"]


def test_report_command_writes_chinese_markdown_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "run-report-v1.json"
    output = tmp_path / "report.md"

    result = main(["report", "--run", str(fixture), "--out", str(output)])

    assert result == 0
    assert "报告已写入" in capsys.readouterr().out
    text = output.read_text(encoding="utf-8")
    assert "## 已核验" in text
    assert "## 待核验" in text
    assert "## 价格变化" in text
    assert "## 来源状态" in text


def test_digest_command_writes_atomic_outputs_without_codex(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "run-report-v1.json"

    result = main(
        [
            "digest",
            "--run",
            str(fixture),
            "--out-dir",
            str(tmp_path),
            "--max-items",
            "5",
            "--summary-model",
            "offline-test",
            "--summary-timeout",
            "1",
            "--no-codex",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "complete"
    assert (tmp_path / "digest-latest.json").is_file()
    assert (tmp_path / "digest-latest.md").is_file()
    assert list((tmp_path / "digests").glob("*.json"))
