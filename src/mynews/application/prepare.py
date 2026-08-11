"""生成不调用 Codex、不自动发布的确定性 editorial candidate pack。"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mynews.application.candidates import (
    build_candidate_payload,
    read_candidate_payload,
    validate_candidate_payload,
)
from mynews.application.collector import SourceCollector
from mynews.application.output_safety import ensure_safe_output
from mynews.application.watchlist import load_watchlist
from mynews.domain.models import Candidate, CollectionRequest
from mynews.domain.normalization import normalize_url
from mynews.infrastructure.clock import Clock, SystemClock
from mynews.sources.newsfromai import DEFAULT_CONFIG_PATH, newsfromai_registry
from mynews.sources.protocol import SourceCollection, SourceHealth
from mynews.sources.registry import SourceRegistry as Registry

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class PrepareResult:
    status: str
    output_dir: Path
    candidate_count: int
    source_failures: int
    refreshed: bool


def prepare_editorial_pack(
    business_date: str,
    *,
    root: Path | str | None = None,
    refresh: bool = False,
    registry: Registry | None = None,
    config_path: Path | str | None = None,
    clock: Clock | None = None,
) -> PrepareResult:
    """Prepare or replay one business-date candidate pack."""
    parsed_date = _parse_date(business_date)
    root_path = Path(root) if root is not None else Path.cwd()
    active_clock = clock or SystemClock()
    output_dir = root_path / "output" / "editorial" / business_date
    candidate_path = output_dir / "candidates.json"
    state_dir = root_path / "state" / "editorial" / business_date
    collection_path = state_dir / "collection.json"
    if collection_path.is_file() and not refresh:
        collection = _load_collection(collection_path)
        refreshed = False
    elif candidate_path.is_file() and not refresh:
        payload = read_candidate_payload(candidate_path)
        if validate_candidate_payload(payload):
            raise ValueError("缓存候选契约无效")
        failure_count = _failure_count(state_dir / "failures.json")
        return PrepareResult(
            "partial" if failure_count else "complete",
            output_dir,
            len(payload["candidates"]),
            failure_count,
            False,
        )
    else:
        active_registry = registry or newsfromai_registry(
            config_path=config_path or _config_path(root_path)
        )
        collection = _collect(parsed_date, active_registry, active_clock)
        refreshed = True

    failures = _structured_failures(collection.health)
    if not collection.candidates and _all_sources_unavailable(collection.health):
        _write_failure_record(state_dir / "failures.json", failures)
        raise ValueError("所有自动来源均失败或受限，候选包未更新")

    observations = _load_observations(
        root_path / "state" / "editorial-observations.json"
    )
    if refreshed:
        _record_observations(observations, collection.candidates, active_clock.now())
    generated_at = datetime.combine(
        parsed_date, time(23, 59, 59), tzinfo=SHANGHAI
    ).astimezone(UTC)
    payload = build_candidate_payload(
        collection.candidates,
        business_date=business_date,
        generated_at=generated_at,
        observations=observations,
        database_matches=_database_matches(root_path / "output" / "runs"),
        publication_history=_publication_history(
            root_path / "output" / "editorial" / "publication-ledger.csv"
        ),
    )
    manual = _load_manual_watchlist(root_path)
    markdown = _render_markdown(payload, manual, failures)
    ensure_safe_output(payload, root="candidate")
    ensure_safe_output(manual, root="candidate.manual")
    ensure_safe_output(markdown, root="candidateMarkdown")
    writes: dict[Path, object] = {
        collection_path: _collection_json(collection),
        root_path / "state" / "editorial-observations.json": observations,
        state_dir / "failures.json": failures,
        candidate_path: payload,
        output_dir / "candidates.md": markdown,
    }
    feedback_path = root_path / "output" / "editorial" / "weekly-feedback.md"
    ledger_path = root_path / "output" / "editorial" / "publication-ledger.csv"
    if not feedback_path.exists():
        writes[feedback_path] = _feedback_template()
    if not ledger_path.exists():
        writes[ledger_path] = _ledger_template()
    _write_transaction(writes)
    status = "partial" if failures else "complete"
    return PrepareResult(
        status, output_dir, len(payload["candidates"]), len(failures), refreshed
    )


def _collect(
    business_date: date, registry: Registry, clock: Clock
) -> SourceCollection:
    start = datetime.combine(
        business_date - timedelta(days=7), time.min, tzinfo=SHANGHAI
    )
    end = datetime.combine(business_date + timedelta(days=1), time.min, tzinfo=SHANGHAI)
    request = CollectionRequest.model_validate(
        {
            "from": start,
            "to": end,
            "timezone": "Asia/Shanghai",
            "source_ids": list(registry.source_ids),
            "freshness_filter": True,
            "freshness_days": 2,
        }
    )
    return SourceCollector(registry, clock=clock).collect(
        request, registry.source_ids
    )


def _config_path(root: Path) -> Path:
    candidate = root / "config" / "newsfromai-feeds.json"
    return candidate if candidate.is_file() else DEFAULT_CONFIG_PATH


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("prepare 日期必须使用 YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError("prepare 日期必须使用 YYYY-MM-DD")
    return parsed


def _collection_json(collection: SourceCollection) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "candidates": [item.model_dump(mode="json") for item in collection.candidates],
        "health": [item.model_dump(mode="json") for item in collection.health],
    }


def _load_collection(path: Path) -> SourceCollection:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = tuple(
        Candidate.model_validate(item) for item in payload.get("candidates", [])
    )
    health = tuple(
        SourceHealth.model_validate(item) for item in payload.get("health", [])
    )
    return SourceCollection(candidates, health)


def _structured_failures(health: tuple[SourceHealth, ...]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for item in health:
        if item.health == "healthy":
            continue
        failures.append(
            {
                "sourceId": item.source_id,
                "status": item.health,
                "code": item.error.code if item.error else "source_unavailable",
                "message": item.error.message if item.error else "来源未返回健康状态",
            }
        )
    return failures


def _all_sources_unavailable(health: tuple[SourceHealth, ...]) -> bool:
    return bool(health) and all(item.health in {"failed", "blocked"} for item in health)


def _load_observations(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _record_observations(
    observations: dict[str, list[dict[str, str]]],
    candidates: tuple[Candidate, ...],
    observed_at: datetime,
) -> None:
    stamp = (
        observed_at.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    run_id = f"prepare-{stamp}"
    for candidate in candidates:
        key = normalize_url(str(candidate.url))
        rows = observations.setdefault(key, [])
        rows.append(
            {"observedAt": stamp, "runId": run_id, "sourceId": str(candidate.source_id)}
        )
        del rows[:-100]


def _database_matches(runs_dir: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    ambiguous: set[str] = set()
    if not runs_dir.is_dir():
        return found
    for path in sorted(runs_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            raw_url = item.get("canonical_url") or item.get("url")
            if not raw_url:
                continue
            try:
                key = normalize_url(str(raw_url))
            except ValueError:
                continue
            item_id = str(item.get("id") or item.get("event_key") or "")
            if not item_id:
                continue
            if key in found and found[key] != item_id:
                ambiguous.add(key)
            else:
                found[key] = item_id
    for key in ambiguous:
        found.pop(key, None)
    return found


def _load_manual_watchlist(root: Path) -> list[dict[str, str]]:
    path = root / "config" / "manual-watchlist.json"
    if not path.is_file():
        return []
    return [item.model_dump(mode="json") for item in load_watchlist(path)]


def _publication_history(path: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    if not path.is_file():
        return result
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            event_id = str(row.get("event_id") or "").strip()
            values = {
                "date": str(row.get("date") or ""),
                "platform": str(row.get("platform") or ""),
                "url": str(row.get("url") or ""),
                "publishedAt": str(row.get("published_at") or ""),
            }
            if event_id and all(values.values()):
                result.setdefault(event_id, []).append(values)
                result[event_id] = result[event_id][-50:]
    return result


def _render_markdown(
    payload: dict[str, Any],
    manual: list[dict[str, str]],
    failures: list[dict[str, str]],
) -> str:
    lines = [
        f"# {payload['date']} AI 资讯候选",
        "",
        "候选只用于人工编辑；`verified` 仍必须经过 mynews 第一方证据核验。",
        "",
        "## 统计",
        "",
        f"- 候选：{payload['stats']['candidateCount']}",
        (
            f"- 主库匹配：{payload['stats']['databaseMatchedCount']}"
            f"（匹配率 {payload['stats']['matchRate']:.6f}）"
        ),
        "",
    ]
    lines += [
        "## 官方人工检查",
        "",
        "以下页面只做只读提示，不自动抓取、不自动发布：",
        "",
    ]
    for item in manual:
        lines.append(
            f"- [{item['name']}]({item['url']})（{item['role']}）：{item['note']}"
        )
    lines += ["", "## 候选", ""]
    for index, item in enumerate(payload["candidates"], start=1):
        lines += [
            f"### {index}. {item['title']}",
            "",
            f"- 来源：{item['source']}（{item['sourceRole']}）",
            f"- 原始链接：{item['url']}",
            f"- 事件：{item['duplicateGroupId']}",
            f"- 首次观察：{item['firstSeenAt']}（{item['firstSeenPrecision']}）",
            f"- 重复观察：{item['repeat_count']}",
            f"- 来源族：{', '.join(item['multiSources'])}",
        ]
        if item.get("publicationHistory"):
            lines += [
                "- 已有发布记录："
                f"{len(item['publicationHistory'])} 条（请人工判断是否重复选题）"
            ]
        if item.get("summaryOriginal"):
            lines += ["", item["summaryOriginal"]]
        lines.append("")
    if failures:
        lines += ["## 数据失败与限制", ""]
        lines += [
            f"- `{item['sourceId']}`：{item['status']} / "
            f"{item['code']}；{item['message']}"
            for item in failures
        ]
        lines.append("")
    lines += [
        "## 每周反馈提示",
        "",
        "请在 `output/editorial/weekly-feedback.md` 记录阅读、收藏、转发和典型反馈；"
        "该文件只提供人工台账提示，不参与候选事实或 verified 判定。",
        "",
    ]
    return "\n".join(lines)


def _failure_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("失败状态文件损坏") from error
    if not isinstance(payload, list):
        raise ValueError("失败状态文件必须是数组")
    return len(payload)


def _feedback_template() -> str:
    return (
        "# 每周反馈\n\n"
        "只读提示：由人工记录周期、阅读、收藏、转发、新增关注和典型读者反馈。"
        "不要把反馈写回候选事实或 verified 状态。\n"
    )


def _ledger_template() -> str:
    return "date,event_id,title,platform,url,published_at\n"


def _write_failure_record(path: Path, failures: list[dict[str, str]]) -> None:
    _write_transaction({path: failures})


def _write_transaction(values: dict[Path, object]) -> None:
    previous = {path: path.read_bytes() if path.exists() else None for path in values}
    staged: dict[Path, str] = {}
    try:
        for path, value in values.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            )
            with handle:
                if isinstance(value, str):
                    handle.write(value)
                else:
                    json.dump(
                        value, handle, ensure_ascii=False, indent=2, sort_keys=True
                    )
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            staged[path] = handle.name
        for path, temporary in staged.items():
            os.replace(temporary, path)
    except Exception as error:
        for path, old in previous.items():
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise ValueError("editorial 输出失败，已恢复旧文件") from error
    finally:
        for temporary in staged.values():
            Path(temporary).unlink(missing_ok=True)


__all__ = ["PrepareResult", "prepare_editorial_pack"]
