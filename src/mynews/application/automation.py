"""分时情报报告与状态的原子提交契约。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from mynews.application.editorial_io import atomic_write_json, atomic_write_text
from mynews.application.output_safety import ensure_safe_output

AUTOMATION_SCHEMA_VERSION = 1
STATE_FIELDS = (
    "schemaVersion",
    "lastAttemptAt",
    "lastSuccessAt",
    "lastCompletedSlot",
    "lastReport",
    "reportedEvents",
)
EVENT_FIELDS = ("lastReportedAt", "contentHash", "reportPath")


def empty_automation_state() -> dict[str, Any]:
    """返回不包含运行秘密的初始任务状态。"""

    return {
        "schemaVersion": AUTOMATION_SCHEMA_VERSION,
        "lastAttemptAt": None,
        "lastSuccessAt": None,
        "lastCompletedSlot": None,
        "lastReport": None,
        "reportedEvents": {},
    }


def validate_automation_state(payload: Mapping[str, Any]) -> None:
    """校验状态字段、时间值以及报告路径边界。"""

    missing = [field for field in STATE_FIELDS if field not in payload]
    if missing:
        raise ValueError("automation 状态缺少必要字段")
    if payload["schemaVersion"] != AUTOMATION_SCHEMA_VERSION:
        raise ValueError("automation 状态 schemaVersion 无效")
    for field in ("lastAttemptAt", "lastSuccessAt"):
        _optional_datetime(payload[field], field)
    if payload["lastCompletedSlot"] is not None and not isinstance(
        payload["lastCompletedSlot"], str
    ):
        raise ValueError("lastCompletedSlot 必须是字符串或 null")
    _optional_relative_path(payload["lastReport"], "lastReport")
    reported = payload["reportedEvents"]
    if not isinstance(reported, Mapping):
        raise ValueError("reportedEvents 必须是对象")
    for event_key, event in reported.items():
        if not isinstance(event_key, str) or not event_key.strip():
            raise ValueError("reportedEvents 事件键无效")
        if not isinstance(event, Mapping) or set(event) != set(EVENT_FIELDS):
            raise ValueError("reportedEvents 条目字段无效")
        _optional_datetime(event["lastReportedAt"], "reportedEvents.lastReportedAt")
        for field in ("contentHash", "reportPath"):
            if not isinstance(event[field], str) or not event[field].strip():
                raise ValueError("reportedEvents 条目字段无效")
        _optional_relative_path(event["reportPath"], "reportedEvents.reportPath")


def commit_automation_output(
    report_path: Path,
    report_text: str,
    state_path: Path,
    state: Mapping[str, Any],
) -> None:
    """先提交报告，再提交状态；状态失败不会冒充成功档位。"""

    validate_automation_state(state)
    ensure_safe_output(report_text, root="automationReport")
    ensure_safe_output(state, root="automationState")
    atomic_write_text(report_path, report_text)
    atomic_write_json(state_path, dict(state))


def _optional_datetime(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是 ISO 时间或 null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} 不是有效 ISO 时间") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} 必须包含时区")


def _optional_relative_path(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是相对路径或 null")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} 必须是相对路径")


__all__ = [
    "AUTOMATION_SCHEMA_VERSION",
    "EVENT_FIELDS",
    "STATE_FIELDS",
    "commit_automation_output",
    "empty_automation_state",
    "validate_automation_state",
]
