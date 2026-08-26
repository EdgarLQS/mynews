from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mynews.application.runtime import ApplicationRuntime, Command
from mynews.domain.models import Candidate
from mynews.sources.protocol import (
    ProbeContext,
    SourceCollection,
    SourceContext,
    SourceHealth,
)


class RegistryFixture:
    source_ids = ("qwen",)
    source_roles = {"qwen": "primary"}
    http = object()

    def __init__(self) -> None:
        self.collect_calls: list[tuple[str, ...] | None] = []
        self.probe_calls: list[tuple[str, ...] | None] = []

    def collect_all(
        self,
        context: SourceContext,
        source_ids: tuple[str, ...] | None = None,
    ) -> SourceCollection:
        self.collect_calls.append(source_ids)
        candidate = Candidate(
            source_id="qwen",
            title_original="Fixture candidate",
            url="https://qwenlm.github.io/blog/fixture",
        )
        return SourceCollection((candidate,), (healthy(),))

    def probe(
        self,
        context: ProbeContext,
        source_ids: tuple[str, ...] | None = None,
    ) -> tuple[SourceHealth, ...]:
        self.probe_calls.append(source_ids)
        return (healthy(),)


def healthy() -> SourceHealth:
    return SourceHealth(
        source_id="qwen",
        role="primary",
        health="healthy",
        fetched_count=1,
        accepted_count=1,
        duration_ms=1,
        checked_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


def test_runtime_probe_returns_structured_command_outcome() -> None:
    registry = RegistryFixture()

    outcome = ApplicationRuntime(registry=registry).run(
        Command("probe", {"source_ids": ["qwen"]})
    )

    assert outcome.exit_code == 0
    assert outcome.payload == {
        "status": "complete",
        "sources": [healthy().model_dump(mode="json")],
    }
    assert registry.probe_calls == [("qwen",)]


def test_command_copies_options_and_keeps_public_shape() -> None:
    options: dict[str, Any] = {"source_ids": ["qwen"]}

    command = Command("probe", options)
    options["source_ids"].append("other")

    assert command.name == "probe"
    assert command.options == {"source_ids": ["qwen"]}
