"""人工 weekly feedback 的稳定 Markdown 区块回填。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from mynews.application.editorial_io import atomic_write_text
from mynews.application.output_safety import ensure_safe_output

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


class FeedbackArgumentError(ValueError):
    """周反馈参数不满足契约。"""


@dataclass(frozen=True, slots=True)
class FeedbackResult:
    status: str
    path: Path


def record_weekly_feedback(
    *,
    week: str,
    platform: str,
    reads: int,
    favorites: int,
    shares: int,
    new_followers: int,
    note: str = "",
    output_path: Path,
    replace: bool = False,
) -> FeedbackResult:
    """新增或幂等更新一个周/平台反馈区块。"""

    clean_week = _week(week)
    clean_platform = _text(platform, "平台")
    clean_note = _note(note)
    _nonnegative_metrics(reads, favorites, shares, new_followers)
    block = render_feedback_block(
        clean_week,
        clean_platform,
        reads,
        favorites,
        shares,
        new_followers,
        clean_note,
    )
    ensure_safe_output(
        {
            "week": clean_week,
            "platform": clean_platform,
            "reads": reads,
            "favorites": favorites,
            "shares": shares,
            "new_followers": new_followers,
            "note": clean_note,
        },
        root="weeklyFeedback",
    )
    content = (
        output_path.read_text(encoding="utf-8")
        if output_path.exists()
        else _header()
    )
    start, end = _markers(clean_week, clean_platform)
    updated, status = _upsert_block(content, block, start, end, replace)
    if status == "unchanged":
        return FeedbackResult(status, output_path)
    ensure_safe_output(updated, root="weeklyFeedbackMarkdown")
    atomic_write_text(output_path, updated)
    return FeedbackResult("created", output_path)


def render_feedback_block(
    week: str,
    platform: str,
    reads: int,
    favorites: int,
    shares: int,
    new_followers: int,
    note: str,
) -> str:
    """渲染带稳定起止标记的周反馈区块。"""

    start, end = _markers(week, platform)
    lines = [
        start,
        f"### {week} · {platform}",
        "",
        f"- 阅读：{reads}",
        f"- 收藏：{favorites}",
        f"- 转发：{shares}",
        f"- 新增关注：{new_followers}",
    ]
    if note:
        lines.append(f"- 典型反馈：{note}")
    lines.extend([end, ""])
    return "\n".join(lines)


def _week(value: str) -> str:
    match = _WEEK_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise FeedbackArgumentError("ISO 周必须使用 YYYY-Www 格式")
    year, week = int(match.group(1)), int(match.group(2))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError as error:
        raise FeedbackArgumentError("ISO 周不是有效周") from error
    return f"{year:04d}-W{week:02d}"


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeedbackArgumentError(f"{field}不能为空")
    cleaned = value.strip()
    if any(token in cleaned for token in ("\n", "\r", "<!--", "-->")):
        raise FeedbackArgumentError(f"{field}包含非法标记")
    return cleaned


def _note(value: str) -> str:
    if not isinstance(value, str):
        raise FeedbackArgumentError("反馈文本必须是单行文本")
    if any(token in value for token in ("\n", "\r", "<!--", "-->")):
        raise FeedbackArgumentError(
            "反馈文本必须是单行文本且不能包含 Markdown 注释标记"
        )
    return value.strip()


def _nonnegative_metrics(*values: int) -> None:
    invalid = any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in values
    )
    if invalid:
        raise FeedbackArgumentError("阅读、收藏、转发和新增关注数必须是非负整数")


def _markers(week: str, platform: str) -> tuple[str, str]:
    marker = f"week={week} platform={platform}"
    return (
        f"<!-- mynews:weekly-feedback:start {marker} -->",
        f"<!-- mynews:weekly-feedback:end {marker} -->",
    )


def _header() -> str:
    return (
        "# 每周反馈\n\n"
        "只读提示：由人工记录周期、阅读、收藏、转发、新增关注和典型读者反馈。"
        "不要把反馈写回候选事实或 verified 状态。\n\n"
    )


def _upsert_block(
    content: str,
    block: str,
    start_marker: str,
    end_marker: str,
    replace: bool,
) -> tuple[str, str]:
    starts = [match.start() for match in re.finditer(re.escape(start_marker), content)]
    ends = [match.start() for match in re.finditer(re.escape(end_marker), content)]
    if not starts and not ends:
        return content.rstrip() + "\n\n" + block, "created"
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise ValueError("weekly feedback 稳定区块标记损坏")
    block_end = ends[0] + len(end_marker)
    existing = content[starts[0] : block_end].rstrip() + "\n"
    if existing == block:
        return content, "unchanged"
    if not replace:
        raise ValueError("同周同平台反馈已存在且内容冲突；请使用 --replace")
    return content[: starts[0]] + block + content[block_end:].lstrip("\n"), "replaced"


__all__ = [
    "FeedbackArgumentError",
    "FeedbackResult",
    "record_weekly_feedback",
    "render_feedback_block",
]
