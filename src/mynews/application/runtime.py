"""CLI 用例装配与执行的应用运行时。"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from mynews.application.collector import PipelineCollector, SourceCollector
from mynews.application.digest import DigestBuildConfig, DigestBuilder
from mynews.application.feedback import FeedbackArgumentError, record_weekly_feedback
from mynews.application.operations import (
    OperationsError,
    build_retention_plan,
    diagnose,
    recovery_check,
    write_operations_report,
)
from mynews.application.prepare import prepare_editorial_pack
from mynews.application.publication import PublicationArgumentError, add_publication
from mynews.application.quality import (
    QualityEvaluationError,
    QualityEvaluator,
    load_quality_suite,
    write_quality_evaluation,
)
from mynews.application.report import load_report, render_report, write_report
from mynews.application.validation import RunValidation, validate_run_file, write_schema
from mynews.application.watchlist import (
    load_watchlist,
    render_watchlist,
    write_watchlist,
)
from mynews.domain.models import CollectionRequest, ReasoningEffort
from mynews.infrastructure.clock import Clock, SystemClock
from mynews.sources.external import ExternalPluginLoader, PluginLoadReport
from mynews.sources.registry import SourceRegistry, default_registry
from mynews.storage.digest_store import DigestFileStore, DigestStoreError
from mynews.storage.json_store import JsonNewsStore, JsonStoreError
from mynews.storage.protocol import NewsStore
from mynews.verification.codex import CodexVerifier
from mynews.verification.protocol import VerificationConfig

SHANGHAI = ZoneInfo("Asia/Shanghai")
FEEDBACK_OUTPUT_PATH = Path("output/editorial/weekly-feedback.md")
PluginLoaderFactory = Callable[[], ExternalPluginLoader]


class ApplicationArgumentError(ValueError):
    """应用层参数错误，由 CLI 适配为中文 argparse 错误。"""


@dataclass(frozen=True, slots=True)
class Command:
    """不依赖 argparse 的 CLI 用例命令。"""

    name: str
    options: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", copy.deepcopy(dict(self.options)))


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """应用用例结果；CLI 只负责把它呈现给用户。"""

    exit_code: int
    payload: object | None = None
    text: str | None = None
    notice: str | None = None
    error: Exception | None = None
    error_prefix: str = ""
    error_suggestion: str = ""
    help_requested: bool = False


class ApplicationRuntime:
    """隐藏来源、Store、Verifier 和各命令用例的装配。"""

    def __init__(
        self,
        *,
        registry: SourceRegistry | None = None,
        store: NewsStore | None = None,
        clock: Clock | None = None,
        external_loader_factory: PluginLoaderFactory | None = None,
    ) -> None:
        self._registry = registry if registry is not None else default_registry()
        self._store = store
        self._clock = clock or SystemClock()
        self._external_loader_factory = external_loader_factory or ExternalPluginLoader
        self._registry_was_injected = registry is not None

    def run(self, command: Command) -> CommandOutcome:
        if command.name == "plugin":
            return self._run_plugin(command.options)
        if command.name == "publication":
            return self._run_publication(command.options)
        if command.name == "feedback":
            return self._run_feedback(command.options)
        if command.name == "evaluate":
            return self._run_evaluate(command.options)
        if command.name == "ops":
            return self._run_ops(command.options)
        active = self._prepare_registry(command.options)
        if isinstance(active, CommandOutcome):
            return active
        active_registry, plugin_ids = active
        if command.name == "prepare":
            return self._run_prepare(command.options)
        if command.name == "report":
            return self._run_report(command.options)
        if command.name == "watchlist":
            return self._run_watchlist(command.options)
        if command.name == "validate":
            return self._run_validate(command.options, active_registry)
        if command.name == "digest":
            return self._run_digest(command.options)
        if command.name == "collect":
            return self._run_collect(command.options, active_registry, plugin_ids)
        if command.name == "probe":
            return self._run_probe(command.options, active_registry, plugin_ids)
        return CommandOutcome(2, help_requested=True)

    def _run_plugin(self, options: Mapping[str, object]) -> CommandOutcome:
        command = _string_option(options, "plugin_command")
        if command == "list":
            list_payload = self._external_loader_factory().list_report()
            return CommandOutcome(
                0 if list_payload["status"] == "complete" else 1,
                list_payload,
            )
        if command != "probe":
            return CommandOutcome(2, help_requested=True)
        plugin_ids = _sequence_option(options, "plugin_ids")
        selected = self._load_plugins(plugin_ids, plugin_only=True)
        if isinstance(selected, CommandOutcome):
            return selected
        registry, loaded_ids, plugin_report = selected
        health = SourceCollector(registry, clock=self._clock).probe(loaded_ids)
        payload = json.loads(SourceCollector.probe_json(health))
        payload["plugins"] = [item.as_payload() for item in plugin_report.loaded]
        return CommandOutcome(SourceCollector.exit_code(health), payload)

    def _prepare_registry(
        self, options: Mapping[str, object]
    ) -> tuple[SourceRegistry, tuple[str, ...]] | CommandOutcome:
        plugin_ids = _sequence_option(options, "plugin_ids")
        with_plugin_ids = _sequence_option(options, "with_plugin_ids")
        if plugin_ids and with_plugin_ids:
            raise ApplicationArgumentError("--plugin 不能与 --with-plugin 混用")
        requested = plugin_ids or with_plugin_ids
        if not requested:
            return self._registry, ()
        selected = self._load_plugins(requested, plugin_only=bool(plugin_ids))
        if isinstance(selected, CommandOutcome):
            return selected
        registry, plugin_source_ids, _ = selected
        return registry, plugin_source_ids

    def _load_plugins(
        self, plugin_ids: Sequence[str], *, plugin_only: bool
    ) -> tuple[SourceRegistry, tuple[str, ...], PluginLoadReport] | CommandOutcome:
        base = self._registry
        report = self._external_loader_factory().load(
            plugin_ids,
            occupied_source_ids=() if plugin_only else base.source_ids,
        )
        if report.status == "failed":
            return CommandOutcome(1, report.as_payload())
        if plugin_only:
            registry = SourceRegistry(report.plugins, http=base.http)
        else:
            registry = base.with_plugins(report.plugins)
        loaded_ids = tuple(item.plugin.metadata.source_id for item in report.loaded)
        return registry, loaded_ids, report

    def _run_prepare(self, options: Mapping[str, object]) -> CommandOutcome:
        selected = _parse_local_date(_string_option(options, "date"), "--date")
        try:
            result = prepare_editorial_pack(
                selected.isoformat(),
                root=Path.cwd(),
                refresh=_bool_option(options, "refresh"),
            )
        except (OSError, ValueError) as error:
            return CommandOutcome(
                1,
                text=json.dumps(
                    {
                        "status": "failed",
                        "error": {"code": "prepare_error", "message": str(error)},
                    },
                    ensure_ascii=False,
                )
                + "\n",
            )
        payload = {
            "status": result.status,
            "outputDir": _relative_path(result.output_dir),
            "candidateCount": result.candidate_count,
            "sourceFailureCount": result.source_failures,
            "refreshed": result.refreshed,
        }
        return CommandOutcome(
            {"complete": 0, "partial": 3, "failed": 1}[result.status], payload
        )

    def _run_report(self, options: Mapping[str, object]) -> CommandOutcome:
        try:
            report = load_report(_path_option(options, "run"))
            output = _optional_path(options, "out")
            if output is not None:
                write_report(report, output)
                return CommandOutcome(0, notice="报告已写入")
            return CommandOutcome(0, text=render_report(report))
        except (OSError, ValueError) as error:
            return _failure(
                "报告生成失败：", error, "请检查输入内容、输出路径和文件权限"
            )

    def _run_watchlist(self, options: Mapping[str, object]) -> CommandOutcome:
        try:
            items = load_watchlist(_path_option(options, "file"))
            output = _optional_path(options, "out")
            if output is not None:
                write_watchlist(items, output)
                return CommandOutcome(0, notice="人工清单已写入")
            return CommandOutcome(0, text=render_watchlist(items))
        except (OSError, ValueError) as error:
            return _failure(
                "人工清单生成失败：", error, "请检查 JSON 格式、输出路径和文件权限"
            )

    def _run_validate(
        self, options: Mapping[str, object], registry: SourceRegistry
    ) -> CommandOutcome:
        run_path = _path_option(options, "run")
        schema_path = _optional_path(options, "schema_out")
        if schema_path is not None:
            try:
                write_schema(schema_path)
            except OSError as error:
                failure = RunValidation.failed(
                    run_path.as_posix(), f"无法写入 Schema：{error}"
                )
                return CommandOutcome(1, failure.as_payload())
        result = validate_run_file(
            run_path,
            check_evidence=_bool_option(options, "check_evidence"),
            timeout=_float_option(options, "timeout", 30.0),
            registry=registry,
        )
        return CommandOutcome(0 if result.passed else 1, result.as_payload())

    def _run_digest(self, options: Mapping[str, object]) -> CommandOutcome:
        try:
            report = load_report(_path_option(options, "run"))
            output_dir = _path_option(options, "out_dir")
            store = DigestFileStore(output_dir)
            previous = store.load_latest()
            config = DigestBuildConfig(
                max_items=_int_option(options, "max_items", 20),
                summary_model=_string_option(options, "summary_model", "gpt-5.6-luna"),
                summary_timeout=_float_option(options, "summary_timeout", 30.0),
                summary_reasoning_effort=cast(
                    ReasoningEffort,
                    _string_option(options, "summary_reasoning_effort", "medium"),
                ),
                use_codex=not _bool_option(options, "no_codex"),
            )
            digest = DigestBuilder().build(
                report,
                previous,
                config=config,
                now=self._clock.now().astimezone(SHANGHAI),
            )
            history, latest_json, latest_markdown = store.write(digest)
        except (DigestStoreError, OSError, ValueError) as error:
            return _failure(
                "简报生成失败：", error, "请检查输入内容、输出路径和文件权限"
            )
        payload = {
            "status": digest.status,
            "digest_id": digest.digest_id,
            "run_id": digest.run_id,
            "history": _relative_path(history, output_dir),
            "latest_json": _relative_path(latest_json, output_dir),
            "latest_markdown": _relative_path(latest_markdown, output_dir),
        }
        return CommandOutcome(0 if digest.status == "complete" else 3, payload)

    def _run_collect(
        self,
        options: Mapping[str, object],
        registry: SourceRegistry,
        plugin_ids: Sequence[str],
    ) -> CommandOutcome:
        selected_ids = self._actual_selection(
            options, getattr(registry, "source_ids", ()), plugin_ids
        )
        request = collection_request_from_options(
            options,
            now=self._clock.now().astimezone(SHANGHAI),
        ).model_copy(update={"source_ids": list(selected_ids)})
        collector = SourceCollector(registry, clock=self._clock)
        try:
            if self._registry_was_injected and self._store is None:
                result = collector.collect(request, selected_ids)
                return CommandOutcome(
                    collector.exit_code(result.health),
                    json.loads(collector.collection_json(result)),
                )
            pipeline = PipelineCollector(
                registry,
                self._store or JsonNewsStore(Path.cwd()),
                clock=self._clock,
                verifier=CodexVerifier(registry.http, clock=self._clock),
                verification_config=_verification_config(options),
            )
            report = pipeline.collect(request, selected_ids)
        except KeyError as error:
            raise ApplicationArgumentError(str(error).strip("'")) from error
        except (JsonStoreError, ValueError) as error:
            return _failure(
                "",
                error,
                "请检查输入内容、输出路径和文件权限",
                payload={
                    "status": "failed",
                    "error": {"code": "pipeline_error", "message": str(error)},
                },
            )
        payload = report.model_dump(mode="json", by_alias=True)
        return CommandOutcome(
            {"complete": 0, "partial": 3, "failed": 1}[report.status], payload
        )

    def _run_probe(
        self,
        options: Mapping[str, object],
        registry: SourceRegistry,
        plugin_ids: Sequence[str],
    ) -> CommandOutcome:
        selected_ids = self._actual_selection(
            options, getattr(registry, "source_ids", ()), plugin_ids
        )
        try:
            health = SourceCollector(registry, clock=self._clock).probe(selected_ids)
        except KeyError as error:
            raise ApplicationArgumentError(str(error).strip("'")) from error
        collector = SourceCollector(registry, clock=self._clock)
        return CommandOutcome(
            collector.exit_code(health), json.loads(collector.probe_json(health))
        )

    def _actual_selection(
        self,
        options: Mapping[str, object],
        builtin_ids: Sequence[str],
        plugin_ids: Sequence[str],
    ) -> tuple[str, ...]:
        requested = _sequence_option(options, "source_ids")
        with_plugins = _sequence_option(options, "with_plugin_ids")
        if requested:
            if with_plugins:
                unknown = [item for item in requested if item not in builtin_ids]
                if unknown:
                    raise ApplicationArgumentError(
                        f"--source 只能选择 built-in 来源：{', '.join(unknown)}"
                    )
            selected = (*requested, *plugin_ids)
        elif _sequence_option(options, "plugin_ids"):
            selected = tuple(plugin_ids)
        else:
            selected = (*builtin_ids, *plugin_ids)
        return tuple(dict.fromkeys(selected))

    def _run_publication(self, options: Mapping[str, object]) -> CommandOutcome:
        if _string_option(options, "publication_command") != "add":
            return CommandOutcome(2, help_requested=True)
        try:
            result = add_publication(
                _path_option(options, "candidate_file"),
                _sequence_option(options, "event_ids"),
                title=_string_option(options, "title"),
                platform=_string_option(options, "platform"),
                url=_string_option(options, "url"),
                published_at=_string_option(options, "published_at"),
                output_path=_path_option(options, "output_path"),
            )
        except PublicationArgumentError as error:
            raise ApplicationArgumentError(str(error)) from error
        except (OSError, ValueError) as error:
            return _failure(
                "发布记录失败：", error, "请检查 Candidate、事件 ID、输出路径和权限"
            )
        return CommandOutcome(
            0,
            text=json.dumps(
                {
                    "status": result.status,
                    "event_count": result.event_count,
                    "path": _relative_path(result.path),
                },
                ensure_ascii=False,
            )
            + "\n",
        )

    def _run_feedback(self, options: Mapping[str, object]) -> CommandOutcome:
        if _string_option(options, "feedback_command") != "record":
            return CommandOutcome(2, help_requested=True)
        try:
            result = record_weekly_feedback(
                week=_string_option(options, "week"),
                platform=_string_option(options, "platform"),
                reads=_int_option(options, "reads"),
                favorites=_int_option(options, "favorites"),
                shares=_int_option(options, "shares"),
                new_followers=_int_option(options, "new_followers"),
                note=_string_option(options, "note", ""),
                output_path=FEEDBACK_OUTPUT_PATH,
                replace=_bool_option(options, "replace"),
            )
        except FeedbackArgumentError as error:
            raise ApplicationArgumentError(str(error)) from error
        except (OSError, ValueError) as error:
            return _failure(
                "周反馈记录失败：", error, "请检查 ISO 周、指标、输出路径和权限"
            )
        return CommandOutcome(
            0,
            text=json.dumps(
                {"status": result.status, "path": _relative_path(result.path)},
                ensure_ascii=False,
            )
            + "\n",
        )

    def _run_evaluate(self, options: Mapping[str, object]) -> CommandOutcome:
        try:
            suite = load_quality_suite(_path_option(options, "suite"))
            evaluation = QualityEvaluator().evaluate(suite)
            json_path, markdown_path = write_quality_evaluation(
                evaluation, _path_option(options, "out_dir")
            )
        except QualityEvaluationError as error:
            return _failure(
                "质量评估失败：", error, "请检查 suite.json 内容和输出目录权限"
            )
        output_dir = _path_option(options, "out_dir")
        payload = {
            "status": evaluation.status,
            "suite_id": evaluation.suite_id,
            "case_count": evaluation.case_count,
            "json": _relative_path(json_path, output_dir),
            "markdown": _relative_path(markdown_path, output_dir),
        }
        return CommandOutcome(0 if evaluation.status == "passed" else 1, payload)

    def _run_ops(self, options: Mapping[str, object]) -> CommandOutcome:
        command = _string_option(options, "ops_command")
        try:
            if command == "diagnose":
                report = diagnose(
                    _path_option(options, "root"),
                    days=_int_option(options, "days", 30),
                )
            elif command == "retention-plan":
                report = build_retention_plan(
                    _path_option(options, "root"),
                    older_than_days=_int_option(options, "older_than_days"),
                )
            elif command == "recovery-check":
                report = recovery_check(
                    _path_option(options, "source_root"),
                    _path_option(options, "target"),
                )
            else:
                return CommandOutcome(2, help_requested=True)
            json_path, markdown_path = write_operations_report(
                report, _path_option(options, "out_dir")
            )
        except OperationsError as error:
            return _failure(
                "运行可靠性检查失败：",
                error,
                "请检查运行目录、目标目录和报告输出权限",
            )
        output_dir = _path_option(options, "out_dir")
        payload = {
            "status": report.status,
            "operation": report.operation,
            "json": _relative_path(json_path, output_dir),
            "markdown": _relative_path(markdown_path, output_dir),
        }
        exit_code = {"complete": 0, "partial": 3, "failed": 1}[report.status]
        return CommandOutcome(exit_code, payload)


def collection_request_from_options(
    options: Mapping[str, object], *, now: datetime | None = None
) -> CollectionRequest:
    current = now or datetime.now(SHANGHAI)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ApplicationArgumentError("当前时间必须包含时区")
    start, end = _request_range(options, current)
    source_ids = _sequence_option(options, "source_ids") or _sequence_option(
        options, "plugin_ids"
    )
    return CollectionRequest.model_validate(
        {
            "from": start,
            "to": end,
            "timezone": "Asia/Shanghai",
            "source_ids": list(source_ids),
            "verification_reasoning_effort": options.get(
                "verification_reasoning_effort"
            ),
        }
    )


def _request_range(
    options: Mapping[str, object], current: datetime
) -> tuple[datetime, datetime]:
    days = options.get("days")
    selected_date = options.get("date")
    from_date = options.get("from_date")
    to_date = options.get("to_date")
    has_calendar = days is not None or selected_date is not None
    has_range = from_date is not None or to_date is not None
    if has_calendar and has_range:
        raise ApplicationArgumentError("日期选择器不能混用")
    if days is not None:
        try:
            count = int(str(days))
        except ValueError as error:
            raise ApplicationArgumentError("--days 必须是正整数") from error
        if count <= 0:
            raise ApplicationArgumentError("--days 必须是正整数")
        return current - timedelta(days=count), current
    if selected_date is not None:
        start = _parse_local_date(str(selected_date), "--date")
        begin = datetime.combine(start, time.min, tzinfo=SHANGHAI)
        return begin, begin + timedelta(days=1)
    if (from_date is None) != (to_date is None):
        raise ApplicationArgumentError("--from 与 --to 必须同时提供")
    if from_date is None:
        return current - timedelta(days=1), current
    start = _parse_local_date(str(from_date), "--from")
    end = _parse_local_date(str(to_date), "--to")
    if start >= end:
        raise ApplicationArgumentError("开始时间必须早于结束时间")
    begin = datetime.combine(start, time.min, tzinfo=SHANGHAI)
    return begin, datetime.combine(end, time.min, tzinfo=SHANGHAI) + timedelta(days=1)


def _parse_local_date(value: str, option: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ApplicationArgumentError(f"{option} 必须使用 YYYY-MM-DD") from error
    if value != parsed.isoformat():
        raise ApplicationArgumentError(f"{option} 必须使用 YYYY-MM-DD")
    return parsed


def _verification_config(options: Mapping[str, object]) -> VerificationConfig:
    defaults = VerificationConfig()
    return VerificationConfig(
        model=_string_option(options, "verification_model", defaults.model),
        budget=_int_option(options, "verification_budget", defaults.budget),
        batch_size=_int_option(options, "verification_batch_size", defaults.batch_size),
        timeout=_float_option(options, "verification_timeout", defaults.timeout),
        reasoning_effort=cast(
            ReasoningEffort,
            _string_option(
                options, "verification_reasoning_effort", defaults.reasoning_effort
            ),
        ),
        codex_executable=defaults.codex_executable,
    )


def _failure(
    prefix: str,
    error: Exception,
    suggestion: str,
    *,
    payload: object | None = None,
) -> CommandOutcome:
    return CommandOutcome(
        1,
        payload=payload,
        error=error,
        error_prefix=prefix,
        error_suggestion=suggestion,
    )


def _relative_path(path: Path, root: Path | None = None) -> str:
    base = root or Path.cwd()
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _string_option(
    options: Mapping[str, object], name: str, default: str | None = None
) -> str:
    value = options.get(name)
    if value is None:
        value = default
    if value is None:
        raise ApplicationArgumentError(f"缺少参数：{name}")
    return str(value)


def _sequence_option(options: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = options.get(name)
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _path_option(options: Mapping[str, object], name: str) -> Path:
    return Path(_string_option(options, name))


def _optional_path(options: Mapping[str, object], name: str) -> Path | None:
    value = options.get(name)
    return None if value is None else Path(str(value))


def _bool_option(options: Mapping[str, object], name: str) -> bool:
    return bool(options.get(name, False))


def _int_option(
    options: Mapping[str, object], name: str, default: int | None = None
) -> int:
    value = options.get(name)
    if value is None:
        value = default
    if value is None:
        raise ApplicationArgumentError(f"缺少参数：{name}")
    return int(str(value))


def _float_option(
    options: Mapping[str, object], name: str, default: float | None = None
) -> float:
    value = options.get(name)
    if value is None:
        value = default
    if value is None:
        raise ApplicationArgumentError(f"缺少参数：{name}")
    return float(str(value))
