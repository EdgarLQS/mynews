"""统一的同目录文件暂存、替换和回滚提交模块。"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CommitPhase = Literal["validate", "stage", "replace"]
RollbackStatus = Literal["not_needed", "succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class ArtifactWrite:
    """一个待提交文件的最终字节内容。"""

    path: Path
    content: bytes

    @classmethod
    def text(cls, path: Path, content: str) -> ArtifactWrite:
        return cls(path, content.encode("utf-8"))

    @classmethod
    def json(
        cls,
        path: Path,
        payload: object,
        *,
        sort_keys: bool = False,
    ) -> ArtifactWrite:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=sort_keys,
        )
        return cls.text(path, content + "\n")


class ArtifactCommitError(RuntimeError):
    """文件提交失败，并保留失败阶段、目标和恢复结果。"""

    def __init__(
        self,
        message: str,
        *,
        phase: CommitPhase,
        target_path: Path | None,
        rollback_status: RollbackStatus,
        rollback_errors: tuple[str, ...] = (),
        cause: Exception,
    ) -> None:
        self.phase = phase
        self.target_path = target_path
        self.rollback_status = rollback_status
        self.rollback_errors = rollback_errors
        self.cause = cause
        detail = f"{message}；阶段={phase}；回滚={rollback_status}"
        if target_path is not None:
            detail += f"；目标={target_path}"
        if rollback_errors:
            detail += f"；回滚错误={'; '.join(rollback_errors)}"
        super().__init__(detail)


class ArtifactCommitter:
    """把一个或多个文件作为同一批次安全提交。"""

    def commit(self, writes: Sequence[ArtifactWrite]) -> None:
        batch = tuple(writes)
        self._validate(batch)
        if not batch:
            return

        previous = self._snapshot(batch)
        staged: dict[Path, str] = {}
        try:
            for write in batch:
                staged[write.path] = self._stage(write)
        except Exception as error:
            self._cleanup(staged.values())
            raise ArtifactCommitError(
                "文件暂存失败",
                phase="stage",
                target_path=write.path,
                rollback_status="not_needed",
                cause=error,
            ) from error

        replaced: list[Path] = []
        target_path: Path | None = None
        try:
            for write in batch:
                target_path = write.path
                temporary = staged[write.path]
                os.replace(temporary, write.path)
                staged.pop(write.path)
                replaced.append(write.path)
        except Exception as error:
            rollback_errors = self._rollback(replaced, previous)
            rollback_status: RollbackStatus = (
                "failed"
                if rollback_errors
                else "succeeded"
                if replaced
                else "not_needed"
            )
            raise ArtifactCommitError(
                "文件替换失败",
                phase="replace",
                target_path=target_path,
                rollback_status=rollback_status,
                rollback_errors=tuple(rollback_errors),
                cause=error,
            ) from error
        finally:
            self._cleanup(staged.values())

    @staticmethod
    def _validate(writes: Sequence[ArtifactWrite]) -> None:
        seen: set[Path] = set()
        for write in writes:
            if write.path in seen:
                cause = ValueError("同一批次不能重复提交同一路径")
                raise ArtifactCommitError(
                    "文件提交参数无效",
                    phase="validate",
                    target_path=write.path,
                    rollback_status="not_needed",
                    cause=cause,
                ) from cause
            seen.add(write.path)

    @staticmethod
    def _snapshot(writes: Sequence[ArtifactWrite]) -> dict[Path, bytes | None]:
        previous: dict[Path, bytes | None] = {}
        for write in writes:
            try:
                previous[write.path] = (
                    write.path.read_bytes() if write.path.exists() else None
                )
            except Exception as error:
                raise ArtifactCommitError(
                    "文件提交前无法读取旧文件",
                    phase="stage",
                    target_path=write.path,
                    rollback_status="not_needed",
                    cause=error,
                ) from error
        return previous

    @staticmethod
    def _stage(write: ArtifactWrite) -> str:
        write.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=write.path.parent,
            prefix=f".{write.path.name}.",
            suffix=".tmp",
            delete=False,
        )
        try:
            with handle:
                handle.write(write.content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            Path(handle.name).unlink(missing_ok=True)
            raise
        return handle.name

    def _rollback(
        self,
        replaced: Sequence[Path],
        previous: dict[Path, bytes | None],
    ) -> list[str]:
        errors: list[str] = []
        for path in reversed(replaced):
            try:
                old = previous[path]
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    temporary = self._stage(ArtifactWrite(path, old))
                    try:
                        os.replace(temporary, path)
                    finally:
                        Path(temporary).unlink(missing_ok=True)
            except Exception as error:
                errors.append(f"{path}: {error}")
        return errors

    @staticmethod
    def _cleanup(temporary_paths: Iterable[str]) -> None:
        for temporary in temporary_paths:
            Path(temporary).unlink(missing_ok=True)


__all__ = [
    "ArtifactCommitError",
    "ArtifactCommitter",
    "ArtifactWrite",
]
