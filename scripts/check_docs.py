#!/usr/bin/env python3
"""校验 mynews 文档与 AI 指令入口。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS = {
    "title",
    "doc_type",
    "status",
    "implementation_status",
    "version",
    "created",
    "updated",
    "owner",
}
DOC_TYPES = {
    "plan",
    "architecture",
    "matrix",
    "reference",
    "adr",
    "index",
    "archive-index",
    "governance",
    "test",
}
STATUSES = {"draft", "current", "superseded", "archived"}
IMPLEMENTATION_STATUSES = {
    "proposed",
    "in_progress",
    "implemented",
    "verified",
    "not_applicable",
}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
JSON_PATTERN = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


class ChineseArgumentParser(argparse.ArgumentParser):
    """Keep this repository's developer CLI messages in Chinese."""

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法：", 1)

    def format_help(self) -> str:
        help_text = super().format_help()
        help_text = help_text.replace("usage:", "用法：", 1)
        help_text = help_text.replace("options:", "选项：", 1)
        return help_text.replace("optional arguments:", "选项：", 1)

    def error(self, message: str) -> None:
        translated = message.replace("unrecognized arguments:", "无法识别的参数：")
        translated = translated.replace(
            "argument --root: expected one argument",
            "参数 --root 需要一个路径",
        )
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: 参数错误：{translated}\n")


def markdown_files(root: Path) -> list[Path]:
    files = [root / "README.md", root / "AGENTS.md", root / "CLAUDE.md"]
    files.extend(sorted((root / "docs").rglob("*.md")))
    files.extend(sorted((root / ".claude" / "skills").rglob("*.md")))
    return files


def frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    for line in content[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def check_header(path: Path, content: str) -> list[str]:
    fields = frontmatter(content)
    errors = []
    missing = REQUIRED_FIELDS - fields.keys()
    if missing:
        errors.append(f"missing frontmatter fields {sorted(missing)}")
    if fields.get("doc_type") not in DOC_TYPES:
        errors.append(f"invalid doc_type {fields.get('doc_type')!r}")
    if fields.get("status") not in STATUSES:
        errors.append(f"invalid status {fields.get('status')!r}")
    if fields.get("implementation_status") not in IMPLEMENTATION_STATUSES:
        errors.append(
            "invalid implementation_status "
            f"{fields.get('implementation_status')!r}"
        )
    return [f"{path}: {error}" for error in errors]


def check_links(path: Path, content: str, root: Path) -> list[str]:
    errors = []
    for target in LINK_PATTERN.findall(content):
        target = target.strip().strip("<>")
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        local_target = target.split("#", 1)[0]
        if local_target and not (path.parent / local_target).resolve().exists():
            errors.append(f"{path.relative_to(root)}: missing link target {target}")
    return errors


def check_json(path: Path, content: str) -> list[str]:
    errors = []
    for index, block in enumerate(JSON_PATTERN.findall(content), 1):
        try:
            json.loads(block)
        except json.JSONDecodeError as error:
            errors.append(f"{path}: JSON block {index}: {error}")
    return errors


def validate(root: Path) -> tuple[list[Path], list[str]]:
    files = markdown_files(root)
    errors = []
    for path in files:
        if not path.exists():
            errors.append(f"{path}: required file is missing")
            continue
        content = path.read_text(encoding="utf-8")
        if path.is_relative_to(root / "docs"):
            errors.extend(check_header(path.relative_to(root), content))
        errors.extend(check_links(path, content, root))
        errors.extend(check_json(path.relative_to(root), content))
    claude_file = root / "CLAUDE.md"
    if claude_file.exists():
        lines = claude_file.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "@AGENTS.md":
            errors.append("CLAUDE.md: line 1 must import @AGENTS.md")
    if not (root / ".claude/skills/acceptance/SKILL.md").exists():
        errors.append(".claude/skills/acceptance/SKILL.md: required file is missing")
    return files, errors


def project_root(value: Path | None, parser: argparse.ArgumentParser) -> Path:
    root = (value or Path(__file__).resolve().parents[1]).resolve()
    if not root.is_dir():
        parser.error(f"--root 目录不存在：{root}")
    markers = (root / "README.md", root / "docs/GOVERNANCE.md")
    if not all(marker.exists() for marker in markers):
        parser.error(f"--root 不是有效的 mynews 项目目录：{root}")
    return root


def main() -> int:
    parser = ChineseArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    parser.add_argument(
        "--root",
        type=Path,
        metavar="路径",
        help="仓库根目录；默认使用脚本所在项目",
    )
    args = parser.parse_args()
    root = project_root(args.root, parser)
    files, errors = validate(root)
    print(f"checked_markdown_files={len(files)}")
    print(f"errors={len(errors)}")
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
