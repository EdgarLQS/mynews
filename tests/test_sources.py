from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from mynews.domain.models import Candidate, CollectionRequest
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceContext,
    SourceHealth,
    SourceMetadata,
    SourcePluginError,
)
from mynews.sources.registry import SourceRegistry, built_in_registry

NOW = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)
REQUEST = CollectionRequest.model_validate(
    {
        "from": "2026-08-01T00:00:00+00:00",
        "to": "2026-08-03T00:00:00+00:00",
    }
)


class NullHttpClient:
    def get(self, url: str, **kwargs: object) -> object:
        raise AssertionError("stub source does not use HTTP")

    def get_json(self, url: str, **kwargs: object) -> object:
        raise AssertionError("stub source does not use HTTP")

    def get_text(self, url: str, **kwargs: object) -> str:
        raise AssertionError("stub source does not use HTTP")


class FrozenClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def metadata(source_id: str) -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        name=source_id,
        role="discovery",
        homepage="https://example.test/",
        official_domains=("example.test",),
        capabilities=("fixture",),
    )


def experimental_metadata(source_id: str) -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        name=source_id,
        role="discovery",
        homepage="https://example.test/",
        official_domains=("example.test",),
        capabilities=("fixture",),
        stability="experimental",
    )


@dataclass
class StubPlugin:
    metadata: SourceMetadata
    should_fail: bool = False

    def collect(self, context: SourceContext) -> SourceBatch:
        if self.should_fail:
            raise SourcePluginError("fixture_failure", "fixture source failed")
        candidate = Candidate(
            source_id=self.metadata.source_id,
            title_original="Fixture item",
            url="https://example.test/item",
            published_at=NOW,
        )
        return SourceBatch(self.metadata.source_id, (candidate,))

    def probe(self, context: ProbeContext) -> SourceHealth:
        return SourceHealth(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            health="healthy",
            fetched_count=1,
            accepted_count=1,
            duration_ms=0,
            checked_at=NOW,
        )


def test_registry_rejects_duplicate_stable_source_ids() -> None:
    with pytest.raises(ValueError, match="重复来源 ID"):
        SourceRegistry([StubPlugin(metadata("same")), StubPlugin(metadata("same"))])


def test_registry_isolates_collection_failure_and_keeps_other_source() -> None:
    registry = SourceRegistry(
        [
            StubPlugin(metadata("good")),
            StubPlugin(metadata("bad"), should_fail=True),
        ]
    )

    result = registry.collect_all(
        SourceContext(request=REQUEST, http=NullHttpClient())
    )

    assert [candidate.source_id for candidate in result.candidates] == ["good"]
    assert [health.source_id for health in result.health] == ["good", "bad"]
    assert result.health[0].health == "healthy"
    assert result.health[1].health == "failed"
    assert result.health[1].error is not None
    assert result.health[1].error.code == "fixture_failure"


def test_registry_uses_injected_clock_for_health_snapshot() -> None:
    clock = FrozenClock(datetime(2026, 8, 2, 12, 0, tzinfo=UTC))
    registry = SourceRegistry([StubPlugin(metadata("good"))])

    result = registry.collect_all(
        SourceContext(request=REQUEST, http=NullHttpClient(), clock=clock)
    )

    assert result.health[0].checked_at == clock.value


def test_experimental_source_failure_does_not_make_collection_partial() -> None:
    registry = SourceRegistry(
        [StubPlugin(metadata("stable")), StubPlugin(experimental_metadata("lab"), True)]
    )

    result = registry.collect_all(
        SourceContext(request=REQUEST, http=NullHttpClient())
    )

    assert result.health[1].stability == "experimental"
    assert result.health[1].health == "failed"


def test_registry_rejects_unsupported_plugin_protocol_version() -> None:
    plugin_metadata = metadata("old")
    plugin_metadata = SourceMetadata(
        source_id=plugin_metadata.source_id,
        name=plugin_metadata.name,
        role=plugin_metadata.role,
        homepage=plugin_metadata.homepage,
        official_domains=plugin_metadata.official_domains,
        capabilities=plugin_metadata.capabilities,
        plugin_api_version="0.9",
    )

    with pytest.raises(ValueError, match="协议版本"):
        SourceRegistry([StubPlugin(plugin_metadata)])


def test_registry_probe_can_select_one_source() -> None:
    registry = SourceRegistry(
        [StubPlugin(metadata("one")), StubPlugin(metadata("two"))]
    )

    health = registry.probe(ProbeContext(http=NullHttpClient()), ["two"])

    assert [item.source_id for item in health] == ["two"]


def test_registry_rejects_unknown_source_selection() -> None:
    registry = SourceRegistry([StubPlugin(metadata("known"))])

    with pytest.raises(KeyError, match="未知来源"):
        registry.probe(ProbeContext(http=NullHttpClient()), ["missing"])


def test_built_in_registry_contains_phase_two_sources() -> None:
    registry = built_in_registry(http=NullHttpClient())

    assert registry.source_ids[:3] == ("cc-switch", "hacker-news", "qwen")
    assert {
        "openai",
        "anthropic",
        "google-gemini",
        "deepseek",
        "trae",
        "openai-pricing",
        "deepseek-pricing",
        "zhihu-hot",
        "bloomberg-ai",
    }.issubset(registry.source_ids)
