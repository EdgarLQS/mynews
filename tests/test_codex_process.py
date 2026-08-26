from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from mynews.domain.models import ReasoningEffort
from mynews.infrastructure.codex_process import (
    CodexProcessAdapter,
    CodexProcessError,
    CodexProcessRequest,
)


def _request(**overrides: object) -> CodexProcessRequest:
    values: dict[str, object] = {
        "prompt": "structured prompt",
        "model": "test-model",
        "timeout": 2.5,
        "reasoning_effort": "medium",
        "output_schema": {"type": "object"},
    }
    values.update(overrides)
    return CodexProcessRequest(**values)  # type: ignore[arg-type]


def test_process_adapter_owns_command_schema_temp_dir_and_output_reading() -> None:
    captured: dict[str, object] = {}

    def run(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: float,
        check: bool,
        shell: bool,
        cwd: str,
    ) -> SimpleNamespace:
        captured.update(
            {
                "command": command,
                "input": input,
                "text": text,
                "capture_output": capture_output,
                "timeout": timeout,
                "check": check,
                "shell": shell,
                "cwd": cwd,
            }
        )
        schema_path = Path(command[command.index("--output-schema") + 1])
        captured["schema"] = schema_path.read_text(encoding="utf-8")
        output_path = Path(
            command[command.index("--output-last-message") + 1]
        )
        output_path.write_text('{"ok":true}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    output = CodexProcessAdapter(process_runner=run).run(_request())

    assert output == '{"ok":true}'
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:2] == ["codex", "exec"]
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("-c") + 1] == (
        'model_reasoning_effort="medium"'
    )
    assert captured["schema"] == '{"type": "object"}'
    assert captured["input"] == "structured prompt"
    assert captured["timeout"] == 2.5
    assert captured["shell"] is False
    assert captured["check"] is False
    assert captured["cwd"]
    assert not Path(str(captured["cwd"])).exists()


@pytest.mark.parametrize(
    ("process_runner", "code"),
    [
        (
            lambda command, **kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(command, 2.5)
            ),
            "codex_timeout",
        ),
        (
            lambda command, **kwargs: (_ for _ in ()).throw(
                OSError("missing codex")
            ),
            "codex_unavailable",
        ),
    ],
)
def test_process_adapter_normalizes_process_failures(
    process_runner: object,
    code: str,
) -> None:
    adapter = CodexProcessAdapter(process_runner=process_runner)  # type: ignore[arg-type]

    with pytest.raises(CodexProcessError) as raised:
        adapter.run(_request())

    assert raised.value.code == code


def test_process_adapter_reports_nonzero_and_missing_output() -> None:
    def failed(command: list[str], **kwargs: object) -> SimpleNamespace:
        del command
        del kwargs
        return SimpleNamespace(returncode=7, stderr="bad response")

    with pytest.raises(CodexProcessError) as raised:
        CodexProcessAdapter(process_runner=failed).run(_request())
    assert raised.value.code == "codex_failed"
    assert str(raised.value) == "bad response"

    def missing(command: list[str], **kwargs: object) -> SimpleNamespace:
        del command
        del kwargs
        return SimpleNamespace(returncode=0, stderr="")

    with pytest.raises(CodexProcessError) as raised:
        CodexProcessAdapter(process_runner=missing).run(_request())
    assert raised.value.code == "codex_missing_output"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", ""),
        ("timeout", 0),
        ("reasoning_effort", "invalid"),
    ],
)
def test_process_request_rejects_invalid_runtime_options(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        _request(**{field: value})


def test_reasoning_effort_type_remains_the_existing_contract() -> None:
    effort: ReasoningEffort = "medium"
    assert _request(reasoning_effort=effort).reasoning_effort == "medium"
