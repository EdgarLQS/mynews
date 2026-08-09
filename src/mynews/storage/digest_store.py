"""Digest 历史文件、latest JSON 和 Markdown 的原子输出。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from mynews.domain.models import Digest, DigestItem


class DigestStoreError(RuntimeError):
    """Digest 文件无法安全读取、生成或恢复。"""


class DigestFileStore:
    """把一次 Digest 的三个文件作为同一提交单元写入输出目录。"""

    def __init__(self, out_dir: Path | str) -> None:
        self._root = Path(out_dir)
        self._history = self._root / "digests"
        self._latest_json = self._root / "digest-latest.json"
        self._latest_markdown = self._root / "digest-latest.md"

    @property
    def latest_json_path(self) -> Path:
        return self._latest_json

    def load_latest(self) -> Digest | None:
        if not self._latest_json.exists():
            return None
        try:
            return Digest.model_validate_json(
                self._latest_json.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise DigestStoreError(
                f"无法读取上一期 Digest：{self._latest_json}"
            ) from error

    def write(self, digest: Digest) -> tuple[Path, Path, Path]:
        validated = Digest.model_validate(digest)
        history_path = self._history / f"{_safe_filename(validated.digest_id)}.json"
        if history_path.exists():
            raise DigestStoreError(f"Digest 历史文件已存在：{history_path.name}")
        payload = validated.model_dump(mode="json")
        writes = [
            (history_path, _json_bytes(payload)),
            (self._latest_json, _json_bytes(payload)),
            (self._latest_markdown, render_digest(validated).encode("utf-8")),
        ]
        _transactional_write(writes)
        return history_path, self._latest_json, self._latest_markdown


def render_digest(digest: Digest) -> str:
    """渲染可读中文简报，不重新计算事实或核验状态。"""
    lines = [
        "# mynews 情报简报",
        "",
        f"- Digest：`{digest.digest_id}`",
        f"- Run：`{digest.run_id}`",
        f"- 状态：`{digest.status}`",
        f"- 条目：主榜 {len(digest.main_items)}，线索观察 {len(digest.lead_items)}",
        "",
    ]
    lines.extend(_section("主榜", digest.main_items, verified=True))
    lines.extend(_section("线索观察", digest.lead_items, verified=False))
    if digest.summary_errors:
        lines.extend(["## 摘要状态", ""])
        lines.extend(f"- `{error}`" for error in digest.summary_errors)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _section(title: str, items: list[DigestItem], *, verified: bool) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        return lines + ["- 无", ""]
    for item in items:
        lines.extend(
            [
                f"### {item.title_zh}",
                "",
                item.summary_zh,
                "",
                f"- 影响判断：{item.impact_zh}",
                f"- 生命周期：`{item.lifecycle}`",
                f"- 排序分：`{item.rank_score:.2f}`",
                "- 核验："
                f"`{item.verification_status}`；原因：`{item.verification_reason}`",
            ]
        )
        if item.summary_reason:
            lines.append(
                f"- 摘要：`{item.summary_status}`；原因：`{item.summary_reason}`"
            )
        if not verified and item.verification_retry is not None:
            retry = item.verification_retry
            lines.append(
                "- 重试："
                f"`{retry.status}`，{retry.attempt_count}/{retry.max_attempts}；"
                f"原因：`{retry.last_reason}`"
            )
            if retry.next_retry_at is not None:
                lines.append(f"- 下次重试：`{retry.next_retry_at.isoformat()}`")
            if retry.terminal_reason is not None:
                lines.append(f"- 终止原因：`{retry.terminal_reason}`")
        elif not verified:
            lines.append("- 重试：`not_scheduled`；当前没有可持久化的重试状态")
        if item.evidence_refs:
            lines.append("- 证据引用：")
            lines.extend(
                f"  - {ref.url}：{ref.excerpt}" for ref in item.evidence_refs
            )
        lines.append("")
    return lines


def _transactional_write(writes: list[tuple[Path, bytes]]) -> None:
    previous = {
        path: path.read_bytes() if path.exists() else None
        for path, _ in writes
    }
    staged: dict[Path, str] = {}
    try:
        for path, payload in writes:
            staged[path] = _stage_bytes(path, payload)
        for path, _ in writes:
            temporary = staged[path]
            os.replace(temporary, path)
            staged.pop(path)
    except Exception as error:
        rollback_errors: list[Exception] = []
        for path, _ in reversed(writes):
            try:
                old = previous[path]
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    _restore_bytes(path, old)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
        message = (
            "Digest 提交失败且无法完整恢复先前状态"
            if rollback_errors
            else "Digest 提交失败，已恢复先前状态"
        )
        raise DigestStoreError(message) from error
    finally:
        for temporary in staged.values():
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _stage_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.unlink(handle.name)
        except FileNotFoundError:
            pass
        raise
    return handle.name


def _restore_bytes(path: Path, payload: bytes) -> None:
    temporary = _stage_bytes(path, payload)
    try:
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_filename(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(":", "-")


__all__ = ["DigestFileStore", "DigestStoreError", "render_digest"]
