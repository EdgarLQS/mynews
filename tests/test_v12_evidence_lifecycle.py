from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from mynews.domain.models import (
    Candidate,
    Evidence,
    EvidenceValidation,
    RunReport,
)
from mynews.domain.normalization import Normalizer
from mynews.domain.relevance import AiTechnologyRelevanceFilter
from mynews.infrastructure.http import HttpResponse
from mynews.verification.lifecycle import EvidenceLifecycleReviewer
from mynews.verification.protocol import VerificationTarget
from mynews.verification.resolver import EvidenceResolver, EvidenceSuggestion
from mynews.verification.security import content_hash

NOW = datetime(2026, 8, 5, 1, 30, tzinfo=UTC)
PUBLISHED = datetime(2026, 8, 4, 0, 0, tzinfo=UTC)


@dataclass
class FakeHttp:
    pages: dict[str, HttpResponse | BaseException]

    def __post_init__(self) -> None:
        self.requested: list[str] = []

    def get(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        del timeout, headers
        self.requested.append(url)
        value = self.pages[url]
        if isinstance(value, BaseException):
            raise value
        return value


def response(body: str, *, final_url: str) -> HttpResponse:
    return HttpResponse(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        body=body.encode(),
        final_url=final_url,
    )


def official_page(extra: str = "") -> str:
    return (
        "<html><head><meta property='article:published_time' "
        "content='2026-08-04T00:00:00Z'></head>"
        f"<body><article>Official AI release {extra}</article></body></html>"
    )


def target(
    canonical_url: str,
    *,
    published_at: datetime | None = PUBLISHED,
    official_domains: tuple[str, ...] = ("openai.com",),
    organizations: tuple[str, ...] = ("openai",),
) -> VerificationTarget:
    candidate = Candidate(
        source_id="hn",
        title_original="OpenAI AI release",
        url=canonical_url,
        published_at=published_at,
        excerpt="Official AI release",
        source_role="discovery",
        relevance_score=90,
    )
    item = Normalizer(source_roles={"hn": "discovery"}).normalize(
        [candidate], observed_at=NOW
    )[0]
    return VerificationTarget(
        item=item,
        source_id="hn",
        publisher="OpenAI",
        excerpt="Official AI release",
        official_domains=official_domains,
        official_github_organizations=organizations,
        source_role="discovery",
    )


def suggestion(
    url: str,
    item_target: VerificationTarget,
    *,
    digest: str | None,
) -> EvidenceSuggestion:
    return EvidenceSuggestion(
        url=url,
        publisher="OpenAI",
        title="Release",
        published_at=item_target.item.published_at,
        excerpt="Official AI release",
        content_hash=digest,
    )


def evidence(
    item_target: VerificationTarget,
    *,
    digest: str = "sha256:old",
) -> Evidence:
    return Evidence(
        url="https://openai.com/index/release",
        publisher="OpenAI",
        title="Release",
        published_at=item_target.item.published_at,
        retrieved_at=NOW,
        excerpt="Official AI release",
        content_hash=digest,
        validation=EvidenceValidation(
            reachable=True,
            official_domain=True,
            redirect_safe=True,
            excerpt_matched=True,
            date_matched=True,
            content_hash_matched=True,
            lifecycle_status="current",
        ),
    )


def report_payload(
    item: dict[str, object],
    version: str = "1.2",
) -> dict[str, object]:
    return {
        "schema_version": version,
        "run_id": "run-1",
        "status": "complete",
        "requested_range": {
            "from": "2026-08-04T00:00:00+00:00",
            "to": "2026-08-05T00:00:00+00:00",
            "verification_budget": 5,
        },
        "started_at": "2026-08-05T00:00:00+00:00",
        "finished_at": "2026-08-05T00:01:00+00:00",
        "sources": [],
        "stats": {},
        "items": [item],
    }


def test_unrelated_discovery_does_not_match_ai_inside_a_word() -> None:
    candidate = Candidate(
        source_id="hn",
        title_original="Sailing routes for beginners",
        url="https://news.example/sailing",
        source_role="discovery",
    )

    decision = AiTechnologyRelevanceFilter().evaluate(candidate)

    assert decision.relevant is False


def test_resolver_uses_fixed_order_before_codex() -> None:
    candidate_url = "https://media.example/story"
    official_url = "https://openai.com/index/release"
    other_url = "https://openai.com/index/other"
    media_body = f"<a href='{official_url}'>official</a>"
    http = FakeHttp(
        {
            candidate_url: response(media_body, final_url=candidate_url),
            official_url: response(official_page(), final_url=official_url),
        }
    )
    item_target = target(candidate_url)
    resolver = EvidenceResolver(http, official_domains=("openai.com",))

    result = resolver.resolve(
        item_target,
        timeout=5,
        codex_suggestion=suggestion(
            other_url,
            item_target,
            digest="sha256:unused",
        ),
    )

    assert result.evidence is not None
    assert result.source == "page_first_party_link"
    assert http.requested == [candidate_url, official_url]


def test_media_page_without_first_party_evidence_never_verifies_itself() -> None:
    candidate_url = "https://media.example/story"
    http = FakeHttp(
        {
            candidate_url: response(
                "<article>Official AI release</article>",
                final_url=candidate_url,
            )
        }
    )
    resolver = EvidenceResolver(http, official_domains=("openai.com",))

    result = resolver.resolve(target(candidate_url), timeout=5)

    assert result.evidence is None
    assert result.reason == "page_first_party_link_missing"


def test_candidate_cross_domain_redirect_is_terminal() -> None:
    candidate_url = "https://media.example/story"
    official_url = "https://openai.com/index/release"
    http = FakeHttp(
        {
            candidate_url: response(
                f"<a href='{official_url}'>official</a>",
                final_url="https://redirected-media.example/story",
            )
        }
    )
    item_target = target(candidate_url)
    resolver = EvidenceResolver(http, official_domains=("openai.com",))

    result = resolver.resolve(
        item_target,
        timeout=5,
        codex_suggestion=suggestion(
            official_url,
            item_target,
            digest=content_hash(official_page()),
        ),
    )

    assert result.evidence is None
    assert result.reason == "candidate_redirect_anomaly"
    assert http.requested == [candidate_url]


@pytest.mark.parametrize(
    "url",
    [
        "https://openai.com.attacker.example/release",
        "https://github.com/openai-security/fake",
    ],
)
def test_lookalike_domain_or_organization_is_rejected(url: str) -> None:
    candidate_url = "https://media.example/story"
    http = FakeHttp(
        {
            candidate_url: response("<p>none</p>", final_url=candidate_url),
        }
    )
    item_target = target(candidate_url)
    resolver = EvidenceResolver(
        http,
        official_domains=("openai.com",),
        github_organizations=("openai",),
    )

    result = resolver.resolve(
        item_target,
        timeout=5,
        codex_suggestion=suggestion(
            url,
            item_target,
            digest="sha256:not-used",
        ),
    )

    assert result.evidence is None
    assert result.reason == "evidence_not_official"
    assert url not in http.requested


def test_first_verification_requires_date_and_matching_hash() -> None:
    official_url = "https://openai.com/index/release"
    body = official_page()
    http = FakeHttp({official_url: response(body, final_url=official_url)})
    resolver = EvidenceResolver(http, official_domains=("openai.com",))

    missing_date = resolver.resolve(
        target(official_url, published_at=None),
        timeout=5,
    )
    media_target = target("https://media.example/story")
    wrong_hash = resolver.resolve_suggestion(
        media_target,
        suggestion(
            official_url,
            media_target,
            digest="sha256:wrong",
        ),
        timeout=5,
    )

    assert missing_date.evidence is None
    assert missing_date.reason == "evidence_date_missing"
    assert wrong_hash.evidence is None
    assert wrong_hash.reason == "evidence_content_hash_mismatch"


def test_lifecycle_allows_changed_body_only_when_support_remains() -> None:
    item_target = target("https://openai.com/index/release")
    changed_body = official_page("navigation changed")
    reviewer = EvidenceLifecycleReviewer(
        FakeHttp(
            {
                "https://openai.com/index/release": response(
                    changed_body,
                    final_url="https://openai.com/index/release",
                )
            }
        ),
        official_domains=("openai.com",),
    )

    result = reviewer.review(item_target, evidence(item_target), timeout=5)

    assert result.status == "changed_supporting"
    assert result.warning == "evidence_body_changed_support_still_present"
    assert result.evidence is not None
    assert result.evidence.previous_content_hash == "sha256:old"
    assert result.evidence.validation.content_hash_matched is False


def test_lifecycle_fails_when_support_or_domain_disappears() -> None:
    item_target = target("https://openai.com/index/release")
    missing = EvidenceLifecycleReviewer(
        FakeHttp(
            {
                "https://openai.com/index/release": response(
                    official_page().replace("Official AI release", "Removed"),
                    final_url="https://openai.com/index/release",
                )
            }
        ),
        official_domains=("openai.com",),
    ).review(item_target, evidence(item_target), timeout=5)
    redirected = EvidenceLifecycleReviewer(
        FakeHttp(
            {
                "https://openai.com/index/release": response(
                    official_page(),
                    final_url="https://openai.com.attacker.example/release",
                )
            }
        ),
        official_domains=("openai.com",),
    ).review(item_target, evidence(item_target), timeout=5)

    assert missing.status == "failed"
    assert missing.reason == "evidence_excerpt_mismatch"
    assert redirected.status == "failed"
    assert redirected.reason == "redirect_not_official"


def test_schema_10_and_11_migrate_but_12_rejects_weak_verified_evidence() -> None:
    item_target = target("https://openai.com/index/release")
    strong = item_target.item.model_copy(
        update={
            "verification_status": "verified",
            "verification_reason": "official_source",
            "primary_evidence": [evidence(item_target)],
        }
    ).model_dump(mode="json")
    legacy = evidence(item_target).model_copy(
        update={
            "validation": EvidenceValidation(
                reachable=True,
                official_domain=True,
                excerpt_matched=True,
            )
        }
    )
    legacy_item = {
        **strong,
        "primary_evidence": [legacy.model_dump(mode="json")],
    }

    for version in ("1.0", "1.1"):
        loaded = RunReport.model_validate(report_payload(legacy_item, version))
        assert loaded.schema_version == version
        assert loaded.items[0].verification_status == "verified"

    with pytest.raises(ValueError):
        RunReport.model_validate(report_payload(legacy_item, "1.2"))
