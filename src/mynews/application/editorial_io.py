"""Editorial 输出的通用原子写入辅助。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str) -> None:
    """在目标文件所在目录写入并原子替换文本。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: Any) -> None:
    """以稳定格式原子写入 JSON。"""

    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write_text(path, content + "\n")


__all__ = ["atomic_write_json", "atomic_write_text"]
