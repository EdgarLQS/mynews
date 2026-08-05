"""从 RunReport 离线生成中文 Markdown 报告。"""

from __future__ import annotations

from pathlib import Path

from mynews.domain.models import NewsItem, RunReport, SourceResult


def render_report(report: RunReport) -> str:
    lines = [
        "# mynews 信息报告",
        "",
        f"- 运行：`{report.run_id}`",
        f"- 状态：`{report.status}`",
        "",
    ]
    lines.extend(_item_section("已核验", _items(report, "verified", False)))
    lines.extend(_item_section("待核验", _items(report, "unverified", False)))
    lines.extend(
        _item_section(
            "价格变化",
            [item for item in report.items if item.event_type == "pricing_change"],
        )
    )
    lines.extend(_source_section(report.sources))
    return "\n".join(lines).rstrip() + "\n"


def write_report(report: RunReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report), encoding="utf-8")


def load_report(path: Path) -> RunReport:
    return RunReport.model_validate_json(path.read_text(encoding="utf-8"))


def _items(report: RunReport, status: str, include_pricing: bool) -> list[NewsItem]:
    return [
        item
        for item in report.items
        if item.verification_status == status
        and (item.event_type == "pricing_change") == include_pricing
    ]


def _item_section(title: str, items: list[NewsItem]) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        return lines + ["- 无", ""]
    for item in items:
        lines.extend(
            [
                f"### {item.title_zh}",
                "",
                _limit_summary(item.summary_zh),
                "- 状态："
                f"`{item.verification_status}`；原因：`{item.verification_reason}`",
                "- 日期："
                f"{item.published_at.isoformat() if item.published_at else '未提供'}",
                f"- 链接：{item.canonical_url or '未提供'}",
            ]
        )
        if item.primary_evidence:
            lines.append(f"- 证据摘录：{item.primary_evidence[0].excerpt}")
        lines.append("")
    return lines


def _source_section(sources: list[SourceResult]) -> list[str]:
    lines = ["## 来源状态", ""]
    if not sources:
        return lines + ["- 无", ""]
    for source in sources:
        detail = ""
        if source.error is not None:
            detail = f"；错误：`{source.error.code}` {source.error.message}"
        lines.append(
            f"- `{source.source_id}`（{source.role}，{source.stability}）："
            f"`{source.health}`，抓取 {source.fetched_count}，"
            f"保留 {source.accepted_count}"
            f"{detail}"
        )
    lines.append("")
    return lines


def _limit_summary(value: str, limit: int = 500) -> str:
    return value if len(value) <= limit else value[:limit]
