"""mynews 中文命令行入口。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfo

from mynews.application.collector import PipelineCollector, SourceCollector
from mynews.application.digest import DigestBuildConfig, DigestBuilder
from mynews.application.feedback import FeedbackArgumentError, record_weekly_feedback
from mynews.application.prepare import prepare_editorial_pack
from mynews.application.publication import PublicationArgumentError, add_publication
from mynews.application.report import load_report, render_report, write_report
from mynews.application.validation import RunValidation, validate_run_file, write_schema
from mynews.application.watchlist import (
    load_watchlist,
    render_watchlist,
    write_watchlist,
)
from mynews.domain.models import CollectionRequest
from mynews.sources.external import ExternalPluginLoader, PluginLoadReport
from mynews.sources.registry import SourceRegistry, built_in_registry
from mynews.storage.digest_store import DigestFileStore, DigestStoreError
from mynews.storage.json_store import JsonNewsStore, JsonStoreError
from mynews.storage.protocol import NewsStore
from mynews.verification.codex import CodexVerifier
from mynews.verification.protocol import REASONING_EFFORTS, VerificationConfig

SHANGHAI = ZoneInfo("Asia/Shanghai")


class ChineseArgumentParser(argparse.ArgumentParser):
    """将 argparse 的用户可见帮助和错误保持为中文。"""

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法：", 1)

    def format_help(self) -> str:
        help_text = super().format_help()
        help_text = help_text.replace("usage:", "用法：", 1)
        help_text = help_text.replace("options:", "选项：", 1)
        return help_text.replace("optional arguments:", "选项：", 1)

    def error(self, message: str) -> NoReturn:
        translated = message.replace("unrecognized arguments:", "无法识别的参数：")
        translated = translated.replace("invalid choice:", "无效选项：")
        translated = translated.replace("expected one argument", "需要一个参数")
        translated = translated.replace("not allowed with", "不能与")
        translated = translated.replace(
            "the following arguments are required:", "缺少必需参数："
        )
        translated = translated.replace("argument ", "参数 ")
        self.print_usage()
        self.exit(2, f"{self.prog}: 参数错误：{translated}\n")


def build_parser() -> ChineseArgumentParser:
    parser = ChineseArgumentParser(
        prog="mynews",
        description="收集 AI 与科技热点，并保存可验证的结构化结果。",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    commands = parser.add_subparsers(
        dest="command", title="子命令", parser_class=ChineseArgumentParser
    )

    collect = commands.add_parser(
        "collect",
        help="收集热点候选",
        description="按时间范围收集、规范化、去重、核验并保存结构化结果。",
        add_help=False,
    )
    collect.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    selector = collect.add_mutually_exclusive_group()
    selector.add_argument("--days", metavar="天数", help="收集最近 N 天")
    selector.add_argument(
        "--date", metavar="日期", help="收集指定本地日期，格式 YYYY-MM-DD"
    )
    selector.add_argument(
        "--from", dest="from_date", metavar="日期", help="起始本地日期"
    )
    collect.add_argument(
        "--to", dest="to_date", metavar="日期", help="结束本地日期（包含当天）"
    )
    source_selector = collect.add_mutually_exclusive_group()
    source_selector.add_argument(
        "--source", dest="source_ids", action="append", help="只选择指定来源"
    )
    source_selector.add_argument(
        "--plugin", dest="plugin_ids", action="append", help="显式加载并选择外部插件"
    )
    collect.add_argument(
        "--with-plugin",
        dest="with_plugin_ids",
        action="append",
        help="在 built-in 来源之外追加显式外部插件，可重复指定",
    )
    collect.add_argument("--verification-model", metavar="模型", help="Codex 核验模型")
    collect.add_argument(
        "--verification-budget",
        metavar="条数",
        type=_nonnegative_int,
        help="最多交给 Codex 的候选条数",
    )
    collect.add_argument(
        "--verification-batch-size",
        metavar="条数",
        type=_positive_int,
        help="每次 Codex 请求包含的候选条数",
    )
    collect.add_argument(
        "--verification-timeout",
        metavar="秒",
        type=_positive_float,
        help="每次 Codex/证据请求的超时时间",
    )
    collect.add_argument(
        "--verification-reasoning-effort",
        choices=REASONING_EFFORTS,
        metavar="强度",
        help="Codex 核验推理强度，默认 medium",
    )

    probe = commands.add_parser(
        "probe",
        help="检查来源健康状态",
        description="检查内置来源健康状态并输出结构化结果。",
        add_help=False,
    )
    probe.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    probe_selector = probe.add_mutually_exclusive_group()
    probe_selector.add_argument(
        "--source", dest="source_ids", action="append", help="只检查指定来源"
    )
    probe_selector.add_argument(
        "--plugin", dest="plugin_ids", action="append", help="显式加载并检查外部插件"
    )
    probe.add_argument(
        "--with-plugin",
        dest="with_plugin_ids",
        action="append",
        help="在 built-in 来源之外追加显式外部插件，可重复指定",
    )

    validate = commands.add_parser(
        "validate",
        help="校验 RunReport 和 verified 证据",
        description=(
            "按同一 Pydantic Schema 校验 RunReport，并可重新抓取 verified 证据。"
        ),
        add_help=False,
    )
    validate.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    validate.add_argument(
        "--run",
        default="output/latest.json",
        metavar="路径",
        help="要校验的 RunReport JSON，默认 output/latest.json",
    )
    validate.add_argument(
        "--schema-out", metavar="路径", help="导出同源 RunReport JSON Schema"
    )
    validate.add_argument(
        "--check-evidence",
        action="store_true",
        help="重新抓取并校验每条 verified 的第一方证据",
    )
    validate.add_argument(
        "--timeout",
        type=_positive_float,
        default=30.0,
        metavar="秒",
        help="证据重抓取超时时间，默认 30 秒",
    )
    report = commands.add_parser(
        "report",
        help="从 RunReport 生成中文 Markdown 报告",
        description="离线读取 RunReport，生成已核验、待核验、价格变化和来源状态报告。",
        add_help=False,
    )
    report.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    report.add_argument(
        "--run",
        default="output/latest.json",
        metavar="路径",
        help="要读取的 RunReport JSON，默认 output/latest.json",
    )
    report.add_argument(
        "--out",
        metavar="路径",
        help="Markdown 输出路径；不提供时打印到标准输出",
    )
    watchlist = commands.add_parser(
        "watchlist",
        help="校验并渲染人工来源清单",
        description="离线校验人工清单并生成确定性 Markdown，不访问网络或 Store。",
        add_help=False,
    )
    watchlist.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    watchlist.add_argument(
        "--file",
        required=True,
        metavar="路径",
        help="人工清单 JSON 文件",
    )
    watchlist.add_argument(
        "--out",
        metavar="路径",
        help="Markdown 输出路径；不提供时打印到标准输出",
    )
    digest = commands.add_parser(
        "digest",
        help="从 RunReport 生成中文情报简报",
        description=(
            "离线读取 RunReport 和上一期 Digest，生成主榜、线索观察及原子输出。"
        ),
        add_help=False,
    )
    digest.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    digest.add_argument(
        "--run",
        default="output/latest.json",
        metavar="路径",
        help="要读取的 RunReport JSON，默认 output/latest.json",
    )
    digest.add_argument(
        "--out-dir",
        default="output",
        metavar="目录",
        help="Digest 输出目录，默认 output",
    )
    digest.add_argument(
        "--max-items",
        type=_positive_int,
        default=20,
        metavar="条数",
        help="最多输出的主榜和线索总条数，默认 20",
    )
    digest.add_argument(
        "--summary-model",
        metavar="模型",
        help="Codex 摘要模型，默认 gpt-5.6-luna",
    )
    digest.add_argument(
        "--summary-timeout",
        type=_positive_float,
        default=30.0,
        metavar="秒",
        help="每次 Codex 摘要调用超时时间，默认 30 秒",
    )
    digest.add_argument(
        "--summary-reasoning-effort",
        choices=REASONING_EFFORTS,
        metavar="强度",
        help="Codex 摘要推理强度，默认 medium",
    )
    digest.add_argument(
        "--no-codex",
        action="store_true",
        help="不调用 Codex，全部使用安全回退文本",
    )
    prepare = commands.add_parser(
        "prepare",
        help="生成或稳定重放指定日期的编辑候选包",
        description=(
            "采集 17 个 newsFromAI 自动 Feed，生成 candidates.json/md；"
            "不调用 Codex 或自动发布。"
        ),
        add_help=False,
    )
    prepare.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    prepare.add_argument(
        "--date", required=True, metavar="日期", help="业务日期，格式 YYYY-MM-DD"
    )
    prepare.add_argument(
        "--refresh", action="store_true", help="重新抓取当天数据并更新候选包"
    )
    publication = commands.add_parser(
        "publication",
        help="人工记录已发布内容",
        description="校验 Candidate 后，离线回填 publication ledger，不自动发布内容。",
        add_help=False,
    )
    publication.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    publication_commands = publication.add_subparsers(
        dest="publication_command",
        title="发布子命令",
        parser_class=ChineseArgumentParser,
    )
    publication_add = publication_commands.add_parser(
        "add",
        help="添加一篇内容对应的发布记录",
        description="离线校验 Candidate 和事件 ID，重复记录保持不变。",
        add_help=False,
    )
    publication_add.add_argument(
        "-h", "--help", action="help", help="显示帮助并退出"
    )
    publication_add.add_argument(
        "--candidate-file",
        "--candidate",
        "--file",
        dest="candidate_file",
        required=True,
        type=Path,
        metavar="路径",
        help="Candidate JSON 文件",
    )
    publication_add.add_argument(
        "event_ids",
        nargs="*",
        metavar="事件ID",
        help="一个或多个事件 ID，也可使用 --event-id 重复指定",
    )
    publication_add.add_argument(
        "--event-id",
        "--event-ids",
        dest="event_id_options",
        action="append",
        metavar="ID",
        help="事件 ID，可重复指定",
    )
    publication_add.add_argument(
        "--title", "--post-title", required=True, metavar="标题", help="发布标题"
    )
    publication_add.add_argument(
        "--platform", required=True, metavar="平台", help="发布平台"
    )
    publication_add.add_argument(
        "--url",
        "--public-url",
        required=True,
        metavar="HTTPS链接",
        help="公开 HTTPS 链接",
    )
    publication_add.add_argument(
        "--published-at",
        "--time",
        required=True,
        metavar="ISO时间",
        help="带时区的实际发布时间",
    )
    publication_add.add_argument(
        "--out",
        "--ledger",
        dest="output_path",
        type=Path,
        default=Path("output/editorial/publication-ledger.csv"),
        metavar="路径",
        help="ledger 输出路径，默认 output/editorial/publication-ledger.csv",
    )
    feedback = commands.add_parser(
        "feedback",
        help="人工记录每周反馈",
        description="离线回填周反馈 Markdown 稳定区块，不修改候选事实。",
        add_help=False,
    )
    feedback.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    feedback_commands = feedback.add_subparsers(
        dest="feedback_command", title="反馈子命令", parser_class=ChineseArgumentParser
    )
    feedback_record = feedback_commands.add_parser(
        "record",
        help="记录一个 ISO 周的平台反馈",
        description="同周同平台相同内容幂等，冲突时必须显式使用 --replace。",
        add_help=False,
    )
    feedback_record.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    feedback_record.add_argument(
        "--week", "--iso-week", required=True, metavar="YYYY-Www", help="ISO 周"
    )
    feedback_record.add_argument(
        "--platform", required=True, metavar="平台", help="反馈平台"
    )
    feedback_record.add_argument(
        "--reads",
        "--reading",
        "--views",
        dest="reads",
        required=True,
        type=_nonnegative_int,
        metavar="数量",
        help="阅读数，必须是非负整数",
    )
    feedback_record.add_argument(
        "--favorites",
        "--likes",
        "--collects",
        dest="favorites",
        required=True,
        type=_nonnegative_int,
        metavar="数量",
        help="收藏数，必须是非负整数",
    )
    feedback_record.add_argument(
        "--shares",
        "--forwards",
        dest="shares",
        required=True,
        type=_nonnegative_int,
        metavar="数量",
        help="转发数，必须是非负整数",
    )
    feedback_record.add_argument(
        "--new-followers",
        "--new-follows",
        "--followers",
        dest="new_followers",
        required=True,
        type=_nonnegative_int,
        metavar="数量",
        help="新增关注数，必须是非负整数",
    )
    feedback_record.add_argument(
        "--note",
        "--feedback",
        "--comment",
        dest="note",
        default="",
        metavar="文本",
        help="可选的单行典型反馈",
    )
    feedback_record.add_argument(
        "--replace", action="store_true", help="显式替换已有稳定区块"
    )
    feedback_record.add_argument(
        "--out",
        type=Path,
        default=Path("output/editorial/weekly-feedback.md"),
        metavar="路径",
        help="反馈输出路径，默认 output/editorial/weekly-feedback.md",
    )
    plugin = commands.add_parser(
        "plugin",
        help="发现和显式检查外部来源插件",
        description="只发现 Python entry-point；只有显式 --plugin 才会加载外部代码。",
        add_help=False,
    )
    plugin.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    plugin_commands = plugin.add_subparsers(
        dest="plugin_command", title="插件子命令", parser_class=ChineseArgumentParser
    )
    plugin_list = plugin_commands.add_parser(
        "list",
        help="列出已发现的外部 entry-point",
        description="只读取分发元数据，不执行外部插件工厂。",
        add_help=False,
    )
    plugin_list.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    plugin_probe = plugin_commands.add_parser(
        "probe",
        help="显式加载并检查一个外部插件",
        description="加载指定外部插件并检查其来源健康状态。",
        add_help=False,
    )
    plugin_probe.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    plugin_probe.add_argument(
        "--plugin",
        dest="plugin_ids",
        action="append",
        required=True,
        metavar="ID",
        help="entry-point 名称",
    )
    return parser


def _parse_local_date(value: str, parser: ChineseArgumentParser, option: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parser.error(f"{option} 必须使用 YYYY-MM-DD")
    if value != parsed.isoformat():
        parser.error(f"{option} 必须使用 YYYY-MM-DD")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是正整数") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是非负整数") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是正数") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正数")
    return parsed


def _verification_config(args: argparse.Namespace) -> VerificationConfig:
    defaults = VerificationConfig()
    return VerificationConfig(
        model=args.verification_model or defaults.model,
        budget=(
            args.verification_budget
            if args.verification_budget is not None
            else defaults.budget
        ),
        batch_size=(
            args.verification_batch_size
            if args.verification_batch_size is not None
            else defaults.batch_size
        ),
        timeout=(
            args.verification_timeout
            if args.verification_timeout is not None
            else defaults.timeout
        ),
        reasoning_effort=(
            args.verification_reasoning_effort or defaults.reasoning_effort
        ),
        codex_executable=defaults.codex_executable,
    )


def _local_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=SHANGHAI)


def _request_from_namespace(
    args: argparse.Namespace,
    parser: ChineseArgumentParser,
    now: datetime | None,
) -> CollectionRequest:
    current = now or datetime.now(SHANGHAI)
    if current.tzinfo is None or current.utcoffset() is None:
        parser.error("当前时间必须包含时区")

    source_ids = args.source_ids or args.plugin_ids or []
    has_calendar_selector = args.days is not None or args.date is not None
    has_range_selector = args.from_date is not None or args.to_date is not None
    if has_calendar_selector and has_range_selector:
        parser.error("日期选择器不能混用")
    if args.days is not None:
        try:
            days = int(args.days)
        except ValueError:
            parser.error("--days 必须是正整数")
        if days <= 0:
            parser.error("--days 必须是正整数")
        start = current - timedelta(days=days)
        end = current
    elif args.date is not None:
        selected = _parse_local_date(args.date, parser, "--date")
        start = _local_midnight(selected)
        end = start + timedelta(days=1)
    else:
        if (args.from_date is None) != (args.to_date is None):
            parser.error("--from 与 --to 必须同时提供")
        if args.from_date is None:
            start = current - timedelta(days=1)
            end = current
        else:
            start_date = _parse_local_date(args.from_date, parser, "--from")
            end_date = _parse_local_date(args.to_date, parser, "--to")
            start = _local_midnight(start_date)
            end = _local_midnight(end_date) + timedelta(days=1)

    if start >= end:
        parser.error("开始时间必须早于结束时间")

    return CollectionRequest.model_validate(
        {
            "from": start,
            "to": end,
            "timezone": "Asia/Shanghai",
            "source_ids": source_ids,
            "verification_reasoning_effort": args.verification_reasoning_effort,
        }
    )


def _validate_plugin_mode(
    args: argparse.Namespace, parser: ChineseArgumentParser
) -> None:
    if getattr(args, "plugin_ids", None) and getattr(args, "with_plugin_ids", None):
        parser.error("--plugin 不能与 --with-plugin 混用")


def build_collection_request(
    arguments: Sequence[str], *, now: datetime | None = None
) -> CollectionRequest:
    """解析 collect 参数，供 CLI 和离线测试共用。"""

    parser = build_parser()
    args = parser.parse_args(["collect", *arguments])
    return _request_from_namespace(args, parser, now)


def _load_external_selection(
    registry: SourceRegistry,
    plugin_ids: Sequence[str],
) -> tuple[SourceRegistry, PluginLoadReport] | None:
    report = ExternalPluginLoader().load(
        plugin_ids,
        occupied_source_ids=registry.source_ids,
    )
    if report.status == "failed":
        print(json.dumps(report.as_payload(), ensure_ascii=False, indent=2))
        return None
    return registry.with_plugins(report.plugins), report


def _selected_external_source_ids(report: PluginLoadReport) -> tuple[str, ...]:
    return tuple(item.plugin.metadata.source_id for item in report.loaded)


def _relative_output_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _safe_cli_error(error: Exception, suggestion: str) -> str:
    reason = error.strerror if isinstance(error, OSError) else str(error)
    return f"{reason or '文件操作失败'}；{suggestion}"


def _actual_selection(
    args: argparse.Namespace,
    builtin_ids: Sequence[str],
    plugin_ids: Sequence[str],
    parser: ChineseArgumentParser,
) -> tuple[str, ...]:
    source_ids = getattr(args, "source_ids", None)
    if source_ids is not None:
        if getattr(args, "with_plugin_ids", None):
            unknown = [
                source_id for source_id in source_ids if source_id not in builtin_ids
            ]
            if unknown:
                parser.error(f"--source 只能选择 built-in 来源：{', '.join(unknown)}")
        selected = (*source_ids, *plugin_ids)
    elif getattr(args, "plugin_ids", None):
        selected = tuple(plugin_ids)
    else:
        selected = (*builtin_ids, *plugin_ids)
    return tuple(dict.fromkeys(selected))


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: SourceRegistry | None = None,
    store: NewsStore | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    active_registry = registry or built_in_registry()
    if args.command == "plugin":
        if args.plugin_command == "list":
            plugin_list_report = ExternalPluginLoader().list_report()
            print(json.dumps(plugin_list_report, ensure_ascii=False, indent=2))
            return 0 if plugin_list_report["status"] == "complete" else 1
        if args.plugin_command == "probe":
            prepared = _load_external_selection(active_registry, args.plugin_ids)
            if prepared is None:
                return 1
            selected_registry, plugin_report = prepared
            health = SourceCollector(selected_registry).probe(
                _selected_external_source_ids(plugin_report)
            )
            payload = json.loads(SourceCollector.probe_json(health))
            payload["plugins"] = [item.as_payload() for item in plugin_report.loaded]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return SourceCollector.exit_code(health)
        parser.print_help()
        return 2
    if args.command == "publication":
        if args.publication_command != "add":
            parser.print_help()
            return 2
        event_ids = [*args.event_ids, *(args.event_id_options or [])]
        try:
            publication_result = add_publication(
                args.candidate_file,
                event_ids,
                title=args.title,
                platform=args.platform,
                url=args.url,
                published_at=args.published_at,
                output_path=args.output_path,
            )
        except PublicationArgumentError as error:
            parser.error(str(error))
        except (OSError, ValueError) as error:
            print(
                "发布记录失败："
                f"{_safe_cli_error(error, '请检查 Candidate、事件 ID、输出路径和权限')}"
            )
            return 1
        print(
            json.dumps(
                {
                    "status": publication_result.status,
                    "event_count": publication_result.event_count,
                    "path": _relative_output_path(publication_result.path, Path.cwd()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "feedback":
        if args.feedback_command != "record":
            parser.print_help()
            return 2
        try:
            feedback_result = record_weekly_feedback(
                week=args.week,
                platform=args.platform,
                reads=args.reads,
                favorites=args.favorites,
                shares=args.shares,
                new_followers=args.new_followers,
                note=args.note,
                output_path=args.out,
                replace=args.replace,
            )
        except FeedbackArgumentError as error:
            parser.error(str(error))
        except (OSError, ValueError) as error:
            print(
                "周反馈记录失败："
                f"{_safe_cli_error(error, '请检查 ISO 周、指标、输出路径和文件权限')}"
            )
            return 1
        print(
            json.dumps(
                {
                    "status": feedback_result.status,
                    "path": _relative_output_path(feedback_result.path, Path.cwd()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command in {"collect", "probe"}:
        _validate_plugin_mode(args, parser)
    builtin_ids = getattr(active_registry, "source_ids", ())
    requested_plugins = getattr(args, "plugin_ids", None) or getattr(
        args, "with_plugin_ids", None
    )
    if requested_plugins:
        prepared = _load_external_selection(active_registry, requested_plugins)
        if prepared is None:
            return 1
        active_registry, plugin_report = prepared
        selected_plugin_source_ids = _selected_external_source_ids(plugin_report)
    else:
        selected_plugin_source_ids = ()
    collector = SourceCollector(active_registry)
    if args.command == "prepare":
        parsed_date = _parse_local_date(args.date, parser, "--date")
        try:
            prepare_result = prepare_editorial_pack(
                parsed_date.isoformat(),
                root=Path.cwd(),
                refresh=args.refresh,
            )
        except (OSError, ValueError) as error:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": {"code": "prepare_error", "message": str(error)},
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "status": prepare_result.status,
                    "outputDir": _relative_output_path(
                        prepare_result.output_dir, Path.cwd()
                    ),
                    "candidateCount": prepare_result.candidate_count,
                    "sourceFailureCount": prepare_result.source_failures,
                    "refreshed": prepare_result.refreshed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return {"complete": 0, "partial": 3, "failed": 1}[prepare_result.status]
    if args.command == "report":
        try:
            report = load_report(Path(args.run))
            if args.out:
                write_report(report, Path(args.out))
                print("报告已写入")
            else:
                print(render_report(report), end="")
        except (OSError, ValueError) as error:
            print(
                "报告生成失败："
                f"{_safe_cli_error(error, '请检查输入内容、输出路径和文件权限')}"
            )
            return 1
        return 0
    if args.command == "watchlist":
        try:
            items = load_watchlist(Path(args.file))
            if args.out:
                write_watchlist(items, Path(args.out))
                print("人工清单已写入")
            else:
                print(render_watchlist(items), end="")
        except (OSError, ValueError) as error:
            print(
                "人工清单生成失败："
                f"{_safe_cli_error(error, '请检查 JSON 格式、输出路径和文件权限')}"
            )
            return 1
        return 0
    if args.command == "validate":
        if args.schema_out:
            try:
                write_schema(Path(args.schema_out))
            except OSError as error:
                failure = RunValidation.failed(args.run, f"无法写入 Schema：{error}")
                print(json.dumps(failure.as_payload(), ensure_ascii=False, indent=2))
                return 1
        validation_result = validate_run_file(
            Path(args.run),
            check_evidence=args.check_evidence,
            timeout=args.timeout,
            registry=active_registry,
        )
        print(json.dumps(validation_result.as_payload(), ensure_ascii=False, indent=2))
        return 0 if validation_result.passed else 1
    if args.command == "digest":
        try:
            report = load_report(Path(args.run))
            digest_store = DigestFileStore(Path(args.out_dir))
            previous = digest_store.load_latest()
            defaults = DigestBuildConfig()
            config = DigestBuildConfig(
                max_items=args.max_items,
                summary_model=args.summary_model or defaults.summary_model,
                summary_timeout=args.summary_timeout,
                summary_reasoning_effort=(
                    args.summary_reasoning_effort or defaults.summary_reasoning_effort
                ),
                use_codex=not args.no_codex,
            )
            digest = DigestBuilder().build(
                report,
                previous,
                config=config,
                now=datetime.now(SHANGHAI),
            )
            history_path, latest_json, latest_markdown = digest_store.write(digest)
        except (DigestStoreError, OSError, ValueError) as error:
            print(
                "简报生成失败："
                f"{_safe_cli_error(error, '请检查输入内容、输出路径和文件权限')}"
            )
            return 1
        print(
            json.dumps(
                {
                    "status": digest.status,
                    "digest_id": digest.digest_id,
                    "run_id": digest.run_id,
                    "history": _relative_output_path(history_path, Path(args.out_dir)),
                    "latest_json": _relative_output_path(
                        latest_json, Path(args.out_dir)
                    ),
                    "latest_markdown": _relative_output_path(
                        latest_markdown, Path(args.out_dir)
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if digest.status == "complete" else 3
    if args.command == "collect":
        request = _request_from_namespace(args, parser, None)
        selected_source_ids = _actual_selection(
            args, builtin_ids, selected_plugin_source_ids, parser
        )
        request = request.model_copy(update={"source_ids": list(selected_source_ids)})
        verification_config = _verification_config(args)
        try:
            if registry is not None and store is None:
                collection_result = collector.collect(request, selected_source_ids)
                print(collector.collection_json(collection_result))
                return collector.exit_code(collection_result.health)
            pipeline = PipelineCollector(
                active_registry,
                store or JsonNewsStore(Path.cwd()),
                verifier=CodexVerifier(active_registry.http),
                verification_config=verification_config,
            )
            report = pipeline.collect(request, selected_source_ids)
        except KeyError as error:
            parser.error(str(error).strip("'"))
        except (JsonStoreError, ValueError) as error:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": {"code": "pipeline_error", "message": str(error)},
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        print(
            json.dumps(
                report.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            )
        )
        return {"complete": 0, "partial": 3, "failed": 1}[report.status]
    if args.command == "probe":
        selected_source_ids = _actual_selection(
            args, builtin_ids, selected_plugin_source_ids, parser
        )
        try:
            health = collector.probe(selected_source_ids)
        except KeyError as error:
            parser.error(str(error).strip("'"))
        print(collector.probe_json(health))
        return collector.exit_code(health)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
