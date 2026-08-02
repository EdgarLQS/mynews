from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mynews.application.collector import PipelineCollector
from mynews.domain.models import CollectionRequest
from mynews.infrastructure.http import HttpClientError, HttpResponse
from mynews.sources.builtins.official_pages import (
    AnthropicNewsPlugin,
    BloombergAiPlugin,
    DeepSeekPricingPlugin,
    DeepSeekUpdatesPlugin,
    GoogleGeminiPlugin,
    OfficialHtmlPlugin,
    OpenAiNewsPlugin,
    OpenAiPricingPlugin,
    TraeChangelogPlugin,
    ZhihuHotPlugin,
)
from mynews.sources.protocol import ProbeContext, SourceContext, SourcePluginError
from mynews.sources.registry import SourceRegistry, built_in_registry
from mynews.storage.json_store import JsonNewsStore
from mynews.verification.fake import FakeVerifier

FIXTURES = Path(__file__).parent / "fixtures"
REQUEST = CollectionRequest.model_validate(
    {
        "from": "2026-08-01T00:00:00+00:00",
        "to": "2026-08-04T00:00:00+00:00",
    }
)


class FixtureHttp:
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads
        self.requested: list[str] = []

    def get_text(self, url: str, **kwargs: object) -> str:
        del kwargs
        self.requested.append(url)
        return self.payloads[url]

    def get(self, url: str, **kwargs: object) -> HttpResponse:
        del kwargs
        self.requested.append(url)
        return HttpResponse(
            status_code=200,
            headers={},
            body=self.payloads[url].encode(),
            final_url=url,
        )


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 2, 9, 30, tzinfo=UTC)


class IncrementingClock:
    def __init__(self) -> None:
        self._calls = 0

    def now(self) -> datetime:
        value = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
        self._calls += 1
        return value.replace(second=self._calls)


class CountingVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, candidates: object, *, config: object) -> tuple[object, ...]:
        del candidates, config
        self.calls += 1
        return ()


@pytest.mark.parametrize(
    ("plugin_type", "fixture_name", "expected_title"),
    [
        (OpenAiNewsPlugin, "openai-news.html", "Introducing OpenAI Responses API"),
        (AnthropicNewsPlugin, "anthropic-news.html", "Claude for developers"),
        (GoogleGeminiPlugin, "google-gemini-changelog.html", "Gemini API update"),
        (DeepSeekUpdatesPlugin, "deepseek-updates.html", "DeepSeek-V4"),
        (TraeChangelogPlugin, "trae-changelog.html", "TRAE v3.3.48"),
    ],
)
def test_official_pages_collect_fixture_entries(
    plugin_type: type[OfficialHtmlPlugin],
    fixture_name: str,
    expected_title: str,
) -> None:
    plugin = plugin_type()
    http = FixtureHttp({plugin.page_url: (FIXTURES / fixture_name).read_text()})

    batch = plugin.collect(
        SourceContext(request=REQUEST, http=http, clock=FixedClock())
    )
    health = plugin.probe(ProbeContext(http=http, clock=FixedClock()))

    assert batch.source_id == plugin.metadata.source_id
    assert batch.candidates[0].title_original == expected_title
    assert batch.candidates[0].published_at is not None
    assert health.health == "healthy"
    assert health.accepted_count == 1
    assert http.requested == [plugin.page_url, plugin.page_url]


@pytest.mark.parametrize(
    ("plugin_type", "fixture_name"),
    [
        (ZhihuHotPlugin, "zhihu-hot.html"),
        (BloombergAiPlugin, "bloomberg-ai.html"),
    ],
)
def test_experimental_pages_keep_public_metadata_and_discovery_role(
    plugin_type: type[OfficialHtmlPlugin], fixture_name: str
) -> None:
    plugin = plugin_type()
    http = FixtureHttp({plugin.page_url: (FIXTURES / fixture_name).read_text()})

    batch = plugin.collect(SourceContext(request=REQUEST, http=http))
    health = plugin.probe(ProbeContext(http=http))

    assert plugin.metadata.role == "discovery"
    assert plugin.metadata.stability == "experimental"
    assert batch.candidates[0].source_role == "discovery"
    assert batch.candidates[0].content is None
    assert health.health == "healthy"


def test_built_in_registry_contains_phase45_sources() -> None:
    registry = built_in_registry(http=FixtureHttp({}))

    assert registry.source_ids == (
        "cc-switch",
        "hacker-news",
        "qwen",
        "openai",
        "anthropic",
        "google-gemini",
        "deepseek",
        "trae",
        "openai-pricing",
        "deepseek-pricing",
        "zhihu-hot",
        "bloomberg-ai",
    )


def test_experimental_probe_is_blocked_without_public_metadata() -> None:
    plugin = ZhihuHotPlugin()
    registry = SourceRegistry(
        [plugin],
        http=FixtureHttp({plugin.page_url: "<html><title>登录</title></html>"}),
    )

    health = registry.probe(ProbeContext(http=registry.http))

    assert health[0].health == "blocked"
    assert health[0].error is not None
    assert health[0].error.code == "public_metadata_unavailable"


def test_phase45_source_failure_isolated_by_registry() -> None:
    openai = OpenAiNewsPlugin()
    deepseek = DeepSeekUpdatesPlugin()

    class FailingHttp(FixtureHttp):
        def get(self, url: str, **kwargs: object) -> HttpResponse:
            if url == deepseek.page_url:
                raise HttpClientError("network_error", "fixture network failure")
            return super().get(url, **kwargs)

    http = FailingHttp(
        {openai.page_url: (FIXTURES / "openai-news.html").read_text()}
    )
    health = SourceRegistry([openai, deepseek], http=http).probe(
        ProbeContext(http=http)
    )

    assert [item.health for item in health] == ["healthy", "failed"]


def test_official_page_rejects_unexpected_login_shell() -> None:
    plugin = OpenAiNewsPlugin()
    http = FixtureHttp({plugin.page_url: "<html><title>Access denied</title></html>"})

    with pytest.raises(SourcePluginError, match="官方页面没有匹配"):
        plugin.probe(ProbeContext(http=http))


def test_official_page_rejects_unofficial_redirect() -> None:
    plugin = OpenAiNewsPlugin()
    payload = (FIXTURES / "openai-news.html").read_text()

    class RedirectHttp(FixtureHttp):
        def get(self, url: str, **kwargs: object) -> HttpResponse:
            del kwargs
            return HttpResponse(
                status_code=200,
                headers={},
                body=self.payloads[url].encode(),
                final_url="https://evil.example/redirect",
            )

    with pytest.raises(SourcePluginError, match="重定向"):
        plugin.probe(ProbeContext(http=RedirectHttp({plugin.page_url: payload})))


def test_discovery_candidate_never_enters_verifier(tmp_path: Path) -> None:
    plugin = ZhihuHotPlugin()
    http = FixtureHttp({plugin.page_url: (FIXTURES / "zhihu-hot.html").read_text()})
    verifier = CountingVerifier()
    report = PipelineCollector(
        SourceRegistry([plugin], http=http),
        JsonNewsStore(tmp_path),
        clock=IncrementingClock(),
        verifier=verifier,
    ).collect(REQUEST)

    assert len(report.items) == 1
    assert report.items[0].verification_status == "unverified"
    assert verifier.calls == 0


def test_price_page_first_observation_only_writes_snapshot(tmp_path: Path) -> None:
    plugin = DeepSeekPricingPlugin()
    fixture = (FIXTURES / "deepseek-pricing.html").read_text()
    http = FixtureHttp({plugin.page_url: fixture})
    store = JsonNewsStore(tmp_path)
    registry = SourceRegistry([plugin], http=http)
    collector = PipelineCollector(
        registry, store, clock=FixedClock(), verifier=FakeVerifier()
    )

    first = collector.collect(REQUEST)
    health = plugin.probe(ProbeContext(http=http))

    assert first.items == []
    assert store.load_price_snapshot("deepseek-pricing") is not None
    assert first.stats["candidate_count"] == 0
    assert health.health == "healthy"


def test_price_page_change_creates_pricing_change_with_unknown_date(
    tmp_path: Path,
) -> None:
    plugin = OpenAiPricingPlugin()
    first_fixture = (FIXTURES / "openai-pricing.html").read_text()
    changed_fixture = first_fixture.replace("$1.00", "$1.10")
    http = FixtureHttp({plugin.page_url: first_fixture})
    store = JsonNewsStore(tmp_path)
    collector = PipelineCollector(
        SourceRegistry([plugin], http=http),
        store,
        clock=IncrementingClock(),
        verifier=FakeVerifier(),
    )

    collector.collect(REQUEST)
    unchanged = collector.collect(REQUEST)
    assert unchanged.items == []
    http.payloads[plugin.page_url] = changed_fixture
    second = collector.collect(REQUEST)

    assert len(second.items) == 1
    assert second.items[0].event_type == "pricing_change"
    assert second.items[0].published_at is None
    assert second.items[0].verification_status == "unverified"
