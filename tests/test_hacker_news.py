from __future__ import annotations

import json
from pathlib import Path

import pytest

from mynews.domain.models import CollectionRequest
from mynews.sources.builtins.hacker_news import (
    HN_ITEM_URL,
    HN_TOP_STORIES_URL,
    HackerNewsPlugin,
)
from mynews.sources.protocol import ProbeContext, SourceContext, SourcePluginError

FIXTURES = Path(__file__).parent / "fixtures"


class FixtureHttp:
    def __init__(self) -> None:
        top = json.loads((FIXTURES / "hacker-news-topstories.json").read_text())
        items = json.loads((FIXTURES / "hacker-news-items.json").read_text())
        self.payloads = {HN_TOP_STORIES_URL: top}
        self.payloads.update(
            {
                HN_ITEM_URL.format(item_id=item_id): item
                for item_id, item in items.items()
            }
        )
        self.requested: list[str] = []

    def get_json(self, url: str, **kwargs: object) -> object:
        self.requested.append(url)
        return self.payloads[url]


def request() -> CollectionRequest:
    return CollectionRequest.model_validate(
        {
            "from": "2026-08-01T00:00:00+00:00",
            "to": "2026-08-03T00:00:00+00:00",
        }
    )


def test_hacker_news_collects_windowed_stories_and_ask_url() -> None:
    http = FixtureHttp()
    result = HackerNewsPlugin().collect(
        SourceContext(request=request(), http=http, limit=3)
    )

    assert [candidate.title_original for candidate in result.candidates] == [
        "AI tooling update",
        "Ask HN: build tools",
    ]
    assert str(result.candidates[1].url) == "https://news.ycombinator.com/item?id=1003"
    assert result.fetched_count == 3
    assert result.candidates[0].heat_signals == {"score": 120.0, "descendants": 42.0}


def test_hacker_news_probe_only_checks_official_topstories_endpoint() -> None:
    http = FixtureHttp()
    health = HackerNewsPlugin().probe(ProbeContext(http=http, limit=2))

    assert health.health == "healthy"
    assert health.fetched_count == 1
    assert http.requested == [HN_TOP_STORIES_URL, HN_ITEM_URL.format(item_id=1001)]


def test_hacker_news_rejects_malformed_topstories_payload() -> None:
    http = FixtureHttp()
    http.payloads[HN_TOP_STORIES_URL] = ["not-an-id"]

    with pytest.raises(SourcePluginError, match="整数数组"):
        HackerNewsPlugin().probe(ProbeContext(http=http))
