"""从 RunReport 离线生成中文 Markdown 报告。"""

from __future__ import annotations

from pathlib import Path

from mynews.application.editorial_io import atomic_write_text
from mynews.application.output_safety import ensure_safe_output
from mynews.domain.models import NewsItem, RunReport, SourceResult


def render_report(report: RunReport) -> str:
    ensure_safe_output(
        report.model_dump(mode="json", by_alias=True),
        root="report",
    )
    stats = report.verification_stats
    lines = [
        "# mynews 信息报告",
        "",
        f"- 运行：`{report.run_id}`",
        f"- 状态：`{report.status}`",
        "- 核验统计："
        f"尝试 {stats.attempted}，重试 {stats.retried}，"
        f"待核验 {stats.pending}，过期 {stats.expired}",
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
    lines.extend(_evidence_review_section(report))
    lines.extend(_source_section(report.sources))
    return "\n".join(lines).rstrip() + "\n"


def write_report(report: RunReport, path: Path) -> None:
    text = render_report(report)
    atomic_write_text(path, text)


def load_report(path: Path) -> RunReport:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as error:
        raise OSError("无法读取 RunReport 文件") from error
    return RunReport.model_validate_json(payload)


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
            evidence = item.primary_evidence[0]
            lines.append(f"- 证据摘录：{evidence.excerpt}")
            if evidence.validation.lifecycle_status == "changed_supporting":
                lines.append("- 证据警告：`changed_supporting`")
        if item.verification_retry is not None:
            retry = item.verification_retry
            lines.append(
                "- 重试："
                f"`{retry.status}`，{retry.attempt_count}/{retry.max_attempts}；"
                f"原因：`{retry.last_reason}`"
            )
            if retry.terminal_reason is not None:
                lines.append(f"- 终止原因：`{retry.terminal_reason}`")
            if retry.next_retry_at is not None:
                lines.append(f"- 下次重试：{retry.next_retry_at.isoformat()}")
        lines.append("")
    return lines


def _evidence_review_section(report: RunReport) -> list[str]:
    lines = ["## 证据复核", ""]
    if not report.evidence_reviews:
        return lines + ["- 无", ""]
    for review in report.evidence_reviews:
        detail = f"；原因：`{review.reason}`" if review.reason else ""
        warning = f"；警告：`{review.warning}`" if review.warning else ""
        lines.append(
            f"- `{review.event_key}`：`{review.status}`；"
            f"{review.evidence_url}{detail}{warning}"
        )
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
