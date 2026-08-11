from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

import mynews.application.prepare as prepare_module
from mynews.application.candidates import (
    MAX_CONTENT_CHARS,
    MAX_SUMMARY_CHARS,
    build_candidate_payload,
    candidate_contract_schema,
    read_candidate_payload,
    validate_candidate_payload,
)
from mynews.application.collector import SourceCollector
from mynews.application.prepare import prepare_editorial_pack
from mynews.domain.models import Candidate, CollectionRequest
from mynews.sources.feed import RssFeedPlugin
from mynews.sources.newsfromai import newsfromai_registry
from mynews.sources.protocol import SourceContext, SourceMetadata
from mynews.sources.registry import SourceRegistry


class FixtureHttp:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    def get_text(self, url: str, **kwargs: object) -> str:
        del url, kwargs
        self.calls += 1
        return self.payload


class MappingHttp:
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads

    def get_text(self, url: str, **kwargs: object) -> str:
        del kwargs
        return self.payloads[url]


def _feed(source_id: str = "fixture", host: str = "fixture.example") -> RssFeedPlugin:
    return RssFeedPlugin(
        SourceMetadata(
            source_id=source_id,
            name=source_id,
            role="primary",
            homepage=f"https://{host}/feed.xml",
            official_domains=(host,),
            capabilities=("rss",),
            freshness_days=2,
        ),
        f"https://{host}/feed.xml",
    )


def _request() -> CollectionRequest:
    return CollectionRequest.model_validate(
        {
            "from": "2026-08-09T00:00:00Z",
            "to": "2026-08-12T00:00:00Z",
            "freshness_filter": True,
        }
    )


def test_rss_freshness_keeps_business_date_and_previous_day() -> None:
    payload = """<rss><channel>
      <item><title>today</title><link>https://fixture.example/today</link>
        <pubDate>Tue, 11 Aug 2026 08:00:00 GMT</pubDate></item>
      <item><title>previous</title><link>https://fixture.example/previous</link>
        <pubDate>Mon, 10 Aug 2026 08:00:00 GMT</pubDate></item>
      <item><title>old</title><link>https://fixture.example/old</link>
        <pubDate>Sun, 9 Aug 2026 08:00:00 GMT</pubDate></item>
    </channel></rss>"""
    http = FixtureHttp(payload)
    batch = _feed().collect(SourceContext(request=_request(), http=http))
    assert [item.title_original for item in batch.candidates] == ["today", "previous"]


def test_prepare_replay_does_not_fetch_and_refresh_updates_repeat_count(
    tmp_path: Path,
) -> None:
    payload = """<rss><channel><item>
      <title>Stable model release</title><link>https://fixture.example/release</link>
      <description><![CDATA[<p>Useful <b>release</b> details.</p>]]></description>
      <pubDate>Tue, 11 Aug 2026 08:00:00 GMT</pubDate>
      <category>models</category><author>Example Team</author>
    </item></channel></rss>"""
    http = FixtureHttp(payload)
    registry = SourceRegistry([_feed()], http=http)

    first = prepare_editorial_pack("2026-08-11", root=tmp_path, registry=registry)
    output = tmp_path / "output/editorial/2026-08-11/candidates.json"
    first_bytes = output.read_bytes()
    first_payload = json.loads(first_bytes)
    assert first.refreshed is True
    assert first_payload["candidates"][0]["repeat_count"] == 1
    assert first_payload["candidates"][0]["firstSeenAt"] <= first_payload["generatedAt"]
    assert (
        "Useful release details." in first_payload["candidates"][0]["summaryOriginal"]
    )
    assert http.calls == 1

    replay = prepare_editorial_pack("2026-08-11", root=tmp_path, registry=registry)
    assert replay.refreshed is False
    assert output.read_bytes() == first_bytes
    assert http.calls == 1

    refreshed = prepare_editorial_pack(
        "2026-08-11", root=tmp_path, registry=registry, refresh=True
    )
    refreshed_payload = json.loads(output.read_text(encoding="utf-8"))
    assert refreshed.refreshed is True
    assert refreshed_payload["candidates"][0]["repeat_count"] == 2
    assert http.calls == 2


def test_conservative_cross_source_group_and_contract() -> None:
    first = Candidate.model_validate(
        {
            "source_id": "publisher-a",
            "title_original": "OpenAI releases a new coding model for agents",
            "url": "https://publisher-a.example/openai-model",
            "published_at": "2026-08-11T08:00:00Z",
            "excerpt": "Official announcement.",
            "source_role": "primary",
        }
    )
    second = Candidate.model_validate(
        {
            "source_id": "publisher-b",
            "title_original": "OpenAI releases a new coding model for agents today",
            "url": "https://publisher-b.example/openai-model",
            "published_at": "2026-08-11T09:00:00Z",
            "source_role": "discovery",
        }
    )
    payload = build_candidate_payload(
        [first, second],
        business_date="2026-08-11",
        generated_at=datetime(2026, 8, 11, 23, 59, 59, tzinfo=UTC),
        observations={
            "https://publisher-a.example/openai-model": [
                {
                    "observedAt": "2026-08-10T08:00:00Z",
                    "runId": "one",
                    "sourceId": "publisher-a",
                },
                {
                    "observedAt": "2026-08-11T08:00:00Z",
                    "runId": "two",
                    "sourceId": "publisher-a",
                },
            ],
            "https://publisher-b.example/openai-model": [
                {
                    "observedAt": "2026-08-11T09:00:00Z",
                    "runId": "two",
                    "sourceId": "publisher-b",
                },
            ],
        },
    )
    assert validate_candidate_payload(payload) == []
    assert payload["stats"]["candidateCount"] == 1
    candidate = payload["candidates"][0]
    assert candidate["duplicateGroupId"].startswith("event-2026-08-11-")
    assert candidate["multiSources"] == ["publisher-a", "publisher-b"]
    assert candidate["repeat_count"] == 3
    assert candidate["firstSeenAt"] == "2026-08-10T08:00:00Z"


def test_candidate_contract_schema_and_text_limits_are_publicly_stable() -> None:
    public_schema = json.loads(
        Path("docs/reference/candidate-contract-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert candidate_contract_schema() == public_schema

    candidate = Candidate.model_validate(
        {
            "source_id": "fixture",
            "title_original": "Long candidate",
            "url": "https://fixture.example/long",
            "excerpt": "s" * (MAX_SUMMARY_CHARS + 100),
            "content": "c" * (MAX_CONTENT_CHARS + 100),
        }
    )
    payload = build_candidate_payload(
        [candidate],
        business_date="2026-08-11",
        generated_at=datetime(2026, 8, 11, 23, 59, 59, tzinfo=UTC),
        observations={},
    )
    exported = payload["candidates"][0]
    assert len(exported["summaryOriginal"]) <= MAX_SUMMARY_CHARS
    assert len(exported["contentExcerpt"]) <= MAX_CONTENT_CHARS


def test_candidate_validator_rejects_public_schema_violations() -> None:
    payload = {
        "schemaVersion": "1.0",
        "date": "2026-08-11",
        "generatedAt": "2026-08-11T12:00:00Z",
        "stats": {},
        "candidates": [
            {
                "id": "candidate-1",
                "title": "Candidate",
                "url": "https://fixture.example/item",
                "source": "Fixture",
                "firstSeenAt": "2026-08-11T00:00:00Z",
                "firstSeenPrecision": "unknown",
                "unexpected": "must be rejected",
            }
        ],
    }
    issues = validate_candidate_payload(payload)
    assert {issue["field"] for issue in issues} >= {
        "stats.candidateCount",
        "candidates.0.firstSeenPrecision",
        "candidates.0.unexpected",
    }


def test_prepare_privacy_gate_covers_manual_markdown(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual-watchlist.json").write_text(
        json.dumps(
            [
                {
                    "id": "unsafe",
                    "name": "Unsafe",
                    "url": "https://example.example/",
                    "role": "manual",
                    "note": "API_KEY=leaked-secret",
                }
            ]
        ),
        encoding="utf-8",
    )
    http = FixtureHttp(
        "<rss><channel><item><title>Fixture</title>"
        "<link>https://fixture.example/item</link></item></channel></rss>"
    )
    registry = SourceRegistry([_feed()], http=http)

    with pytest.raises(ValueError, match="输出安全检查失败") as raised:
        prepare_editorial_pack("2026-08-11", root=tmp_path, registry=registry)

    assert "leaked-secret" not in str(raised.value)
    assert not (tmp_path / "output/editorial/2026-08-11/candidates.md").exists()


def test_all_source_failure_preserves_previous_candidate_output(tmp_path: Path) -> None:
    http = FixtureHttp(
        "<rss><channel><item><title>Stable item</title>"
        "<link>https://fixture.example/stable</link></item></channel></rss>"
    )
    registry = SourceRegistry([_feed()], http=http)
    prepare_editorial_pack("2026-08-11", root=tmp_path, registry=registry)
    output = tmp_path / "output/editorial/2026-08-11/candidates.json"
    previous = output.read_bytes()

    http.payload = "<broken>"
    with pytest.raises(ValueError, match="所有自动来源均失败"):
        prepare_editorial_pack(
            "2026-08-11", root=tmp_path, registry=registry, refresh=True
        )

    assert output.read_bytes() == previous
    failures = tmp_path / "state/editorial/2026-08-11/failures.json"
    assert json.loads(failures.read_text(encoding="utf-8"))[0]["code"] == "invalid_feed"


def test_editorial_transaction_rolls_back_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    http = FixtureHttp(
        "<rss><channel><item><title>Stable item</title>"
        "<link>https://fixture.example/stable</link></item></channel></rss>"
    )
    registry = SourceRegistry([_feed()], http=http)
    prepare_editorial_pack("2026-08-11", root=tmp_path, registry=registry)
    output = tmp_path / "output/editorial/2026-08-11/candidates.json"
    previous = output.read_bytes()
    original_replace = prepare_module.os.replace
    calls = 0

    def fail_second_replace(source: str, target: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fixture replacement failure")
        original_replace(source, target)

    monkeypatch.setattr(prepare_module.os, "replace", fail_second_replace)
    with pytest.raises(ValueError, match="editorial 输出失败"):
        prepare_editorial_pack(
            "2026-08-11", root=tmp_path, registry=registry, refresh=True
        )

    assert output.read_bytes() == previous
    assert not list(output.parent.glob(".*.tmp"))


def test_legacy_candidate_payload_is_compatibly_read(tmp_path: Path) -> None:
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "date": "2026-08-11",
                "generated_at": "2026-08-11T23:00:00Z",
                "categories": {
                    "inbox": {
                        "order": 1,
                        "items": [
                            {
                                "id": "legacy-1",
                                "title": "Legacy item",
                                "url": "https://legacy.example/item",
                                "source_id": "legacy",
                                "source_role": "primary",
                                "first_seen": "2026-08-11T08:00:00Z",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    payload = read_candidate_payload(path)
    assert payload["schemaVersion"] == "1.0"
    assert payload["candidates"][0]["candidateRef"] == "2026-08-11:legacy-1"
    assert validate_candidate_payload(payload) == []


def test_candidate_v1_minimal_payload_remains_read_compatible() -> None:
    payload = {
        "schemaVersion": "1.0",
        "date": "2026-08-11",
        "generatedAt": "2026-08-11T12:00:00Z",
        "candidates": [
            {
                "id": "candidate-1",
                "title": "Minimal candidate",
                "url": "https://example.com/minimal",
                "source": "Example",
                "firstSeenAt": "2026-08-11T00:00:00Z",
            }
        ],
    }
    assert validate_candidate_payload(payload) == []


def test_newsfromai_inventory_is_17_feeds_and_65_watchlist_items() -> None:
    feeds = json.loads(Path("config/newsfromai-feeds.json").read_text(encoding="utf-8"))
    watchlist = json.loads(
        Path("config/manual-watchlist.json").read_text(encoding="utf-8")
    )
    assert len(feeds["feeds"]) == 17
    assert len(watchlist) == 65
    assert len({item["id"] for item in watchlist}) == 65


def test_newsfromai_registry_runs_all_17_sources_with_fixture_payloads() -> None:
    config = json.loads(Path("config/newsfromai-feeds.json").read_text())
    payloads = {
        item["url"]: (
            "<rss><channel><item><title>"
            f"{item['id']} fixture</title><link>{escape(item['url'])}</link>"
            "<pubDate>Tue, 11 Aug 2026 08:00:00 GMT</pubDate></item>"
            "</channel></rss>"
        )
        for item in config["feeds"]
        if item["id"] != "paperswithcode-daily"
    }
    registry = newsfromai_registry(http=MappingHttp(payloads))
    request = CollectionRequest.model_validate(
        {
            "from": "2026-08-10T00:00:00+08:00",
            "to": "2026-08-12T00:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "freshness_filter": True,
        }
    )
    result = SourceCollector(registry).collect(request, registry.source_ids)
    assert len(registry.source_ids) == 17
    assert len(result.candidates) == 16
    papers_health = next(
        item for item in result.health if item.source_id == "paperswithcode-daily"
    )
    assert papers_health.health == "blocked"
    assert "qwen" not in registry.source_ids
