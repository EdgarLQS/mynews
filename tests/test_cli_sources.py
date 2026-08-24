from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

import mynews.cli as cli
from mynews.cli import main
from mynews.domain.models import Candidate, SourceError
from mynews.sources.protocol import (
    ProbeContext,
    SourceCollection,
    SourceContext,
    SourceHealth,
)
from mynews.storage.json_store import JsonNewsStore


class FakeRegistry:
    def __init__(self, health: tuple[SourceHealth, ...]) -> None:
        self.http = object()
        self.health = health
        self.probe_calls: list[tuple[str, ...] | None] = []
        self.collect_calls: list[tuple[str, ...] | None] = []

    def probe(
        self, context: ProbeContext, source_ids: Sequence[str] | None = None
    ) -> tuple[SourceHealth, ...]:
        self.probe_calls.append(tuple(source_ids) if source_ids is not None else None)
        return self.health

    def collect_all(
        self, context: SourceContext, source_ids: Sequence[str] | None = None
    ) -> SourceCollection:
        self.collect_calls.append(tuple(source_ids) if source_ids is not None else None)
        candidate = Candidate(
            source_id="qwen",
            title_original="Fixture candidate",
            url="https://qwenlm.github.io/blog/fixture",
        )
        return SourceCollection((candidate,), self.health)


def healthy(source_id: str = "qwen") -> SourceHealth:
    return SourceHealth(
        source_id=source_id,
        role="primary",
        health="healthy",
        fetched_count=1,
        accepted_count=1,
        duration_ms=2,
        checked_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


def test_probe_outputs_structured_health_and_honors_source_filter(capsys) -> None:
    registry = FakeRegistry((healthy(),))

    exit_code = main(["probe", "--source", "qwen"], registry=registry)

    assert exit_code == 0
    assert registry.probe_calls == [("qwen",)]
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "complete"
    assert output["sources"][0]["source_id"] == "qwen"
    assert output["sources"][0]["checked_at"] == "2026-08-02T00:00:00Z"


def test_collect_outputs_raw_candidates_without_store(capsys) -> None:
    registry = FakeRegistry((healthy(),))

    exit_code = main(["collect", "--source", "qwen"], registry=registry)

    assert exit_code == 0
    assert registry.collect_calls == [("qwen",)]
    output = json.loads(capsys.readouterr().out)
    assert output["candidates"][0]["title_original"] == "Fixture candidate"
    assert output["sources"][0]["health"] == "healthy"
    assert "run_id" not in output


def test_collect_without_injected_registry_uses_compatibility_registry(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    registry = FakeRegistry((healthy(),))
    monkeypatch.setattr(cli, "default_registry", lambda: registry)

    assert cli.main(["collect", "--source", "qwen"]) == 0
    assert registry.collect_calls == [("qwen",)]
    assert json.loads(capsys.readouterr().out)["status"] == "complete"


def test_degraded_health_is_partial_success(capsys) -> None:
    degraded = healthy().model_copy(
        update={
            "health": "degraded",
            "error": SourceError(code="partial", message="fixture partial"),
        }
    )
    registry = FakeRegistry((degraded,))

    exit_code = main(["probe"], registry=registry)

    assert exit_code == 3
    assert json.loads(capsys.readouterr().out)["status"] == "partial"


def test_collect_pipeline_can_be_injected_at_the_store_seam(
    capsys, tmp_path: Path
) -> None:
    registry = FakeRegistry((healthy(),))

    exit_code = main(
        ["collect", "--source", "qwen"],
        registry=registry,
        store=JsonNewsStore(tmp_path),
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "complete"
    assert "run_id" in output
    assert (tmp_path / "output/latest.json").exists()
