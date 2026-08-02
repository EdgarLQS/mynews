from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect.sh"


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _run_script(
    tmp_path: Path,
    *arguments: str,
    uv: Path | None = None,
    launchctl: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(tmp_path / "home"),
            "MYNEWS_LOG_DIR": str(tmp_path / "logs"),
            "MYNEWS_LAUNCHD_DOMAIN": "gui/501",
        }
    )
    if uv is not None:
        environment["MYNEWS_UV_BIN"] = str(uv)
    if launchctl is not None:
        environment["MYNEWS_LAUNCHCTL_BIN"] = str(launchctl)
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_help_is_chinese_and_lists_launchd_operations(tmp_path: Path) -> None:
    result = _run_script(tmp_path, "--help")

    assert result.returncode == 0
    assert "用法：" in result.stdout
    assert "render-plist" in result.stdout
    assert "install" in result.stdout
    assert "uninstall" in result.stdout


def test_collect_fixes_cwd_passes_args_and_proxy_without_logging_secret(
    tmp_path: Path,
) -> None:
    uv = _write_executable(
        tmp_path / "fake-uv",
        """
printf 'cwd=%s\\n' "$PWD"
printf 'args=%s\\n' "$*"
if [ "${HTTP_PROXY-}" = "http://proxy.example:8080" ]; then
  printf 'proxy-forwarded=true\\n'
fi
printf 'OPENAI_API_KEY=%s\\n' "${OPENAI_API_KEY-}"
exit "${FAKE_UV_EXIT:-0}"
""",
    )
    result = _run_script(
        tmp_path,
        "--days",
        "7",
        "--source",
        "deepseek",
        "--source",
        "google-gemini",
        uv=uv,
        extra_env={
            "HTTP_PROXY": "http://proxy.example:8080",
            "OPENAI_API_KEY": "test-secret-value",
            "FAKE_UV_EXIT": "3",
        },
    )

    assert result.returncode == 3
    assert f"cwd={ROOT}" in result.stdout
    assert "collect --days 7 --source deepseek --source google-gemini" in result.stdout
    assert "proxy-forwarded=true" in result.stdout
    assert "test-secret-value" not in result.stdout
    log_text = (tmp_path / "logs" / "collect.log").read_text(encoding="utf-8")
    assert "test-secret-value" not in log_text
    assert "[REDACTED_SECRET]" in log_text


def test_rendered_plist_is_absolute_and_scheduled_at_beijing_0930(
    tmp_path: Path,
) -> None:
    plist = tmp_path / "home" / "Library" / "LaunchAgents" / "com.mynews.collect.plist"
    result = _run_script(tmp_path, "render-plist", "--output", str(plist))

    assert result.returncode == 0
    assert plist.is_file()
    lint = subprocess.run(
        ["/usr/bin/plutil", "-lint", str(plist)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert lint.returncode == 0, lint.stderr
    payload = plist.read_text(encoding="utf-8")
    assert "<key>Label</key>" in payload
    assert "<string>com.mynews.collect</string>" in payload
    assert "<key>Hour</key>" in payload
    assert "<integer>9</integer>" in payload
    assert "<key>Minute</key>" in payload
    assert "<integer>30</integer>" in payload
    assert "<string>Asia/Shanghai</string>" in payload
    assert str(ROOT / "scripts" / "collect.sh") in payload
    assert str(ROOT / "logs") in payload


def test_launchd_operations_are_idempotent_and_use_exact_label(
    tmp_path: Path,
) -> None:
    state = tmp_path / "launchd-state"
    calls = tmp_path / "launchctl-calls"
    launchctl = _write_executable(
        tmp_path / "fake-launchctl",
        """
printf '%s\\n' "$*" >> "$FAKE_LAUNCHCTL_CALLS"
case "$1" in
  print)
    if test -f "$FAKE_LAUNCHCTL_STATE"; then
      exit 0
    fi
    exit "${FAKE_LAUNCHCTL_MISSING_CODE:-1}"
    ;;
  bootstrap)
    touch "$FAKE_LAUNCHCTL_STATE"
    ;;
  bootout)
    rm -f "$FAKE_LAUNCHCTL_STATE"
    ;;
  *)
    exit 2
    ;;
esac
""",
    )
    environment = {
    "FAKE_LAUNCHCTL_STATE": str(state),
    "FAKE_LAUNCHCTL_CALLS": str(calls),
    "FAKE_LAUNCHCTL_MISSING_CODE": "113",
}

    first = _run_script(
        tmp_path, "install", launchctl=launchctl, extra_env=environment
    )
    second = _run_script(
        tmp_path, "install", launchctl=launchctl, extra_env=environment
    )
    status = _run_script(
        tmp_path, "status", launchctl=launchctl, extra_env=environment
    )
    removed = _run_script(
        tmp_path, "uninstall", launchctl=launchctl, extra_env=environment
    )
    removed_again = _run_script(
        tmp_path, "uninstall", launchctl=launchctl, extra_env=environment
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert status.returncode == 0
    assert removed.returncode == 0
    assert removed_again.returncode == 0
    assert not state.exists()
    assert not (
        tmp_path / "home" / "Library" / "LaunchAgents" / "com.mynews.collect.plist"
    ).exists()
    call_text = calls.read_text(encoding="utf-8")
    assert "print gui/501/com.mynews.collect" in call_text
    assert "bootstrap gui/501 " in call_text
    assert "bootout gui/501/com.mynews.collect" in call_text


def test_collect_does_not_call_launchctl_implicitly(tmp_path: Path) -> None:
    uv = _write_executable(tmp_path / "fake-uv", "exit 0")
    launchctl_marker = tmp_path / "launchctl-called"
    launchctl = _write_executable(
        tmp_path / "launchctl-must-not-run",
        f"touch '{launchctl_marker}'\nexit 99",
    )

    result = _run_script(
        tmp_path,
        "--help",
        uv=uv,
        launchctl=launchctl,
    )

    assert result.returncode == 0
    assert not launchctl_marker.exists()


@pytest.mark.parametrize("action", ["render-plist", "install", "status", "uninstall"])
def test_launchd_actions_require_absolute_home(tmp_path: Path, action: str) -> None:
    environment = {"HOME": "relative-home"}
    result = _run_script(tmp_path, action, extra_env=environment)

    assert result.returncode == 2
    assert "HOME" in result.stderr
