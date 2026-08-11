from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

import mynews.cli as cli
from mynews.application.output_safety import OutputSafetyError
from mynews.application.report import render_report, write_report
from mynews.domain.models import Candidate, CollectionRequest, NewsItem, RunReport
from mynews.domain.normalization import normalize_source_role
from mynews.sources.external import ExternalPluginLoader
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceContext,
    SourceHealth,
    SourceMetadata,
)
from mynews.sources.registry import SourceRegistry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, tzinfo=UTC)
REQUEST = CollectionRequest.model_validate(
    {"from": "2026-08-10T00:00:00Z", "to": "2026-08-12T00:00:00Z"}
)


def test_new_source_roles_are_supported_without_lowering_evidence_boundary() -> None:
    assert [
        normalize_source_role(role)
        for role in ("research", "incident", "benchmark")
    ] == [
        "research",
        "incident",
        "benchmark",
    ]


@dataclass
class FixturePlugin:
    metadata: SourceMetadata

    def collect(self, context: SourceContext) -> SourceBatch:
        del context
        candidate = Candidate(
            source_id=self.metadata.source_id,
            title_original=f"{self.metadata.source_id} AI update",
            url="https://example.test/update",
            published_at=NOW,
        )
        return SourceBatch(self.metadata.source_id, (candidate,))

    def probe(self, context: ProbeContext) -> SourceHealth:
        del context
        return SourceHealth(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            health="healthy",
            fetched_count=1,
            accepted_count=1,
            duration_ms=0,
            checked_at=NOW,
        )


@dataclass
class FakeEntryPoint:
    name: str
    value: str
    factory: object

    def load(self) -> object:
        return self.factory


def _metadata(source_id: str, role: str = "primary") -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        name=source_id,
        role=role,
        homepage="https://example.test/",
        official_domains=("example.test",),
        capabilities=("fixture",),
    )


def test_with_plugin_appends_to_all_builtin_selection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    builtin = FixturePlugin(_metadata("builtin"))
    plugin = FixturePlugin(_metadata("external"))
    registry = SourceRegistry([builtin])
    loader = ExternalPluginLoader(
        [FakeEntryPoint("external-fixture", "fixture:factory", lambda: plugin)]
    )
    monkeypatch.setattr(cli, "ExternalPluginLoader", lambda: loader)

    assert cli.main(
        ["collect", "--with-plugin", "external-fixture"], registry=registry
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"][0]["source_id"] == "builtin"
    assert payload["sources"][1]["source_id"] == "external"
    assert payload["candidates"][1]["source_id"] == "external"


def test_with_plugin_keeps_source_filter_and_records_both_ids(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    builtin = FixturePlugin(_metadata("builtin"))
    plugin = FixturePlugin(_metadata("external"))
    registry = SourceRegistry([builtin])
    loader = ExternalPluginLoader(
        [FakeEntryPoint("external-fixture", "fixture:factory", lambda: plugin)]
    )
    monkeypatch.setattr(cli, "ExternalPluginLoader", lambda: loader)

    assert cli.main(
        ["collect", "--source", "builtin", "--with-plugin", "external-fixture"],
        registry=registry,
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [item["source_id"] for item in payload["sources"]] == [
        "builtin",
        "external",
    ]


def test_with_plugin_probe_includes_builtin_and_external_health(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    builtin = FixturePlugin(_metadata("builtin"))
    plugin = FixturePlugin(_metadata("external"))
    registry = SourceRegistry([builtin])
    loader = ExternalPluginLoader(
        [FakeEntryPoint("external-fixture", "fixture:factory", lambda: plugin)]
    )
    monkeypatch.setattr(cli, "ExternalPluginLoader", lambda: loader)

    assert cli.main(
        ["probe", "--with-plugin", "external-fixture"], registry=registry
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [item["source_id"] for item in payload["sources"]] == [
        "builtin",
        "external",
    ]


def test_plugin_and_with_plugin_are_mutually_exclusive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["collect", "--plugin", "one", "--with-plugin", "two"])

    assert raised.value.code == 2
    assert "不能与" in capsys.readouterr().err


def test_report_rejects_sensitive_values_without_echoing_them() -> None:
    report = RunReport.model_validate_json(
        (ROOT / "tests/fixtures/run-report-v1.json").read_text(encoding="utf-8")
    )
    item = NewsItem(
        id="event-1",
        event_key="event-1",
        event_type="product_update",
        title_original="Fixture update",
        language_original="en",
        title_zh="Fixture update",
        summary_zh="Fixture summary",
        first_seen_at=NOW,
        heat_score=1,
        relevance_score=1,
        discovery_sources=["fixture"],
        verification_reason="verification_pending",
        content_hash="sha256:fixture",
        canonical_url="https://example.test/update?token=secret-value",
    )
    unsafe = report.model_copy(update={"items": [item]})

    with pytest.raises(OutputSafetyError) as raised:
        render_report(unsafe)

    assert "report.items[0].canonical_url" in str(raised.value)
    assert "secret-value" not in str(raised.value)


def test_report_write_is_atomic_and_preserves_old_output_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = RunReport.model_validate_json(
        (ROOT / "tests/fixtures/run-report-v1.json").read_text(encoding="utf-8")
    )
    path = tmp_path / "report.md"
    path.write_text("old report\n", encoding="utf-8")

    def fail_replace(source: str, destination: Path) -> None:
        del source, destination
        raise OSError("replace blocked")

    monkeypatch.setattr("mynews.application.report.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace blocked"):
        write_report(report, path)

    assert path.read_text(encoding="utf-8") == "old report\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_watchlist_command_renders_deterministic_markdown_without_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    watchlist = tmp_path / "watchlist.json"
    watchlist.write_text(
        json.dumps(
            [
                {
                    "id": "zeta",
                    "name": "Zeta",
                    "url": "https://zeta.example/",
                    "role": "manual",
                    "note": "Check official updates",
                },
                {
                    "id": "alpha",
                    "name": "Alpha",
                    "url": "https://alpha.example/",
                    "role": "manual",
                    "note": "Check release notes",
                },
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "watchlist.md"

    assert cli.main(["watchlist", "--file", str(watchlist), "--out", str(output)]) == 0
    first = output.read_text(encoding="utf-8")
    message = capsys.readouterr().out
    assert message.strip() == "人工清单已写入"
    assert str(output) not in message
    assert cli.main(["watchlist", "--file", str(watchlist), "--out", str(output)]) == 0
    second = output.read_text(encoding="utf-8")

    assert first == second
    assert first.index("Alpha") < first.index("Zeta")
    assert not (tmp_path / "output").exists()


def test_expanded_script_forwards_fixed_plugins_without_shell_reinterpretation(
    tmp_path: Path,
) -> None:
    uv = tmp_path / "fake-uv"
    calls = tmp_path / "calls"
    uv.write_text(
        "#!/bin/sh\nset -eu\nprintf '%s\\n' \"$*\" >> \"$FAKE_CALLS\"\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "MYNEWS_UV_BIN": str(uv),
            "FAKE_CALLS": str(calls),
            "MYNEWS_LOG_DIR": str(tmp_path / "logs"),
            "TMPDIR": "/tmp",
        }
    )

    result = subprocess.run(
        [
            str(ROOT / "scripts/collect-expanded.sh"),
            "--days",
            "7",
            "--verification-budget",
            "10",
            "--digest",
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    command = calls.read_text(encoding="utf-8").splitlines()[0]
    assert "collect --days 7 --verification-budget 10" in command
    assert command.count("--with-plugin") == 15
    assert "openai-news" in command
    assert "paperswithcode-daily" in command
