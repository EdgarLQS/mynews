from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mynews.cli import build_collection_request, main

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_collect_help_is_chinese(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["collect", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "用法：" in output
    assert "收集" in output


@pytest.mark.parametrize("arguments", [["--help"], ["probe", "--help"]])
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
