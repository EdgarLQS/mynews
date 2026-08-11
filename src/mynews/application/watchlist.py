"""离线校验和渲染人工来源清单。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)

from mynews.application.output_safety import ensure_safe_output


class WatchlistItem(BaseModel):
    """人工清单 1.0 的单项契约。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: AnyHttpUrl
    role: Literal["primary", "monitor", "manual"]
    note: str = Field(min_length=1)

    @field_validator("id", "name", "note")
    @classmethod
    def require_clean_text(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("watchlist 文本字段不能为空或包含首尾空白")
        return value

    @field_validator("url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("watchlist URL 必须使用 HTTPS")
        return value


def load_watchlist(path: Path) -> tuple[WatchlistItem, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = TypeAdapter(list[WatchlistItem]).validate_python(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"无法读取人工清单：{path.name}") from error
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("人工清单 ID 不能重复")
    return tuple(sorted(items, key=lambda item: item.id))


def render_watchlist(items: tuple[WatchlistItem, ...]) -> str:
    payload = [item.model_dump(mode="json") for item in items]
    ensure_safe_output(payload, root="watchlist")
    lines = ["# mynews 人工来源清单", "", "版本：`1.0`", ""]
    if not items:
        return "\n".join(lines + ["- 无", ""])
    for item in items:
        lines.extend(
            [
                f"## {item.name}",
                "",
                f"- ID：`{item.id}`",
                f"- 角色：`{item.role}`",
                f"- 官方入口：{item.url}",
                f"- 备注：{item.note}",
                "",
            ]
        )
    return "\n".join(lines)


def write_watchlist(items: tuple[WatchlistItem, ...], path: Path) -> None:
    text = render_watchlist(items)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    finally:
        try:
            os.unlink(handle.name)
        except FileNotFoundError:
            pass


__all__ = ["WatchlistItem", "load_watchlist", "render_watchlist", "write_watchlist"]
