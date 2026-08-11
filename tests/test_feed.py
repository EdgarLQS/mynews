from __future__ import annotations

from pathlib import Path

import pytest

from mynews.domain.models import CollectionRequest
from mynews.sources.builtins.feed import QWEN_FEED_URL, QwenFeedPlugin
from mynews.sources.feed import RssFeedPlugin
from mynews.sources.protocol import (
    ProbeContext,
    SourceContext,
    SourceMetadata,
    SourcePluginError,
)

FIXTURE = Path(__file__).parent / "fixtures/qwen-blog-feed.xml"


class FixtureHttp:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.requested: list[str] = []

    def get_text(self, url: str, **kwargs: object) -> str:
        self.requested.append(url)
        return self.payload


def request() -> CollectionRequest:
    return CollectionRequest.model_validate(
        {
            "from": "2026-08-01T00:00:00+00:00",
            "to": "2026-08-03T00:00:00+00:00",
        }
    )


def test_qwen_feed_collects_official_entries_in_requested_window() -> None:
    http = FixtureHttp(FIXTURE.read_text(encoding="utf-8"))
    result = QwenFeedPlugin().collect(SourceContext(request=request(), http=http))

    assert [candidate.title_original for candidate in result.candidates] == [
        "Qwen official update"
    ]
    assert result.candidates[0].published_at is not None
    assert result.candidates[0].published_at.isoformat() == "2026-08-02T02:00:00+00:00"
    assert result.fetched_count == 2
    assert http.requested == [QWEN_FEED_URL]


def test_qwen_feed_probe_reports_feed_entry_count() -> None:
    http = FixtureHttp(FIXTURE.read_text(encoding="utf-8"))

    health = QwenFeedPlugin().probe(ProbeContext(http=http, limit=5))

    assert health.health == "healthy"
    assert health.fetched_count == 2
    assert health.accepted_count == 2


def test_qwen_feed_rejects_malformed_xml() -> None:
    with pytest.raises(SourcePluginError, match="有效 XML"):
        QwenFeedPlugin().probe(ProbeContext(http=FixtureHttp("<broken>")))


def test_qwen_feed_probe_rejects_invalid_entry() -> None:
    payload = FIXTURE.read_text(encoding="utf-8").replace(
        "https://qwenlm.github.io/blog/official-update/",
        "https://example.test/not-official/",
    )

    with pytest.raises(SourcePluginError, match="官方标题或链接"):
        QwenFeedPlugin().probe(ProbeContext(http=FixtureHttp(payload)))


def test_public_feed_probe_accepts_a_valid_empty_feed() -> None:
    payload = '<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>'
    plugin = RssFeedPlugin(
        QwenFeedPlugin().metadata,
        QWEN_FEED_URL,
    )

    health = plugin.probe(ProbeContext(http=FixtureHttp(payload)))

    assert health.health == "healthy"
    assert health.fetched_count == 0
    assert health.accepted_count == 0


def test_qwen_feed_preserves_strict_empty_feed_behavior() -> None:
    payload = '<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>'

    with pytest.raises(SourcePluginError, match="item 或 entry"):
        QwenFeedPlugin().probe(ProbeContext(http=FixtureHttp(payload)))


def test_public_feed_rejects_github_subdomain_for_declared_organization() -> None:
    payload = FIXTURE.read_text(encoding="utf-8").replace(
        "https://qwenlm.github.io/blog/official-update/",
        "https://gist.github.com/trusted-org/fixture",
    )
    plugin = RssFeedPlugin(
        SourceMetadata(
            source_id="github-feed",
            name="GitHub feed",
            role="research",
            homepage="https://github.com/trusted-org/repo/releases.atom",
            official_domains=("github.com",),
            official_github_organizations=("trusted-org",),
        ),
        "https://github.com/trusted-org/repo/releases.atom",
    )

    with pytest.raises(SourcePluginError, match="官方标题或链接"):
        plugin.probe(ProbeContext(http=FixtureHttp(payload)))
