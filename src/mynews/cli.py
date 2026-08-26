"""mynews 中文命令行适配器。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from mynews.application.runtime import (
    ApplicationArgumentError,
    ApplicationRuntime,
    Command,
    CommandOutcome,
    collection_request_from_options,
)
from mynews.domain.models import CollectionRequest
from mynews.verification.protocol import REASONING_EFFORTS

if TYPE_CHECKING:
    from mynews.sources.registry import SourceRegistry
    from mynews.storage.protocol import NewsStore


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


def _add_publication_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    publication = commands.add_parser(
        "publication",
        help="人工记录已发布内容",
        description="校验 Candidate 后，离线回填 publication ledger，不自动发布内容。",
        add_help=False,
    )
    publication.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    subcommands = publication.add_subparsers(
        dest="publication_command",
        title="发布子命令",
        parser_class=ChineseArgumentParser,
    )
    add = subcommands.add_parser(
        "add",
        help="添加一篇内容对应的发布记录",
        description="离线校验 Candidate 和事件 ID，重复记录保持不变。",
        add_help=False,
    )
    add.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    add.add_argument(
        "--candidate-file",
        required=True,
        type=Path,
        metavar="路径",
        help="Candidate JSON 文件",
    )
    add.add_argument(
        "--event-id",
        dest="event_ids",
        action="append",
        required=True,
        metavar="ID",
        help="事件 ID，可重复指定",
    )
    add.add_argument("--title", required=True, metavar="标题", help="发布标题")
    add.add_argument("--platform", required=True, metavar="平台", help="发布平台")
    add.add_argument(
        "--url", required=True, metavar="HTTPS链接", help="公开 HTTPS 链接"
    )
    add.add_argument(
        "--published-at", required=True, metavar="ISO时间", help="带时区的实际发布时间"
    )
    add.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Path("output/editorial/publication-ledger.csv"),
        metavar="路径",
        help="ledger 输出路径，默认 output/editorial/publication-ledger.csv",
    )


def _add_feedback_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    feedback = commands.add_parser(
        "feedback",
        help="人工记录每周反馈",
        description="离线回填周反馈 Markdown 稳定区块，不修改候选事实。",
        add_help=False,
    )
    feedback.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    subcommands = feedback.add_subparsers(
        dest="feedback_command", title="反馈子命令", parser_class=ChineseArgumentParser
    )
    record = subcommands.add_parser(
        "record",
        help="记录一个 ISO 周的平台反馈",
        description="同周同平台相同内容幂等，冲突时必须显式使用 --replace。",
        add_help=False,
    )
    record.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    record.add_argument("--week", required=True, metavar="YYYY-Www", help="ISO 周")
    record.add_argument("--platform", required=True, metavar="平台", help="反馈平台")
    metrics = (
        ("--reads", "reads", "阅读数"),
        ("--favorites", "favorites", "收藏数"),
        ("--shares", "shares", "转发数"),
        ("--new-followers", "new_followers", "新增关注数"),
    )
    for option, destination, label in metrics:
        record.add_argument(
            option,
            dest=destination,
            required=True,
            type=_nonnegative_int,
            metavar="数量",
            help=f"{label}，必须是非负整数",
        )
    record.add_argument("--note", default="", metavar="文本", help="可选的单行典型反馈")
    record.add_argument("--replace", action="store_true", help="显式替换已有稳定区块")


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
    _add_collect_parser(commands)
    _add_probe_parser(commands)
    _add_validate_parser(commands)
    _add_report_parser(commands)
    _add_watchlist_parser(commands)
    _add_digest_parser(commands)
    _add_prepare_parser(commands)
    _add_evaluate_parser(commands)
    _add_ops_parser(commands)
    _add_editorial_parser(commands)
    _add_publication_parser(commands)
    _add_feedback_parser(commands)
    _add_plugin_parser(commands)
    return parser


def _add_collect_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
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


def _add_probe_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    probe = commands.add_parser(
        "probe",
        help="检查来源健康状态",
        description="检查内置来源健康状态并输出结构化结果。",
        add_help=False,
    )
    probe.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    selector = probe.add_mutually_exclusive_group()
    selector.add_argument(
        "--source", dest="source_ids", action="append", help="只检查指定来源"
    )
    selector.add_argument(
        "--plugin", dest="plugin_ids", action="append", help="显式加载并检查外部插件"
    )
    probe.add_argument(
        "--with-plugin",
        dest="with_plugin_ids",
        action="append",
        help="在 built-in 来源之外追加显式外部插件，可重复指定",
    )


def _add_validate_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
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


def _add_report_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
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


def _add_watchlist_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    watchlist = commands.add_parser(
        "watchlist",
        help="校验并渲染人工来源清单",
        description="离线校验人工清单并生成确定性 Markdown，不访问网络或 Store。",
        add_help=False,
    )
    watchlist.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    watchlist.add_argument(
        "--file", required=True, metavar="路径", help="人工清单 JSON 文件"
    )
    watchlist.add_argument(
        "--out",
        metavar="路径",
        help="Markdown 输出路径；不提供时打印到标准输出",
    )


def _add_digest_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
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


def _add_prepare_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    prepare = commands.add_parser(
        "prepare",
        help="生成或稳定重放指定日期的编辑候选包",
        description=(
            "采集 25 个 newsFromAI 自动 Feed，生成 candidates.json/md；"
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


def _add_evaluate_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    evaluate = commands.add_parser(
        "evaluate",
        help="执行离线情报质量评估",
        description=(
            "读取自包含 suite.json，比较固定样本的期望与实际结果；"
            "不访问网络、Codex 或定时任务。"
        ),
        add_help=False,
    )
    evaluate.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    evaluate.add_argument(
        "--suite",
        required=True,
        type=Path,
        metavar="路径",
        help="自包含质量评估样本 JSON",
    )
    evaluate.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        metavar="目录",
        help="JSON 与 Markdown 输出目录",
    )


def _add_ops_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    ops = commands.add_parser(
        "ops",
        help="执行离线运行可靠性检查",
        description=(
            "诊断运行状态、生成非破坏性保留计划或检查隔离恢复；"
            "不访问网络、不调用 Codex、不删除文件。"
        ),
        add_help=False,
    )
    ops.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    subcommands = ops.add_subparsers(
        dest="ops_command", title="运维子命令", parser_class=ChineseArgumentParser
    )
    diagnose = subcommands.add_parser(
        "diagnose",
        help="诊断来源、证据、存储和调度状态",
        description="只读分析指定运行目录，报告只含相对路径、哈希和统计。",
        add_help=False,
    )
    diagnose.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    diagnose.add_argument(
        "--root", required=True, type=Path, metavar="目录", help="运行根目录"
    )
    diagnose.add_argument(
        "--days",
        type=_positive_int,
        default=30,
        metavar="天数",
        help="陈旧 latest 的判断天数，默认 30",
    )
    diagnose.add_argument(
        "--out-dir", required=True, type=Path, metavar="目录", help="报告输出目录"
    )
    retention = subcommands.add_parser(
        "retention-plan",
        help="生成非破坏性保留候选",
        description="只列出候选，不移动或删除文件，人工台账和引用记录受保护。",
        add_help=False,
    )
    retention.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    retention.add_argument(
        "--root", required=True, type=Path, metavar="目录", help="运行根目录"
    )
    retention.add_argument(
        "--older-than-days",
        required=True,
        type=_positive_int,
        metavar="天数",
        help="只列出早于该天数的候选",
    )
    retention.add_argument(
        "--out-dir", required=True, type=Path, metavar="目录", help="报告输出目录"
    )
    recovery = subcommands.add_parser(
        "recovery-check",
        help="检查隔离恢复结果",
        description="只复制白名单到全新空目录，校验 Schema、引用和哈希。",
        add_help=False,
    )
    recovery.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    recovery.add_argument(
        "--source-root", required=True, type=Path, metavar="目录", help="恢复源目录"
    )
    recovery.add_argument(
        "--target", required=True, type=Path, metavar="目录", help="全新空目标目录"
    )
    recovery.add_argument(
        "--out-dir", required=True, type=Path, metavar="目录", help="报告输出目录"
    )


def _add_editorial_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
    editorial = commands.add_parser(
        "editorial",
        help="生成只读周复盘",
        description=(
            "读取 Candidate、Digest、发布台账和周反馈，生成 EditorialReview 1.0；"
            "不修改输入、不访问网络、不自动发布。"
        ),
        add_help=False,
    )
    editorial.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    subcommands = editorial.add_subparsers(
        dest="editorial_command",
        title="编辑子命令",
        parser_class=ChineseArgumentParser,
    )
    review = subcommands.add_parser(
        "review",
        help="生成指定 ISO 周的复盘报告",
        description=(
            "确定性统计始终离线完成；Codex 仅可生成可丢弃的建议，不是事实来源。"
        ),
        add_help=False,
    )
    review.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    review.add_argument("--week", required=True, metavar="YYYY-Www", help="目标 ISO 周")
    review.add_argument(
        "--out-dir", required=True, type=Path, metavar="目录", help="报告输出目录"
    )
    review.add_argument(
        "--no-codex", action="store_true", help="只运行确定性离线统计，不调用 Codex"
    )


def _add_plugin_parser(
    commands: argparse._SubParsersAction[ChineseArgumentParser],
) -> None:
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


def _request_from_namespace(
    args: argparse.Namespace,
    parser: ChineseArgumentParser,
    now: datetime | None,
) -> CollectionRequest:
    try:
        return collection_request_from_options(vars(args), now=now)
    except ApplicationArgumentError as error:
        parser.error(str(error))


def build_collection_request(
    arguments: Sequence[str], *, now: datetime | None = None
) -> CollectionRequest:
    """解析 collect 参数，供 CLI 和离线测试共用。"""

    parser = build_parser()
    args = parser.parse_args(["collect", *arguments])
    return _request_from_namespace(args, parser, now)


def _safe_cli_error(error: Exception, suggestion: str) -> str:
    reason = error.strerror if isinstance(error, OSError) else str(error)
    return f"{reason or '文件操作失败'}；{suggestion}"


def _present(outcome: CommandOutcome, parser: ChineseArgumentParser) -> int:
    if outcome.help_requested:
        parser.print_help()
    if outcome.payload is not None:
        print(json.dumps(outcome.payload, ensure_ascii=False, indent=2))
    elif outcome.error is not None:
        print(
            f"{outcome.error_prefix}"
            f"{_safe_cli_error(outcome.error, outcome.error_suggestion)}"
        )
    elif outcome.notice is not None:
        print(outcome.notice)
    elif outcome.text is not None:
        print(outcome.text, end="")
    return outcome.exit_code


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: SourceRegistry | None = None,
    store: NewsStore | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None or (
        args.command == "plugin" and args.plugin_command is None
    ):
        parser.print_help()
        return 2
    try:
        outcome = ApplicationRuntime(registry=registry, store=store).run(
            Command(args.command, vars(args))
        )
    except ApplicationArgumentError as error:
        parser.error(str(error))
    return _present(outcome, parser)


if __name__ == "__main__":
    raise SystemExit(main())
