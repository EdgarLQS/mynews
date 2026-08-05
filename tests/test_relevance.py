from __future__ import annotations

from mynews.domain.models import Candidate
from mynews.domain.relevance import AiTechnologyRelevanceFilter


def test_relevance_filter_keeps_ai_and_technology_candidates() -> None:
    policy = AiTechnologyRelevanceFilter()

    decision = policy.evaluate(
        Candidate(
            source_id="hacker-news",
            title_original="Rust developer tooling update",
            url="https://example.test/rust",
        )
    )

    assert decision.relevant is True
    assert decision.reason == "ai_or_technology_match"
    assert decision.score > 0


def test_relevance_filter_rejects_unrelated_discovery_candidate() -> None:
    policy = AiTechnologyRelevanceFilter()

    decision = policy.evaluate(
        Candidate(
            source_id="hacker-news",
            title_original="A recipe for soup",
            url="https://example.test/soup",
        )
    )

    assert decision.relevant is False
    assert decision.reason == "irrelevant_ai_technology"


def test_relevance_filter_does_not_match_ai_inside_unrelated_word() -> None:
    decision = AiTechnologyRelevanceFilter().evaluate(
        Candidate(
            source_id="hacker-news",
            title_original="Sailing routes for beginners",
            url="https://example.test/sailing",
            excerpt="A practical guide to coastal sailing.",
        )
    )

    assert decision.relevant is False


def test_relevance_filter_ignores_ai_only_in_html_url() -> None:
    decision = AiTechnologyRelevanceFilter().evaluate(
        Candidate(
            source_id="hacker-news",
            title_original="Ask HN: Who is hiring? (August 2026)",
            url="https://news.ycombinator.com/item?id=49156683",
            excerpt=(
                "Searchers: try "
                "<a href=\"https:&#x2F;&#x2F;nthesis.ai&#x2F;public\">"
                "https:&#x2F;&#x2F;nthesis.ai&#x2F;public</a>."
            ),
        )
    )

    assert decision.relevant is False
    assert decision.reason == "irrelevant_ai_technology"
