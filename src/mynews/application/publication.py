"""人工确认后的 publication ledger 回填。"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from mynews.application.candidates import (
    read_candidate_payload,
    validate_candidate_payload,
)
from mynews.application.editorial_io import atomic_write_text
from mynews.application.output_safety import ensure_safe_output
from mynews.domain.normalization import normalize_url

SHANGHAI = ZoneInfo("Asia/Shanghai")
LEDGER_FIELDS = ("date", "event_id", "title", "platform", "url", "published_at")


class PublicationArgumentError(ValueError):
    """发布记录参数不满足人工回填契约。"""


@dataclass(frozen=True, slots=True)
class PublicationResult:
    status: str
    path: Path
    event_count: int


def add_publication(
    candidate_path: Path,
    event_ids: list[str] | tuple[str, ...],
    *,
    title: str,
    platform: str,
    url: str,
    published_at: str,
    output_path: Path,
) -> PublicationResult:
    """校验 Candidate 后，将一篇内容对应的事件写入 CSV。"""

    clean_ids = _unique_event_ids(event_ids)
    clean_title = _required_text(title, "标题")
    clean_platform = _required_text(platform, "平台")
    clean_url = _public_https_url(url)
    published = _aware_datetime(published_at)
    payload = _load_candidates(candidate_path)
    matched = _match_events(payload["candidates"], clean_ids)
    rows, fields = _read_ledger(output_path)
    new_rows = _new_rows(
        matched,
        title=clean_title,
        platform=clean_platform,
        url=clean_url,
        published_at=published,
        existing=rows,
    )
    if not new_rows:
        return PublicationResult("unchanged", output_path, len(matched))
    rows.extend(new_rows)
    content = _render_csv(rows, fields)
    ensure_safe_output(rows, root="publicationLedger")
    ensure_safe_output(content, root="publicationLedgerMarkdown")
    atomic_write_text(output_path, content)
    return PublicationResult("created", output_path, len(new_rows))


def _load_candidates(path: Path) -> dict[str, Any]:
    try:
        payload = read_candidate_payload(path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("Candidate 文件读取或格式校验失败") from error
    issues = validate_candidate_payload(payload)
    if issues:
        raise ValueError("Candidate 文件契约校验失败")
    ensure_safe_output(payload, root="publicationCandidate")
    return payload


def _unique_event_ids(event_ids: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for event_id in event_ids:
        value = _required_text(event_id, "事件 ID")
        if value not in result:
            result.append(value)
    if not result:
        raise PublicationArgumentError("至少提供一个事件 ID")
    return result


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublicationArgumentError(f"{field}不能为空")
    cleaned = value.strip()
    if "\n" in cleaned or "\r" in cleaned:
        raise PublicationArgumentError(f"{field}不能包含换行")
    return cleaned


def _public_https_url(value: str) -> str:
    cleaned = _required_text(value, "公开链接")
    parsed = urlsplit(cleaned)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise PublicationArgumentError("公开链接必须是带主机名的 HTTPS URL")
    if parsed.username or parsed.password:
        raise PublicationArgumentError("公开链接不能包含用户名或密码")
    try:
        normalize_url(cleaned)
    except ValueError as error:
        raise PublicationArgumentError("公开链接不是有效 URL") from error
    return cleaned


def _aware_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PublicationArgumentError("发布时间不能为空")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise PublicationArgumentError(
            "发布时间必须是带时区的 ISO 8601 时间"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PublicationArgumentError("发布时间必须包含时区")
    return parsed


def _match_events(
    candidates: list[dict[str, Any]], event_ids: list[str]
) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    for event_id in event_ids:
        primary = [
            item for item in candidates if item.get("duplicateGroupId") == event_id
        ]
        fallback = [
            item
            for item in candidates
            if not item.get("duplicateGroupId")
            and (item.get("candidateRef") == event_id or item.get("id") == event_id)
        ]
        matches = primary or fallback
        if not matches:
            raise PublicationArgumentError("事件 ID 与 Candidate 不匹配")
        result.extend((event_id, item) for item in matches)
    return result


def _read_ledger(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], list(LEDGER_FIELDS)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            if not set(LEDGER_FIELDS).issubset(fields):
                raise ValueError("publication ledger 缺少必要列")
            rows = [{key: value or "" for key, value in row.items()} for row in reader]
    except (OSError, csv.Error, UnicodeError) as error:
        raise ValueError("publication ledger 读取失败") from error
    for row in rows:
        if any(field not in row for field in LEDGER_FIELDS):
            raise ValueError("publication ledger 行格式无效")
    ensure_safe_output(rows, root="existingPublicationLedger")
    return rows, fields


def _new_rows(
    matched: list[tuple[str, dict[str, Any]]],
    *,
    title: str,
    platform: str,
    url: str,
    published_at: datetime,
    existing: list[dict[str, str]],
) -> list[dict[str, str]]:
    identity = {
        (
            row.get("event_id", ""),
            row.get("platform", ""),
            _identity_url(row.get("url", "")),
        )
        for row in existing
    }
    normalized_url = _identity_url(url)
    result: list[dict[str, str]] = []
    date_value = published_at.astimezone(SHANGHAI).date().isoformat()
    timestamp = published_at.isoformat()
    for event_id, _candidate in matched:
        key = (event_id, platform, normalized_url)
        if key in identity:
            continue
        result.append(
            {
                "date": date_value,
                "event_id": event_id,
                "title": title,
                "platform": platform,
                "url": url,
                "published_at": timestamp,
            }
        )
        identity.add(key)
    return result


def _identity_url(value: str) -> str:
    try:
        return normalize_url(value)
    except ValueError:
        return value.strip()


def _render_csv(rows: list[dict[str, str]], fields: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


__all__ = [
    "LEDGER_FIELDS",
    "PublicationArgumentError",
    "PublicationResult",
    "add_publication",
]
