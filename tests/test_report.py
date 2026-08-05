from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mynews.application.report import render_report, write_report
from mynews.domain.models import RunReport, SourceError, SourceResult


def report() -> RunReport:
    return RunReport(
        run_id="run-1",
        status="partial",
        requested_range={
            "from": "2026-08-01T00:00:00+00:00",
            "to": "2026-08-02T00:00:00+00:00",
            "verification_budget": 5,
        },
        started_at=datetime(2026, 8, 1, tzinfo=UTC),
        finished_at=datetime(2026, 8, 1, 0, 1, tzinfo=UTC),
        sources=[
            SourceResult(
                source_id="experimental-source",
                role="discovery",
                stability="experimental",
                health="blocked",
                fetched_count=0,
                accepted_count=0,
                duration_ms=1,
                error=SourceError(code="http_403", message="访问受限"),
            )
        ],
        items=[],
        stats={"filtered": 1, "verification_attempted": 0},
    )


def test_report_is_markdown_with_required_offline_sections() -> None:
    markdown = render_report(report())

    assert "## 已核验" in markdown
    assert "## 待核验" in markdown
    assert "## 价格变化" in markdown
    assert "## 来源状态" in markdown
    assert "experimental-source" in markdown
    assert "访问受限" in markdown


def test_report_writer_writes_only_rendered_run_facts(tmp_path: Path) -> None:
    path = tmp_path / "report.md"

    write_report(report(), path)

    text = path.read_text(encoding="utf-8")
    assert "run-1" in text
    assert "没有更多信息" not in text
