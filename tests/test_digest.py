from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from mynews.application.digest import DigestBuildConfig, DigestBuilder
from mynews.domain.models import (
    CollectionRequest,
    Digest,
    Evidence,
    EvidenceValidation,
    NewsItem,
    RunReport,
    VerificationRetry,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


class StaticRunner:
    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def run(self, prompt: str, *, model: str, timeout: float) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _item(
    key: str,
    *,
    title: str = "OpenAI releases a model",
    url: str | None = None,
    event_type: str = "model_release",
    status: str = "unverified",
    reason: str = "codex_no_suggestion",
    relevance: int = 80,
    heat: int = 70,
    published_at: datetime | None = NOW - timedelta(days=1),
    content_hash: str | None = None,
    retry: VerificationRetry | None = None,
    evidence: list[Evidence] | None = None,
) -> NewsItem:
    return NewsItem(
        id=key,
        event_key=key,
        event_type=event_type,
        title_original=title,
        language_original="en",
        title_zh=title,
        summary_zh=title,
        published_at=published_at,
        first_seen_at=NOW,
        heat_score=heat,
        relevance_score=relevance,
        discovery_sources=["hacker-news"],
        verification_status=status,
        verification_reason=reason,
        primary_evidence=evidence or [],
        verification_retry=retry,
        content_hash=content_hash or f"sha256:{key}",
        canonical_url=url or f"https://news.example/{key}",
        entities=["openai"],
        source_roles=["discovery"],
    )


def _evidence(
    url: str = "https://openai.com/index/release",
    *,
    content_hash: str = "sha256:evidence",
    strict: bool = True,
) -> Evidence:
    return Evidence(
        url=url,
        publisher="OpenAI",
        title="Official release",
        published_at=NOW - timedelta(days=1),
        retrieved_at=NOW,
        excerpt="The official release changes model availability.",
        content_hash=content_hash,
        validation=EvidenceValidation(
            reachable=True,
            official_domain=True,
            redirect_safe=strict,
            excerpt_matched=True,
            date_matched=strict,
            content_hash_matched=strict,
            lifecycle_status="current",
        ),
    )


def _report(*items: NewsItem, schema_version: str = "1.2") -> RunReport:
    return RunReport(
        schema_version=schema_version,
        run_id="run-2026-08-09",
        status="complete",
        requested_range=CollectionRequest(
            **{
                "from": NOW - timedelta(days=1),
                "to": NOW,
                "timezone": "UTC",
                "verification_budget": 30,
            }
        ),
        started_at=NOW,
        finished_at=NOW,
        items=list(items),
    )


def _build(
    report: RunReport,
    *,
    runner: StaticRunner | None = None,
    previous: Digest | None = None,
    config: DigestBuildConfig | None = None,
):
    return DigestBuilder(runner).build(
        report,
        previous,
        config=config or DigestBuildConfig(use_codex=False),
        now=NOW,
    )


def test_conservative_cluster_merges_same_event_but_not_unrelated_story() -> None:
    same_event_a = _item(
        "same-a",
        title="OpenAI releases GPT 5 model",
        url="https://example.test/story-a",
        content_hash="sha256:same-a",
    )
    same_event_b = _item(
        "same-b",
        title="OpenAI releases GPT 5 model update",
        url="https://example.test/story-b",
        content_hash="sha256:same-b",
    )
    unrelated = _item(
        "other",
        title="OpenAI releases image generation model",
        url="https://example.test/story-c",
        content_hash="sha256:other",
    )

    digest = _build(_report(same_event_a, same_event_b, unrelated))

    assert digest.stats["input_item_count"] == 3
    assert digest.stats["cluster_count"] == 2
    assert len(digest.lead_items) == 2
    assert len(digest.lead_items[0].source_item_keys) == 2


def test_missing_dates_do_not_enable_fuzzy_cross_url_merge() -> None:
    first = _item(
        "missing-date-a",
        title="OpenAI releases GPT 5 model",
        url="https://example.test/missing-a",
        published_at=None,
        content_hash="sha256:missing-a",
    )
    second = _item(
        "missing-date-b",
        title="OpenAI releases GPT 5 model update",
        url="https://example.test/missing-b",
        published_at=None,
        content_hash="sha256:missing-b",
    )

    digest = _build(_report(first, second))

    assert digest.stats["cluster_count"] == 2


def test_rank_score_uses_documented_weights_and_is_deterministic() -> None:
    item = _item(
        "ranked",
        status="unverified",
        relevance=80,
        heat=20,
        published_at=NOW,
    )

    digest = _build(_report(item))

    ranked = digest.lead_items[0]
    assert ranked.freshness_score == 100
    assert ranked.event_type_score == 100
    assert ranked.rank_score == pytest.approx(73.0)


def test_lifecycle_marks_updated_then_ongoing_by_saved_facts() -> None:
    first_item = _item(
        "first",
        url="https://openai.com/index/release",
        status="verified",
        reason="official_source",
        evidence=[_evidence(content_hash="sha256:one")],
        content_hash="sha256:one",
    )
    first = _build(_report(first_item))
    changed_item = _item(
        "changed-key",
        url="https://openai.com/index/release",
        status="verified",
        reason="official_source",
        evidence=[_evidence(content_hash="sha256:two")],
        content_hash="sha256:two",
    )
    changed = _build(_report(changed_item), previous=first)
    ongoing = _build(_report(changed_item), previous=changed)

    assert changed.main_items[0].lifecycle == "updated"
    assert ongoing.main_items[0].lifecycle == "ongoing"


def test_verified_main_and_unverified_lead_keep_reason_and_retry_separate() -> None:
    retry = VerificationRetry(
        status="pending",
        attempt_count=2,
        last_reason="codex_timeout",
        next_retry_at=NOW + timedelta(hours=1),
        max_attempts=3,
        expires_at=NOW + timedelta(days=1),
    )
    verified = _item(
        "verified",
        status="verified",
        reason="official_source",
        evidence=[_evidence()],
        relevance=100,
        heat=100,
    )
    lead = _item(
        "lead",
        title="OpenAI changes pricing policy",
        retry=retry,
        reason="codex_timeout",
    )

    digest = _build(_report(verified, lead))

    assert [item.verification_status for item in digest.main_items] == ["verified"]
    assert [item.verification_status for item in digest.lead_items] == ["unverified"]
    assert digest.lead_items[0].verification_reason == "codex_timeout"
    assert digest.lead_items[0].verification_retry == retry


def test_codex_summary_must_use_saved_evidence_reference() -> None:
    item = _item(
        "verified",
        status="verified",
        reason="official_source",
        evidence=[_evidence()],
    )
    response = json.dumps(
        {
            "summaries": [
                {
                    "item_id": "verified",
                    "summary_zh": "官方公告确认了模型可用性变化。",
                    "impact_zh": "开发者需要关注兼容性和采用成本。",
                    "evidence_refs": ["https://openai.com/index/release"],
                }
            ]
        }
    )
    runner = StaticRunner(response)

    digest = _build(
        _report(item),
        runner=runner,
        config=DigestBuildConfig(),
    )

    assert digest.status == "complete"
    assert digest.main_items[0].summary_status == "codex"
    assert str(digest.main_items[0].evidence_refs[0].url) == (
        "https://openai.com/index/release"
    )
    assert "saved_evidence" in runner.prompts[0]


@pytest.mark.parametrize(
    "runner",
    [
        StaticRunner(error=TimeoutError()),
        StaticRunner(response="not-json"),
        StaticRunner(
            response=json.dumps(
                {
                    "summaries": [
                        {
                            "item_id": "verified",
                            "summary_zh": "摘要包含 https://evil.example/ 网址。",
                            "impact_zh": "影响判断。",
                            "evidence_refs": ["https://evil.example/"],
                        }
                    ]
                }
            )
        ),
    ],
)
def test_codex_failure_or_unsafe_reference_uses_partial_fallback(
    runner: StaticRunner,
) -> None:
    item = _item(
        "verified",
        status="verified",
        reason="official_source",
        evidence=[_evidence()],
    )

    digest = _build(_report(item), runner=runner, config=DigestBuildConfig())

    assert digest.status == "partial"
    assert digest.main_items[0].summary_status == "fallback"
    assert "证据摘录" in digest.main_items[0].summary_zh
    assert digest.summary_errors


def test_invalid_saved_evidence_cannot_become_a_digest_citation() -> None:
    item = _item(
        "legacy-verified",
        status="verified",
        reason="official_source",
        evidence=[_evidence(strict=False)],
    )
    digest = _build(
        _report(item, schema_version="1.1"),
        config=DigestBuildConfig(),
    )

    assert digest.status == "partial"
    assert digest.main_items[0].evidence_refs == []
    assert "missing_saved_evidence" in digest.summary_errors[0]


def test_digest_schema_rejects_fact_lead_cross_contamination() -> None:
    item = _build(_report(_item("lead"))).lead_items[0]
    payload = {
        "digest_id": "bad",
        "run_id": "run",
        "generated_at": NOW.isoformat(),
        "status": "complete",
        "main_items": [item.model_dump(mode="json")],
        "lead_items": [],
    }

    with pytest.raises(ValidationError, match="主榜"):
        Digest.model_validate(payload)


def test_max_items_prioritizes_verified_items() -> None:
    verified = _item(
        "verified",
        status="verified",
        reason="official_source",
        evidence=[_evidence()],
        relevance=100,
        heat=100,
    )
    leads = [
        _item("lead-0", title="OpenAI releases image model"),
        _item("lead-1", title="OpenAI changes pricing policy"),
        _item("lead-2", title="OpenAI funds robotics research"),
    ]

    digest = _build(
        _report(verified, *leads),
        config=DigestBuildConfig(max_items=2, use_codex=False),
    )

    assert len(digest.all_items) == 2
    assert len(digest.main_items) == 1
    assert len(digest.lead_items) == 1
