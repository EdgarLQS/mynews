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
from mynews.application.validation import RunValidation, validate_run_file, write_schema
from mynews.domain.models import CollectionRequest
from mynews.sources.registry import SourceRegistry, built_in_registry
from mynews.storage.json_store import JsonNewsStore, JsonStoreError
from mynews.storage.protocol import NewsStore
from mynews.verification.codex import CodexVerifier
from mynews.verification.protocol import VerificationConfig

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
    collect.add_argument(
        "--source", dest="source_ids", action="append", help="只选择指定来源"
    )
    collect.add_argument(
        "--verification-model", metavar="模型", help="Codex 核验模型"
    )
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

    probe = commands.add_parser(
        "probe",
        help="检查来源健康状态",
        description="检查内置来源健康状态并输出结构化结果。",
        add_help=False,
    )
    probe.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    probe.add_argument(
        "--source", dest="source_ids", action="append", help="只检查指定来源"
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

    source_ids = args.source_ids or []
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
        }
    )


def build_collection_request(
    arguments: Sequence[str], *, now: datetime | None = None
) -> CollectionRequest:
    """解析 collect 参数，供 CLI 和离线测试共用。"""

    parser = build_parser()
    args = parser.parse_args(["collect", *arguments])
    return _request_from_namespace(args, parser, now)


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: SourceRegistry | None = None,
    store: NewsStore | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    active_registry = registry or built_in_registry()
    collector = SourceCollector(active_registry)
    if args.command == "validate":
        if args.schema_out:
            try:
                write_schema(Path(args.schema_out))
            except OSError as error:
                failure = RunValidation.failed(args.run, f"无法写入 Schema：{error}")
                print(
                    json.dumps(failure.as_payload(), ensure_ascii=False, indent=2)
                )
                return 1
        validation_result = validate_run_file(
            Path(args.run),
            check_evidence=args.check_evidence,
            timeout=args.timeout,
            registry=active_registry,
        )
        print(
            json.dumps(
                validation_result.as_payload(), ensure_ascii=False, indent=2
            )
        )
        return 0 if validation_result.passed else 1
    if args.command == "collect":
        request = _request_from_namespace(args, parser, None)
        verification_config = _verification_config(args)
        try:
            if registry is not None and store is None:
                result = collector.collect(request, args.source_ids)
                print(collector.collection_json(result))
                return collector.exit_code(result.health)
            pipeline = PipelineCollector(
                active_registry,
                store or JsonNewsStore(Path.cwd()),
                verifier=CodexVerifier(active_registry.http),
                verification_config=verification_config,
            )
            report = pipeline.collect(request, args.source_ids)
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
        try:
            health = collector.probe(args.source_ids)
        except KeyError as error:
            parser.error(str(error).strip("'"))
        print(collector.probe_json(health))
        return collector.exit_code(health)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
