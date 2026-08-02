from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mynews.domain.models import Candidate
from mynews.domain.normalization import Normalizer, normalize_source_role

OBSERVED_AT = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)


def test_normalizer_builds_stable_normalized_news_item() -> None:
    candidate = Candidate(
        source_id="news",
        title_original="  OpenAI launches Model 5  ",
        url="https://Example.com/news?id=5&utm_source=feed#comments",
        published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
        excerpt="OpenAI launches Model 5 with a new API.",
        entities=[" OpenAI ", "openai", "Model 5"],
        language="en-US",
        event_type="release",
        heat_signals={"score": 120, "descendants": 42},
    )

    item = Normalizer(source_roles={"news": "discovery"}).normalize(
        [candidate], observed_at=OBSERVED_AT
    )[0]

    assert item.canonical_url == "https://example.com/news?id=5"
    assert item.language_original == "en"
    assert item.source_roles == ["discovery"]
    assert item.event_type == "model_release"
    assert item.published_at == datetime(2026, 8, 2, 1, 0, tzinfo=UTC)
    assert item.first_seen_at == OBSERVED_AT
    assert item.heat_score == 100
    assert item.relevance_score == 50
    assert item.verification_status == "unverified"
    assert item.verification_reason == "verification_pending"
    assert item.entities == ["model 5", "openai"]
    assert item.id == item.event_key
    assert item.content_hash.startswith("sha256:")


def test_normalizer_event_key_is_stable_for_equivalent_candidates() -> None:
    first = Candidate(
        source_id="one",
        title_original="Qwen update",
        url="https://example.test/item/",
        published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
        excerpt="A factual update",
        entities=["Qwen"],
    )
    second = first.model_copy(
        update={
            "source_id": "two",
            "url": "https://EXAMPLE.TEST/item#fragment",
            "title_original": " qwen   update ",
            "entities": ["qwen"],
        }
    )

    normalizer = Normalizer(source_roles={"one": "primary", "two": "monitor"})
    first_item = normalizer.normalize([first], observed_at=OBSERVED_AT)[0]
    second_item = normalizer.normalize([second], observed_at=OBSERVED_AT)[0]

    assert first_item.event_key == second_item.event_key


def test_normalizer_keeps_unknown_publication_time_unknown() -> None:
    candidate = Candidate(
        source_id="manual",
        title_original="价格页",
        url="https://example.test/pricing",
        published_at=None,
        excerpt="价格更新",
        source_role="monitor",
    )

    item = Normalizer().normalize([candidate], observed_at=OBSERVED_AT)[0]

    assert item.published_at is None
    assert item.event_type == "pricing_change"
    assert item.language_original == "zh"
    assert item.source_roles == ["monitor"]


def test_unknown_source_role_is_rejected_instead_of_reclassified() -> None:
    with pytest.raises(ValueError, match="不支持的来源角色"):
        normalize_source_role("primray")
