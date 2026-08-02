from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mynews.application.validation import validate_run_file
from mynews.domain.models import (
    CollectionRequest,
    Evidence,
    EvidenceValidation,
    NewsItem,
    RunReport,
    SourceResult,
)
from mynews.infrastructure.http import HttpResponse
from mynews.sources.builtins.official_pages import OpenAiNewsPlugin
from mynews.sources.registry import SourceRegistry
from mynews.verification.codex import _content_hash

BODY = (
    '<meta property="article:published_time" content="2026-08-02T01:00:00Z">'
    "<h1>Official launch of Model 5.</h1>"
)


class FakeHttp:
    def get(self, url: str, **kwargs: object) -> HttpResponse:
        del kwargs
        return HttpResponse(
            status_code=200,
            headers={},
            body=BODY.encode(),
            final_url=url,
        )


def _report() -> RunReport:
    evidence = Evidence(
        url="https://developers.openai.com/api/docs/models",
        publisher="OpenAI",
        title="Model 5 launches",
        published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 2, 9, 30, tzinfo=UTC),
        excerpt="Official launch of Model 5.",
        content_hash=_content_hash(BODY),
        validation=EvidenceValidation(
            reachable=True, official_domain=True, excerpt_matched=True
        ),
    )
    item = NewsItem(
        id="evt_123",
        event_key="event-123",
        event_type="model_release",
        title_original="Model 5 launches",
        language_original="en",
        title_zh="Model 5 发布",
        summary_zh="官方发布 Model 5。",
        published_at=evidence.published_at,
        first_seen_at=evidence.retrieved_at,
        heat_score=20,
        relevance_score=80,
        discovery_sources=["openai"],
        source_roles=["primary"],
        verification_status="verified",
        verification_reason="codex_primary_evidence",
        primary_evidence=[evidence],
        content_hash="sha256:item",
        canonical_url=str(evidence.url),
    )
    return RunReport(
        run_id="run-1",
        status="complete",
        requested_range=CollectionRequest.model_validate(
            {
                "from": "2026-08-01T00:00:00+00:00",
                "to": "2026-08-03T00:00:00+00:00",
                "verification_budget": 30,
            }
        ),
        started_at=evidence.retrieved_at,
        finished_at=evidence.retrieved_at,
        sources=[
            SourceResult(
                source_id="openai",
                role="primary",
                health="healthy",
                fetched_count=1,
                accepted_count=1,
                duration_ms=1,
            )
        ],
        stats={"verified_count": 1},
        items=[item],
    )


def test_validate_can_recheck_every_verified_evidence(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(
        json.dumps(_report().model_dump(mode="json", by_alias=True)),
        encoding="utf-8",
    )
    plugin = OpenAiNewsPlugin()
    registry = SourceRegistry([plugin], http=FakeHttp())

    result = validate_run_file(path, check_evidence=True, registry=registry)

    assert result.passed
    assert result.verified_count == 1
    assert result.evidence_count == 1
    assert result.evidence_checked
