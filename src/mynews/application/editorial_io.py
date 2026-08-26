"""Editorial 输出的通用原子写入辅助。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mynews.storage.artifact_committer import (
    ArtifactCommitError,
    ArtifactCommitter,
    ArtifactWrite,
)


def atomic_write_text(path: Path, content: str) -> None:
    """在目标文件所在目录写入并原子替换文本。"""

    try:
        ArtifactCommitter().commit((ArtifactWrite.text(path, content),))
    except ArtifactCommitError as error:
        cause = error.cause
        if isinstance(cause, OSError):
            raise OSError(str(cause)) from error
        raise OSError(str(error)) from error


def atomic_write_json(
    path: Path, payload: Any, *, sort_keys: bool = True
) -> None:
    """以稳定格式原子写入 JSON。"""

    try:
        ArtifactCommitter().commit(
            (ArtifactWrite.json(path, payload, sort_keys=sort_keys),)
        )
    except ArtifactCommitError as error:
        cause = error.cause
        if isinstance(cause, OSError):
            raise OSError(str(cause)) from error
        raise OSError(str(error)) from error


__all__ = ["atomic_write_json", "atomic_write_text"]
