from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from mynews.domain.models import Evidence, NewsItem, RunReport

FIXTURE = Path(__file__).parent / "fixtures/run-report-v1.json"


def test_documented_run_fixture_is_compatible_with_v1_models() -> None:
    report = RunReport.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    assert report.schema_version == "1.0"
    assert report.requested_range.timezone == "Asia/Shanghai"
    assert report.sources[0].source_id == "hacker-news"


def test_schema_is_generated_from_the_models_and_keeps_contract_fields() -> None:
    schema = RunReport.model_json_schema()
    run_fields = schema["properties"]

    assert set(
        ("schema_version", "run_id", "status", "requested_range", "started_at",
         "finished_at", "sources", "stats", "items")
    ).issubset(run_fields)
    assert schema["$defs"]["Evidence"]["properties"]["validation"]["$ref"].endswith(
        "/EvidenceValidation"
    )


def test_unknown_optional_fields_are_accepted_for_minor_compatibility() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["producer_revision"] = "local-test"

    report = RunReport.model_validate(payload)

    assert report.schema_version == "1.0"


def test_verification_reasoning_effort_is_optional_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["requested_range"]["verification_reasoning_effort"] = "medium"

    report = RunReport.model_validate(payload)

    assert report.requested_range.verification_reasoning_effort == "medium"


def test_unknown_major_schema_version_is_rejected() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0"

    with pytest.raises(ValidationError):
        RunReport.model_validate(payload)


def test_new_minor_schema_version_is_accepted() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.1"

    report = RunReport.model_validate(payload)

    assert report.schema_version == "1.1"


def test_verified_item_requires_primary_evidence() -> None:
    with pytest.raises(ValidationError, match="primary_evidence"):
        NewsItem(
            id="evt_123",
            event_key="event-123",
            event_type="model_release",
            title_original="A release",
            language_original="en",
            title_zh="发布",
            summary_zh="事实摘要",
            published_at=datetime(2026, 8, 2, 1, 0, tzinfo=ZoneInfo("UTC")),
            first_seen_at=datetime(2026, 8, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            heat_score=20,
            relevance_score=80,
            discovery_sources=["hacker-news"],
            verification_status="verified",
            verification_reason="official_source",
            primary_evidence=[],
            content_hash="sha256:abc",
        )


def test_verified_item_requires_programmatically_validated_evidence() -> None:
    evidence = Evidence(
        url="https://official.example/news/item",
        publisher="Official Publisher",
        title="Official announcement",
        published_at=None,
        retrieved_at=datetime(2026, 8, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        excerpt="Short supporting excerpt",
        content_hash="sha256:abc",
    )

    with pytest.raises(ValidationError, match="validation"):
        NewsItem(
            id="evt_123",
            event_key="event-123",
            event_type="model_release",
            title_original="A release",
            language_original="en",
            title_zh="发布",
            summary_zh="事实摘要",
            published_at=None,
            first_seen_at=datetime(
                2026, 8, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
            heat_score=20,
            relevance_score=80,
            discovery_sources=["hacker-news"],
            verification_status="verified",
            verification_reason="official_source",
            primary_evidence=[evidence],
            content_hash="sha256:abc",
        )


def test_evidence_validation_defaults_to_explicit_false_values() -> None:
    evidence = Evidence(
        url="https://official.example/news/item",
        publisher="Official Publisher",
        title="Official announcement",
        published_at=None,
        retrieved_at=datetime(2026, 8, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        excerpt="Short supporting excerpt",
        content_hash="sha256:abc",
    )

    assert evidence.validation.reachable is False
    assert evidence.validation.official_domain is False
    assert evidence.validation.excerpt_matched is False
