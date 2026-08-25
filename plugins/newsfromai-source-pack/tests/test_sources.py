from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from mynews_newsfromai_sources import SOURCE_SPECS, plugin_for

from mynews.application.collector import SourceCollector
from mynews.domain.models import CollectionRequest
from mynews.sources.protocol import (
    ProbeContext,
    SourceBlockedError,
    SourceContext,
    SourcePluginError,
)
from mynews.sources.registry import SourceRegistry

FIXTURES = Path(__file__).parents[1] / "fixtures"
REQUEST = CollectionRequest.model_validate(
    {"from": "2026-08-10T00:00:00Z", "to": "2026-08-12T00:00:00Z"}
)


class FixtureHttp:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def get_text(self, url: str, **kwargs: object) -> str:
        del url, kwargs
        return self.payload


@dataclass
class BrokenPlugin:
    metadata: object

    def collect(self, context: SourceContext) -> object:
        del context
        raise RuntimeError("broken source fixture")

    def probe(self, context: ProbeContext) -> object:
        del context
        raise RuntimeError("broken source fixture")


@pytest.mark.parametrize("spec", SOURCE_SPECS, ids=lambda item: item.source_id)
def test_every_source_parses_fixture_and_has_independent_probe(spec) -> None:
    plugin = plugin_for(spec.source_id)
    if spec.manual_reason:
        health = plugin.probe(ProbeContext(http=FixtureHttp("")))
        assert health.health == "blocked"
        assert health.error is not None
        assert health.error.code == "manual_source"
        assert SourceCollector.exit_code((health,)) == 0
        with pytest.raises(SourceBlockedError, match="没有可确认"):
            plugin.collect(SourceContext(request=REQUEST, http=FixtureHttp("")))
        return
    payload = (FIXTURES / f"{spec.source_id}.xml").read_text(encoding="utf-8")
    http = FixtureHttp(payload)

    batch = plugin.collect(SourceContext(request=REQUEST, http=http))
    health = plugin.probe(ProbeContext(http=http))

    assert batch.source_id == spec.source_id
    assert len(batch.candidates) == 1
    assert health.health == "healthy"
    assert health.accepted_count == 1


@pytest.mark.parametrize("spec", SOURCE_SPECS, ids=lambda item: item.source_id)
def test_every_source_rejects_non_official_feed_link(spec) -> None:
    if spec.manual_reason:
        return
    plugin = plugin_for(spec.source_id)
    payload = (FIXTURES / f"{spec.source_id}.xml").read_text(encoding="utf-8")
    if spec.official_github_organizations:
        bad_link = "https://github.com/WrongOrg/fixture/releases/tag/bad"
    else:
        bad_link = "https://not-official.example/fixture"
    bad_payload = payload.replace("https://", bad_link.split("://", 1)[0] + "://", 1)
    bad_payload = bad_payload.replace(
        plugin.feed_url.split("://", 1)[1].split("/", 1)[0],
        bad_link.split("://", 1)[1].split("/", 1)[0],
    )
    if spec.official_github_organizations:
        bad_payload = payload.replace("MoonshotAI", "WrongOrg").replace(
            "THUDM", "WrongOrg"
        )

    if spec.role == "discovery":
        health = plugin.probe(ProbeContext(http=FixtureHttp(bad_payload)))
        assert health.health == "healthy"
    else:
        with pytest.raises(SourcePluginError, match="官方标题或链接"):
            plugin.probe(ProbeContext(http=FixtureHttp(bad_payload)))


@pytest.mark.parametrize("spec", SOURCE_SPECS, ids=lambda item: item.source_id)
def test_every_source_failure_isolated_from_other_sources(spec) -> None:
    plugin = plugin_for(spec.source_id)
    broken = BrokenPlugin(replace(plugin.metadata, source_id="broken"))
    payload = (
        ""
        if spec.manual_reason
        else (FIXTURES / f"{spec.source_id}.xml").read_text(encoding="utf-8")
    )
    registry = SourceRegistry(
        [plugin, broken],
        http=FixtureHttp(payload),
    )

    result = registry.collect_all(SourceContext(request=REQUEST, http=registry.http))

    if spec.manual_reason:
        assert result.candidates == ()
        assert result.health[0].health == "blocked"
    else:
        assert [item.source_id for item in result.candidates] == [spec.source_id]
        assert result.health[0].health == "healthy"
    assert result.health[1].health == "failed"


def test_anthropic_status_uses_claude_status_and_rejects_old_host() -> None:
    spec = next(item for item in SOURCE_SPECS if item.source_id == "anthropic-status")
    assert spec.feed_url == "https://status.claude.com/history.rss"
    assert spec.official_domains == ("status.claude.com",)

    payload = (FIXTURES / "anthropic-status.xml").read_text(encoding="utf-8")
    old_host_payload = payload.replace("status.claude.com", "status.anthropic.com")
    with pytest.raises(SourcePluginError, match="官方标题或链接"):
        plugin_for(spec.source_id).probe(ProbeContext(http=FixtureHttp(old_host_payload)))


def test_paperswithcode_daily_uses_current_manual_entrypoint() -> None:
    spec = next(
        item for item in SOURCE_SPECS if item.source_id == "paperswithcode-daily"
    )
    assert spec.feed_url == "https://huggingface.co/papers"
    assert spec.official_domains == ("huggingface.co",)
    assert spec.manual_reason is not None
