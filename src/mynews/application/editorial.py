"""只读聚合 Candidate、Digest、发布记录和反馈的周复盘。"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mynews.application.candidates import (
    read_candidate_payload,
    validate_candidate_payload,
)
from mynews.application.output_safety import OutputSafetyError, ensure_safe_output
from mynews.domain.editorial import (
    EditorialCodexStatus,
    EditorialEvent,
    EditorialFeedbackSummary,
    EditorialHint,
    EditorialInputSummary,
    EditorialReview,
    EditorialStats,
    EditorialSuggestion,
)
from mynews.domain.models import Digest, ReasoningEffort
from mynews.infrastructure.codex_process import (
    CodexProcessAdapter,
    CodexProcessError,
    CodexProcessRequest,
)
from mynews.storage.artifact_committer import ArtifactCommitter, ArtifactWrite

DEFAULT_EDITORIAL_MODEL = "gpt-5.6-luna"
DEFAULT_EDITORIAL_TIMEOUT = 30.0
_WEEK_PATTERN = re.compile(r"^(\d{4})-W(\d{2})$")
_FEEDBACK_START = re.compile(
    r"<!-- mynews:weekly-feedback:start week=(\d{4}-W\d{2}) platform=(.*?) -->"
)
_FEEDBACK_METRICS = {
    "reads": re.compile(r"^- 阅读：(\d+)$", re.MULTILINE),
    "favorites": re.compile(r"^- 收藏：(\d+)$", re.MULTILINE),
    "shares": re.compile(r"^- 转发：(\d+)$", re.MULTILINE),
    "new_followers": re.compile(r"^- 新增关注：(\d+)$", re.MULTILINE),
}


class EditorialReviewError(ValueError):
    """周复盘输入、Codex 建议或输出提交失败。"""


class EditorialSuggestionRunner(Protocol):
    """可替换的结构化编辑建议调用 seam。"""

    def run(
        self,
        prompt: str,
        *,
        model: str,
        timeout: float,
        reasoning_effort: ReasoningEffort,
    ) -> str: ...


class EditorialCodexSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    text: str = Field(min_length=1)
    references: list[str] = Field(min_length=1)


class EditorialCodexResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[EditorialCodexSuggestion] = Field(max_length=5)


class EditorialCodexRunnerError(RuntimeError):
    """Codex 建议调用失败；确定性统计仍可保留。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EditorialCodexValidationError(ValueError):
    """Codex JSON 结构有效但引用了本报告之外的内容。"""

    code = "unknown_codex_reference"


class CodexEditorialSuggestionRunner:
    """使用共享进程 Adapter 的只读编辑建议调用。"""

    def __init__(
        self,
        executable: str = "codex",
        *,
        adapter: CodexProcessAdapter | None = None,
    ) -> None:
        self._executable = executable
        self._adapter = adapter or CodexProcessAdapter()

    def run(
        self,
        prompt: str,
        *,
        model: str,
        timeout: float,
        reasoning_effort: ReasoningEffort,
    ) -> str:
        try:
            return self._adapter.run(
                CodexProcessRequest(
                    prompt=prompt,
                    model=model,
                    timeout=timeout,
                    reasoning_effort=reasoning_effort,
                    output_schema=EditorialCodexResponse.model_json_schema(),
                    executable=self._executable,
                    temp_prefix="mynews-editorial-codex-",
                )
            )
        except CodexProcessError as error:
            raise EditorialCodexRunnerError(error.code, str(error)) from error


@dataclass(frozen=True, slots=True)
class EditorialReviewConfig:
    """周复盘 Codex 配置；不改变确定性事实统计。"""

    use_codex: bool = True
    model: str = DEFAULT_EDITORIAL_MODEL
    timeout: float = DEFAULT_EDITORIAL_TIMEOUT
    reasoning_effort: ReasoningEffort = "medium"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("编辑建议模型不能为空")
        if self.timeout <= 0:
            raise ValueError("编辑建议超时必须是正数")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("编辑建议推理强度无效")


@dataclass(frozen=True, slots=True)
class _CandidateRecord:
    week: str
    event_key: str
    title: str
    source: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DigestRecord:
    week: str
    event_key: str
    title: str
    verified: bool
    lifecycle: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class _PublicationRecord:
    week: str
    event_id: str
    title: str


@dataclass(frozen=True, slots=True)
class _FeedbackRecord:
    week: str
    platform: str
    reads: int
    favorites: int
    shares: int
    new_followers: int


@dataclass(frozen=True, slots=True)
class _EditorialInputs:
    candidates: tuple[_CandidateRecord, ...]
    digests: tuple[_DigestRecord, ...]
    publications: tuple[_PublicationRecord, ...]
    feedback: tuple[_FeedbackRecord, ...]


def build_editorial_review(
    root: Path,
    week: str,
    *,
    config: EditorialReviewConfig | None = None,
    now: datetime | None = None,
    runner: EditorialSuggestionRunner | None = None,
) -> EditorialReview:
    """从本地历史构建周复盘，不写输入文件。"""

    clean_week = _validate_week(week)
    inputs = _load_inputs(root)
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise EditorialReviewError("编辑复盘生成时间必须包含时区")
    active_config = config or EditorialReviewConfig()
    summary = _input_summary(inputs, clean_week)
    feedback = _feedback_summary(inputs, clean_week)
    duplicate_topics = _duplicate_topics(inputs, clean_week)
    updates = _substantive_updates(inputs, clean_week)
    stats, layers = _build_layers(
        inputs, clean_week, len(duplicate_topics), len(updates)
    )
    deterministic = _deterministic_suggestions(duplicate_topics, updates)
    codex_status, codex_suggestions = _codex_suggestions(
        inputs,
        clean_week,
        summary,
        stats,
        feedback,
        duplicate_topics,
        updates,
        active_config,
        runner,
    )
    suggestions = _limit_suggestions((*deterministic, *codex_suggestions))
    status: Literal["complete", "partial"] = "complete"
    if summary.missing_requirements or codex_status.mode == "partial":
        status = "partial"
    return EditorialReview(
        week=clean_week,
        generated_at=generated_at,
        status=status,
        inputs=summary,
        feedback=feedback,
        stats=stats,
        published=layers[0],
        unpublished=layers[1],
        pending=layers[2],
        duplicate_topics=duplicate_topics,
        substantive_updates=updates,
        suggestions=suggestions,
        codex=codex_status,
    )


def write_editorial_review(
    review: EditorialReview,
    out_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    """原子提交周 JSON、Markdown 及其 latest 双格式。"""

    json_path = out_dir / f"{review.week}.json"
    markdown_path = out_dir / f"{review.week}.md"
    latest_json = out_dir / "latest.json"
    latest_markdown = out_dir / "latest.md"
    try:
        payload = review.model_dump(mode="json")
        ensure_safe_output(payload, root="editorial_review")
        markdown = render_editorial_review(review)
        ArtifactCommitter().commit(
            (
                ArtifactWrite.json(json_path, payload),
                ArtifactWrite.text(markdown_path, markdown),
                ArtifactWrite.json(latest_json, payload),
                ArtifactWrite.text(latest_markdown, markdown),
            )
        )
    except (OutputSafetyError, ValueError) as error:
        raise EditorialReviewError("编辑复盘输出不安全") from error
    except Exception as error:
        raise EditorialReviewError("编辑复盘输出提交失败") from error
    return json_path, markdown_path, latest_json, latest_markdown


def render_editorial_review(review: EditorialReview) -> str:
    """渲染不含原始 URL、绝对路径或秘密的中文周复盘。"""

    try:
        ensure_safe_output(review.model_dump(mode="json"), root="editorial_review")
    except OutputSafetyError as error:
        raise EditorialReviewError("编辑复盘输出不安全") from error
    lines = [
        "# mynews 周复盘",
        "",
        f"- 周：`{review.week}`",
        f"- 状态：`{review.status}`",
        f"- 生成时间：`{review.generated_at.isoformat()}`",
        "",
        "## 输入门槛",
        "",
        f"- 完整 ISO 周：`{review.inputs.complete_iso_week_count}`",
        f"- 发布记录：`{review.inputs.publication_count}`",
        f"- 反馈记录：`{review.inputs.feedback_count}`",
        f"- 缺失：{_items(review.inputs.missing_requirements)}",
        "",
        "## 反馈汇总",
        "",
        (
            f"- 周：`{_items(review.feedback.weeks)}`；"
            f"平台：`{_items(review.feedback.platforms)}`"
        ),
        (
            f"- 阅读：`{review.feedback.reads}`；收藏：`{review.feedback.favorites}`；"
            f"转发：`{review.feedback.shares}`；新增关注：`{review.feedback.new_followers}`"
        ),
        "",
        "## 确定性统计",
        "",
    ]
    lines.extend(_render_stats(review.stats))
    lines.extend(_render_events("已发布", review.published))
    lines.extend(_render_events("未发布", review.unpublished))
    lines.extend(_render_events("待核查", review.pending))
    lines.extend(_render_hints("重复选题提示", review.duplicate_topics))
    lines.extend(_render_hints("实质更新提示", review.substantive_updates))
    lines.extend(_render_suggestions(review))
    return "\n".join(lines).rstrip() + "\n"


def _load_inputs(root: Path) -> _EditorialInputs:
    return _EditorialInputs(
        candidates=_load_candidates(root),
        digests=_load_digests(root),
        publications=_load_publications(root),
        feedback=_load_feedback(root),
    )


def _load_candidates(root: Path) -> tuple[_CandidateRecord, ...]:
    result: list[_CandidateRecord] = []
    paths = sorted((root / "output/editorial").glob("*/candidates.json"))
    for path in paths:
        try:
            payload = read_candidate_payload(path)
            issues = validate_candidate_payload(payload)
            if issues:
                raise ValueError("Candidate Contract 校验失败")
            week = _week_from_date(str(payload["date"]))
            for item in payload["candidates"]:
                if not isinstance(item, Mapping):
                    raise ValueError("Candidate 条目必须是对象")
                event_key = str(
                    item.get("duplicateGroupId")
                    or item.get("candidateRef")
                    or item.get("id")
                    or ""
                )
                if not event_key or not item.get("title"):
                    raise ValueError("Candidate 缺少事件或标题")
                aliases = tuple(
                    dict.fromkeys(
                        str(value)
                        for value in (
                            event_key,
                            item.get("candidateRef"),
                            item.get("id"),
                        )
                        if value
                    )
                )
                result.append(
                    _CandidateRecord(
                        week=week,
                        event_key=event_key,
                        title=str(item["title"]),
                        source=str(item.get("source") or "candidate"),
                        aliases=aliases,
                    )
                )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise EditorialReviewError("Candidate 输入无效") from error
    return tuple(result)


def _load_digests(root: Path) -> tuple[_DigestRecord, ...]:
    paths = sorted((root / "output/digests").glob("*.json"))
    latest = root / "output/digest-latest.json"
    if latest.exists():
        paths.append(latest)
    result: list[_DigestRecord] = []
    seen: set[str] = set()
    for path in paths:
        try:
            digest = Digest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, ValidationError) as error:
            raise EditorialReviewError("Digest 输入无效") from error
        if digest.digest_id in seen:
            continue
        seen.add(digest.digest_id)
        week = _week_from_datetime(digest.generated_at)
        result.extend(
            _DigestRecord(
                week=week,
                event_key=item.event_key,
                title=item.title_zh,
                verified=item.verification_status == "verified",
                lifecycle=item.lifecycle,
                content_hash=item.source_content_hash,
            )
            for item in digest.all_items
        )
    return tuple(result)


def _load_publications(root: Path) -> tuple[_PublicationRecord, ...]:
    path = root / "output/editorial/publication-ledger.csv"
    if not path.exists():
        return ()
    result: list[_PublicationRecord] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"date", "event_id", "title"}
            if not required.issubset(set(reader.fieldnames or ())):
                raise ValueError("publication ledger 缺少必要列")
            for row in reader:
                business_date = date.fromisoformat(str(row.get("date", "")))
                event_id = str(row.get("event_id", "")).strip()
                if not event_id:
                    raise ValueError("publication ledger 缺少 event_id")
                result.append(
                    _PublicationRecord(
                        week=_week_from_date(business_date.isoformat()),
                        event_id=event_id,
                        title=str(row.get("title", "")),
                    )
                )
    except (OSError, TypeError, ValueError, csv.Error, UnicodeError) as error:
        raise EditorialReviewError("publication ledger 输入无效") from error
    return tuple(result)


def _load_feedback(root: Path) -> tuple[_FeedbackRecord, ...]:
    path = root / "output/editorial/weekly-feedback.md"
    if not path.exists():
        return ()
    try:
        content = path.read_text(encoding="utf-8")
        result: list[_FeedbackRecord] = []
        for match in _FEEDBACK_START.finditer(content):
            week, platform = match.groups()
            end_marker = (
                f"<!-- mynews:weekly-feedback:end week={week} platform={platform} -->"
            )
            end = content.find(end_marker, match.end())
            if end < 0:
                raise ValueError("weekly feedback 结束标记缺失")
            block = content[match.end() : end]
            metric_values: dict[str, int] = {}
            for name, pattern in _FEEDBACK_METRICS.items():
                metric = pattern.search(block)
                if metric is None:
                    raise ValueError("weekly feedback 指标缺失")
                metric_values[name] = int(metric.group(1))
            if not platform.strip():
                raise ValueError("weekly feedback 指标缺失")
            result.append(
                _FeedbackRecord(
                    week=week,
                    platform=platform.strip(),
                    reads=metric_values["reads"],
                    favorites=metric_values["favorites"],
                    shares=metric_values["shares"],
                    new_followers=metric_values["new_followers"],
                )
            )
        return tuple(result)
    except (OSError, TypeError, ValueError, UnicodeError) as error:
        raise EditorialReviewError("weekly feedback 输入无效") from error


def _input_summary(inputs: _EditorialInputs, target_week: str) -> EditorialInputSummary:
    candidate_weeks = {
        item.week for item in inputs.candidates if item.week <= target_week
    }
    digest_weeks = {item.week for item in inputs.digests if item.week <= target_week}
    feedback_weeks = {
        item.week for item in inputs.feedback if item.week <= target_week
    }
    feedback_records = [
        item for item in inputs.feedback if item.week <= target_week
    ]
    complete = candidate_weeks & digest_weeks & feedback_weeks
    available = sorted(candidate_weeks | digest_weeks | feedback_weeks)
    missing: list[str] = []
    if target_week not in candidate_weeks:
        missing.append("target_candidates")
    if target_week not in digest_weeks:
        missing.append("target_digest")
    if len(complete) < 4:
        missing.append("four_complete_iso_weeks")
    publications = [item for item in inputs.publications if item.week <= target_week]
    if len(publications) < 10:
        missing.append("ten_publications")
    publication_weeks = {item.week for item in publications}
    if not feedback_weeks or not publication_weeks.issubset(feedback_weeks):
        missing.append("publication_feedback")
    return EditorialInputSummary(
        candidate_batch_count=len(candidate_weeks),
        digest_count=len(digest_weeks),
        publication_count=len(publications),
        feedback_count=len(feedback_records),
        complete_iso_week_count=len(complete),
        available_iso_weeks=available,
        missing_requirements=sorted(set(missing)),
    )


def _feedback_summary(
    inputs: _EditorialInputs, target_week: str
) -> EditorialFeedbackSummary:
    records = [item for item in inputs.feedback if item.week <= target_week]
    return EditorialFeedbackSummary(
        record_count=len(records),
        weeks=sorted({item.week for item in records}),
        platforms=sorted({item.platform for item in records}),
        reads=sum(item.reads for item in records),
        favorites=sum(item.favorites for item in records),
        shares=sum(item.shares for item in records),
        new_followers=sum(item.new_followers for item in records),
    )


def _build_layers(
    inputs: _EditorialInputs,
    target_week: str,
    duplicate_topic_count: int,
    substantive_update_count: int,
) -> tuple[
    EditorialStats,
    tuple[list[EditorialEvent], list[EditorialEvent], list[EditorialEvent]],
]:
    candidates = [item for item in inputs.candidates if item.week == target_week]
    digests = [item for item in inputs.digests if item.week == target_week]
    candidate_by_key = _first_candidate_by_key(candidates)
    digest_by_key = _first_digest_by_key(digests)
    published_ids = {
        item.event_id
        for item in inputs.publications
        if item.week == target_week
    }
    pending_keys = {item.event_key for item in digests if not item.verified}
    keys = sorted(digest_by_key)
    layers: dict[str, list[EditorialEvent]] = {
        "published": [],
        "unpublished": [],
        "pending": [],
    }
    for event_key in keys:
        candidate = candidate_by_key.get(event_key)
        references = set(candidate.aliases if candidate else (event_key,))
        is_published = bool(references & published_ids)
        layer = (
            "pending"
            if event_key in pending_keys
            else "published"
            if is_published
            else "unpublished"
        )
        event = EditorialEvent(
            event_key=event_key,
            title=digest_by_key[event_key].title,
            source=candidate.source if candidate else "digest",
            layer=layer,  # type: ignore[arg-type]
        )
        layers[layer].append(event)
    stats = EditorialStats(
        candidate_count=len(candidates),
        digest_item_count=len(digests),
        published_count=len(layers["published"]),
        unpublished_count=len(layers["unpublished"]),
        pending_count=len(layers["pending"]),
        publication_record_count=len(
            [item for item in inputs.publications if item.week == target_week]
        ),
        feedback_record_count=len(
            [item for item in inputs.feedback if item.week == target_week]
        ),
        duplicate_topic_count=duplicate_topic_count,
        substantive_update_count=substantive_update_count,
    )
    return stats, (layers["published"], layers["unpublished"], layers["pending"])


def _duplicate_topics(
    inputs: _EditorialInputs,
    target_week: str,
) -> list[EditorialHint]:
    records = [item for item in inputs.candidates if item.week == target_week]
    by_topic: dict[str, list[_CandidateRecord]] = defaultdict(list)
    for item in records:
        by_topic[_topic_key(item.title)].append(item)
    hints: list[EditorialHint] = []
    for records_for_topic in by_topic.values():
        keys = sorted({item.event_key for item in records_for_topic})
        if len(records_for_topic) < 2 or not keys:
            continue
        title = sorted(item.title for item in records_for_topic)[0]
        hints.append(
            EditorialHint(
                kind="duplicate_topic",
                title=title,
                detail=f"本周观察到 {len(records_for_topic)} 条相似候选",
                references=keys,
            )
        )
    return sorted(hints, key=lambda item: (item.title.casefold(), item.references))


def _substantive_updates(
    inputs: _EditorialInputs,
    target_week: str,
) -> list[EditorialHint]:
    current: dict[str, list[_DigestRecord]] = defaultdict(list)
    previous: dict[str, list[_DigestRecord]] = defaultdict(list)
    for item in inputs.digests:
        if item.week == target_week:
            current[item.event_key].append(item)
        elif item.week < target_week:
            previous[item.event_key].append(item)
    hints: list[EditorialHint] = []
    for event_key, records in current.items():
        updated = [item for item in records if item.lifecycle == "updated"]
        if not updated:
            continue
        latest = sorted(updated, key=lambda item: item.title.casefold())[0]
        prior_hashes = {item.content_hash for item in previous.get(event_key, ())}
        detail = "本周出现实质更新"
        if prior_hashes and latest.content_hash not in prior_hashes:
            detail += "，证据内容哈希发生变化"
        hints.append(
            EditorialHint(
                kind="substantive_update",
                title=latest.title,
                detail=detail,
                references=[event_key],
            )
        )
    return sorted(hints, key=lambda item: item.references)


def _deterministic_suggestions(
    duplicate_topics: Sequence[EditorialHint],
    updates: Sequence[EditorialHint],
) -> list[EditorialSuggestion]:
    result = [
        EditorialSuggestion(
            kind="duplicate_topic",
            text=f"检查重复选题：{hint.title}",
            references=hint.references,
        )
        for hint in duplicate_topics
    ]
    result.extend(
        EditorialSuggestion(
            kind="substantive_update",
            text=f"复核实质更新：{hint.title}",
            references=hint.references,
        )
        for hint in updates
    )
    return result


def _codex_suggestions(
    inputs: _EditorialInputs,
    week: str,
    summary: EditorialInputSummary,
    stats: EditorialStats,
    feedback: EditorialFeedbackSummary,
    duplicate_topics: Sequence[EditorialHint],
    updates: Sequence[EditorialHint],
    config: EditorialReviewConfig,
    runner: EditorialSuggestionRunner | None,
) -> tuple[EditorialCodexStatus, list[EditorialSuggestion]]:
    if not config.use_codex:
        return EditorialCodexStatus(mode="disabled", accepted_count=0), []
    if summary.missing_requirements:
        return EditorialCodexStatus(mode="skipped_incomplete", accepted_count=0), []
    active_runner = runner or CodexEditorialSuggestionRunner()
    allowed = _allowed_references(inputs, week, stats)
    try:
        response = EditorialCodexResponse.model_validate_json(
            active_runner.run(
                _editorial_prompt(
                    week,
                    summary,
                    feedback,
                    stats,
                    duplicate_topics,
                    updates,
                ),
                model=config.model,
                timeout=config.timeout,
                reasoning_effort=config.reasoning_effort,
            )
        )
        suggestions = [
            _convert_codex_suggestion(item, allowed) for item in response.suggestions
        ]
    except EditorialCodexRunnerError as error:
        return EditorialCodexStatus(
            mode="partial", accepted_count=0, error=error.code
        ), []
    except EditorialCodexValidationError as error:
        return EditorialCodexStatus(
            mode="partial", accepted_count=0, error=error.code
        ), []
    except (ValidationError, ValueError, TypeError):
        return EditorialCodexStatus(
            mode="partial", accepted_count=0, error="invalid_codex_json"
        ), []
    except Exception:
        return EditorialCodexStatus(
            mode="partial", accepted_count=0, error="codex_failed"
        ), []
    return (
        EditorialCodexStatus(mode="used", accepted_count=len(suggestions)),
        suggestions,
    )


def _convert_codex_suggestion(
    suggestion: EditorialCodexSuggestion,
    allowed: set[str],
) -> EditorialSuggestion:
    if suggestion.kind not in {"trend", "model_suggestion"}:
        raise ValueError("未知 Codex 建议类型")
    references = sorted(set(suggestion.references))
    if not references or not set(references).issubset(allowed):
        raise EditorialCodexValidationError("Codex 建议引用了未知事件或指标")
    return EditorialSuggestion(
        kind=suggestion.kind,  # type: ignore[arg-type]
        text=suggestion.text,
        references=references,
    )


def _allowed_references(
    inputs: _EditorialInputs,
    week: str,
    stats: EditorialStats,
) -> set[str]:
    references = {
        item.event_key for item in inputs.candidates if item.week == week
    }
    references.update(item.event_key for item in inputs.digests if item.week == week)
    references.update(
        {
            "metric:candidate_count",
            "metric:digest_item_count",
            "metric:published_count",
            "metric:unpublished_count",
            "metric:pending_count",
            "metric:publication_record_count",
            "metric:feedback_record_count",
        }
    )
    del stats
    return references


def _editorial_prompt(
    week: str,
    summary: EditorialInputSummary,
    feedback: EditorialFeedbackSummary,
    stats: EditorialStats,
    duplicate_topics: Sequence[EditorialHint],
    updates: Sequence[EditorialHint],
) -> str:
    payload = {
        "week": week,
        "input_summary": summary.model_dump(mode="json"),
        "feedback": feedback.model_dump(mode="json"),
        "stats": stats.model_dump(mode="json"),
        "deterministic_hints": [
            item.model_dump(mode="json") for item in (*duplicate_topics, *updates)
        ],
    }
    return (
        "你是只读编辑建议器。只能根据下列已保存统计和可解析引用提出最多五条建议；"
        "不得新增事实、事件引用或 URL。只返回符合 Schema 的 JSON。\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _limit_suggestions(
    suggestions: Sequence[EditorialSuggestion],
) -> list[EditorialSuggestion]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[EditorialSuggestion] = []
    for suggestion in suggestions:
        key = (suggestion.text, tuple(suggestion.references))
        if key in seen:
            continue
        seen.add(key)
        result.append(suggestion)
        if len(result) == 5:
            break
    return result


def _first_candidate_by_key(
    items: Sequence[_CandidateRecord],
) -> dict[str, _CandidateRecord]:
    result: dict[str, _CandidateRecord] = {}
    for item in sorted(
        items, key=lambda value: (value.event_key, value.title.casefold())
    ):
        result.setdefault(item.event_key, item)
    return result


def _first_digest_by_key(items: Sequence[_DigestRecord]) -> dict[str, _DigestRecord]:
    result: dict[str, _DigestRecord] = {}
    for item in sorted(
        items, key=lambda value: (value.event_key, value.title.casefold())
    ):
        result.setdefault(item.event_key, item)
    return result


def _week_from_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise EditorialReviewError("输入日期无效") from error
    return f"{parsed.isocalendar().year:04d}-W{parsed.isocalendar().week:02d}"


def _week_from_datetime(value: datetime) -> str:
    return _week_from_date(value.date().isoformat())


def _validate_week(value: str) -> str:
    match = _WEEK_PATTERN.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise EditorialReviewError("ISO 周必须使用 YYYY-Www 格式")
    try:
        date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    except ValueError as error:
        raise EditorialReviewError("ISO 周不是有效周") from error
    return value.strip()


def _topic_key(value: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold())


def _render_stats(stats: EditorialStats) -> list[str]:
    return [
        (
            f"- Candidate：`{stats.candidate_count}`；"
            f"Digest 条目：`{stats.digest_item_count}`"
        ),
        (
            f"- 已发布：`{stats.published_count}`；"
            f"未发布：`{stats.unpublished_count}`；"
            f"待核查：`{stats.pending_count}`"
        ),
        (
            f"- 本周发布记录：`{stats.publication_record_count}`；"
            f"反馈：`{stats.feedback_record_count}`"
        ),
        (
            f"- 重复选题：`{stats.duplicate_topic_count}`；"
            f"实质更新：`{stats.substantive_update_count}`"
        ),
        "",
    ]


def _render_events(title: str, events: Sequence[EditorialEvent]) -> list[str]:
    lines = [f"## {title}", ""]
    if not events:
        return lines + ["- 无", ""]
    return lines + [
        f"- `{event.event_key}`：{event.title}（来源：{event.source}）"
        for event in events
    ] + [""]


def _render_hints(title: str, hints: Sequence[EditorialHint]) -> list[str]:
    lines = [f"## {title}", ""]
    if not hints:
        return lines + ["- 无", ""]
    for hint in hints:
        lines.append(f"- {hint.title}：{hint.detail}；引用：{_items(hint.references)}")
    return lines + [""]


def _render_suggestions(review: EditorialReview) -> list[str]:
    lines = ["## 建议", ""]
    if not review.suggestions:
        lines.append("- 无")
    else:
        lines.extend(
            f"- {item.text}；引用：{_items(item.references)}"
            for item in review.suggestions
        )
    lines.extend(
        [
            "",
            "## Codex 状态",
            "",
            f"- 模式：`{review.codex.mode}`；接受建议：`{review.codex.accepted_count}`",
        ]
    )
    if review.codex.error:
        lines.append(f"- 错误：`{review.codex.error}`")
    return lines + [""]


def _items(items: Sequence[str]) -> str:
    return "、".join(f"`{item}`" for item in items) if items else "无"


__all__ = [
    "CodexEditorialSuggestionRunner",
    "EditorialCodexResponse",
    "EditorialReviewConfig",
    "EditorialReviewError",
    "EditorialSuggestionRunner",
    "build_editorial_review",
    "render_editorial_review",
    "write_editorial_review",
]
