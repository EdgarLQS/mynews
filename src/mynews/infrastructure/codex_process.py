"""共享的结构化 Codex CLI 进程 Adapter。"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from mynews.domain.models import ReasoningEffort

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


class CodexProcessError(RuntimeError):
    """Codex 进程机制失败；领域调用方负责决定如何回退。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CodexProcessRequest:
    """一次结构化 Codex 进程请求，不包含领域 prompt 或响应模型。"""

    prompt: str
    model: str
    timeout: float
    reasoning_effort: ReasoningEffort
    output_schema: Mapping[str, object]
    executable: str = "codex"
    temp_prefix: str = "mynews-codex-"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Codex 模型不能为空")
        if self.timeout <= 0:
            raise ValueError("Codex 超时必须是正数")
        if self.reasoning_effort not in {
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("Codex 推理强度无效")
        if not self.executable.strip():
            raise ValueError("Codex 可执行文件不能为空")
        if not self.temp_prefix:
            raise ValueError("Codex 临时目录前缀不能为空")


class CodexProcessAdapter:
    """统一临时目录、Schema、命令、超时、返回码和结构化输出读取。"""

    def __init__(self, process_runner: ProcessRunner | None = None) -> None:
        self._process_runner = process_runner or cast(ProcessRunner, subprocess.run)

    def run(self, request: CodexProcessRequest) -> str:
        schema = _serialize_schema(request.output_schema)
        with tempfile.TemporaryDirectory(prefix=request.temp_prefix) as directory:
            workdir = Path(directory)
            schema_path = workdir / "schema.json"
            output_path = workdir / "output.json"
            schema_path.write_text(schema, encoding="utf-8")
            completed = self._run_process(request, directory, schema_path, output_path)
            if completed.returncode != 0:
                raise CodexProcessError(
                    "codex_failed",
                    completed.stderr.strip() or "Codex 返回失败状态",
                )
            return _read_output(output_path)

    def _run_process(
        self,
        request: CodexProcessRequest,
        directory: str,
        schema_path: Path,
        output_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._process_runner(
                _command(request, schema_path, output_path),
                input=request.prompt,
                text=True,
                capture_output=True,
                timeout=request.timeout,
                check=False,
                shell=False,
                cwd=directory,
            )
        except subprocess.TimeoutExpired as error:
            raise CodexProcessError("codex_timeout", "Codex 调用超时") from error
        except OSError as error:
            raise CodexProcessError("codex_unavailable", str(error)) from error


def _serialize_schema(schema: Mapping[str, object]) -> str:
    try:
        return json.dumps(schema, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise CodexProcessError(
            "codex_invalid_schema", "Codex 输出 Schema 无法序列化"
        ) from error


def _command(
    request: CodexProcessRequest,
    schema_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        request.executable,
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--model",
        request.model,
        "-c",
        f'model_reasoning_effort="{request.reasoning_effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]


def _read_output(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise CodexProcessError(
            "codex_missing_output",
            "Codex 没有返回结构化输出",
        ) from error


__all__ = [
    "CodexProcessAdapter",
    "CodexProcessError",
    "CodexProcessRequest",
]
