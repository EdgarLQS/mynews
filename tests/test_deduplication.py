from __future__ import annotations

from datetime import UTC, datetime

from mynews.domain.deduplication import Deduplicator, DedupState
from mynews.domain.models import Candidate
from mynews.domain.normalization import Normalizer

OBSERVED_AT = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)


def test_deduplicator_merges_same_event_from_two_sources() -> None:
    candidates = [
        Candidate(
            source_id="one",
            title_original="Qwen update",
            url="https://example.test/item",
            published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
            excerpt="A factual update",
        ),
        Candidate(
            source_id="two",
            title_original=" qwen update ",
            url="https://EXAMPLE.TEST/item#top",
            published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
            excerpt="A factual update",
        ),
    ]
    items = Normalizer(source_roles={"one": "discovery", "two": "primary"}).normalize(
        candidates, observed_at=OBSERVED_AT
    )

    result = Deduplicator().deduplicate(items)

    assert len(result) == 1
    assert result[0].discovery_sources == ["one", "two"]
    assert result[0].source_roles == ["discovery", "primary"]


def test_dedup_state_suppresses_event_seen_by_a_previous_run() -> None:
    candidate = Candidate(
        source_id="one",
        title_original="Qwen update",
        url="https://example.test/item",
        published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
        excerpt="A factual update",
    )
    item = Normalizer().normalize([candidate], observed_at=OBSERVED_AT)[0]

    first_deduplicator = Deduplicator(DedupState())
    first = first_deduplicator.deduplicate([item])
    saved_state = first_deduplicator.state

    second = Deduplicator(saved_state).deduplicate([item])

    assert len(first) == 1
    assert second == ()
