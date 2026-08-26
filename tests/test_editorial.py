from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mynews.application.editorial import (
    CodexEditorialSuggestionRunner,
    EditorialReviewConfig,
    build_editorial_review,
    write_editorial_review,
)
from mynews.application.feedback import render_feedback_block
from mynews.cli import main
from mynews.domain.editorial import EditorialReview
from mynews.domain.models import Digest, DigestItem


def _candidate(
    *,
    business_date: str,
    event_key: str,
    title: str,
    source: str = "fixture-source",
) -> dict[str, object]:
    timestamp = f"{business_date}T00:00:00+00:00"
    return {
        "id": event_key,
        "candidateRef": f"{business_date}:{event_key}",
        "idScope": "global",
        "title": title,
        "url": f"https://example.com/{event_key}",
        "source": source,
        "sourceRole": "discovery",
        "firstSeenAt": timestamp,
        "duplicateGroupId": event_key,
        "multiSources": [source],
        "repeat_count": 1,
    }


def _write_candidates(
    root: Path,
    business_date: str,
    candidates: list[dict[str, object]],
) -> None:
    path = root / "output" / "editorial" / business_date / "candidates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "date": business_date,
                "generatedAt": f"{business_date}T09:00:00+08:00",
                "candidates": candidates,
            }
        ),
        encoding="utf-8",
    )


def _digest_item(
    event_key: str,
    title: str,
    *,
    verified: bool,
    lifecycle: str = "new",
    content_hash: str = "hash-1",
) -> DigestItem:
    return DigestItem(
        event_key=event_key,
        event_type="model_release",
        title_zh=title,
        summary_zh=f"{title} 摘要",
        impact_zh="影响判断",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        verification_status="verified" if verified else "unverified",
        verification_reason="official_source" if verified else "pending",
        evidence_refs=[],
        source_item_keys=[event_key],
        source_content_hash=content_hash,
        source_title_original=title,
        canonical_url=f"https://example.com/{event_key}",
        published_at=datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
        relevance_score=80,
        heat_score=70,
        freshness_score=90,
        event_type_score=100,
        rank_score=85.0,
        summary_status="not_requested",
    )


def _write_digest(
    root: Path,
    digest_date: str,
    items: list[DigestItem],
) -> None:
    digest = Digest(
        digest_id=f"digest-{digest_date}",
        run_id=f"run-{digest_date}",
        generated_at=datetime.fromisoformat(f"{digest_date}T18:00:00+08:00"),
        status="complete",
        main_items=[item for item in items if item.verification_status == "verified"],
        lead_items=[item for item in items if item.verification_status == "unverified"],
    )
    path = root / "output" / "digests" / f"{digest.digest_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(digest.model_dump(mode="json")), encoding="utf-8")


def _write_ledger(root: Path, rows: list[dict[str, str]]) -> None:
    path = root / "output" / "editorial" / "publication-ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("date", "event_id", "title", "platform", "url", "published_at"),
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_feedback(root: Path, weeks: list[str]) -> None:
    path = root / "output" / "editorial" / "weekly-feedback.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = [
        render_feedback_block(week, "fixture", 10, 2, 1, 1, "反馈")
        for week in weeks
    ]
    path.write_text("# 每周反馈\n\n" + "\n".join(blocks), encoding="utf-8")


def _seed_history(root: Path, *, complete: bool) -> None:
    weeks = ["2026-W31", "2026-W32", "2026-W33", "2026-W34"]
    dates = ["2026-07-27", "2026-08-03", "2026-08-10", "2026-08-17"]
    for week, business_date in zip(weeks, dates, strict=True):
        event = f"event-{week}"
        _write_candidates(root, business_date, [_candidate(
            business_date=business_date, event_key=event, title=f"标题 {week}"
        )])
        _write_digest(
            root,
            business_date,
            [_digest_item(event, f"标题 {week}", verified=True)],
        )
    if complete:
        rows = [
            {
                "date": "2026-08-17",
                "event_id": "event-published",
                "title": "已发布",
                "platform": "fixture",
                "url": "https://example.com/published",
                "published_at": "2026-08-17T12:00:00+08:00",
            }
            for _ in range(10)
        ]
        _write_ledger(root, rows)
        _write_feedback(root, weeks)


def test_incomplete_week_is_partial_and_explains_missing_inputs(tmp_path: Path) -> None:
    _seed_history(tmp_path, complete=False)

    review = build_editorial_review(
        tmp_path, "2026-W34", config=EditorialReviewConfig(use_codex=False)
    )

    assert review.status == "partial"
    assert review.codex.mode == "disabled"
    assert "ten_publications" in review.inputs.missing_requirements
    assert "publication_feedback" in review.inputs.missing_requirements
    assert "four_complete_iso_weeks" in review.inputs.missing_requirements


def test_complete_week_has_three_layers_and_atomic_latest_outputs(
    tmp_path: Path,
) -> None:
    _seed_history(tmp_path, complete=True)
    _write_candidates(
        tmp_path,
        "2026-08-17",
        [
            _candidate(
                business_date="2026-08-17",
                event_key="event-published",
                title="已发布",
            ),
            _candidate(
                business_date="2026-08-17",
                event_key="event-pending",
                title="待核查",
            ),
            _candidate(
                business_date="2026-08-17",
                event_key="event-unpublished",
                title="未发布",
            ),
        ],
    )
    _write_digest(
        tmp_path,
        "2026-08-17",
        [
            _digest_item("event-published", "已发布", verified=True),
            _digest_item("event-pending", "待核查", verified=False),
            _digest_item("event-unpublished", "未发布", verified=True),
        ],
    )

    review = build_editorial_review(
        tmp_path, "2026-W34", config=EditorialReviewConfig(use_codex=False)
    )
    assert review.status == "complete"
    assert [item.event_key for item in review.published] == ["event-published"]
    assert [item.event_key for item in review.pending] == ["event-pending"]
    assert review.stats.unpublished_count >= 1
    assert review.feedback.reads == 40
    assert review.feedback.favorites == 8
    assert review.feedback.shares == 4
    assert review.feedback.new_followers == 4

    paths = write_editorial_review(review, tmp_path / "output/editorial/reviews")
    assert all(path.exists() for path in paths)
    assert json.loads(paths[0].read_text(encoding="utf-8"))["schema_version"] == "1.0"
    assert paths[0].name == "2026-W34.json"
    assert paths[2].name == "latest.json"


def test_editorial_output_failure_preserves_previous_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_history(tmp_path, complete=True)
    review = build_editorial_review(
        tmp_path, "2026-W34", config=EditorialReviewConfig(use_codex=False)
    )
    out_dir = tmp_path / "output/editorial/reviews"
    paths = write_editorial_review(review, out_dir)
    previous = {path: path.read_bytes() for path in paths}

    def fail_commit(self: object, writes: object) -> None:
        del self, writes
        raise OSError("injected commit failure")

    monkeypatch.setattr(
        "mynews.application.editorial.ArtifactCommitter.commit", fail_commit
    )
    with pytest.raises(ValueError, match="编辑复盘输出提交失败"):
        write_editorial_review(review, out_dir)

    assert {path: path.read_bytes() for path in paths} == previous


def test_layers_do_not_promote_candidate_only_and_updates_are_target_scoped(
    tmp_path: Path,
) -> None:
    _seed_history(tmp_path, complete=True)
    _write_candidates(
        tmp_path,
        "2026-08-17",
        [
            _candidate(
                business_date="2026-08-17",
                event_key="event-W34",
                title="本周事件",
            ),
            _candidate(
                business_date="2026-08-17",
                event_key="candidate-only",
                title="只有候选",
            ),
        ],
    )
    _write_digest(
        tmp_path,
        "2026-08-17",
        [
            _digest_item("event-W34", "本周事件", verified=True),
            _digest_item(
                "event-W31",
                "历史事件本周更新",
                verified=True,
                lifecycle="updated",
                content_hash="hash-2",
            ),
        ],
    )
    _write_ledger(
        tmp_path,
        [
            {
                "date": "2026-08-17",
                "event_id": "candidate-only",
                "title": "只有候选",
                "platform": "fixture",
                "url": "https://example.com/candidate-only",
                "published_at": "2026-08-17T12:00:00+08:00",
            }
        ]
        * 10,
    )

    review = build_editorial_review(
        tmp_path, "2026-W34", config=EditorialReviewConfig(use_codex=False)
    )

    layer_keys = {
        item.event_key
        for item in (*review.published, *review.unpublished, *review.pending)
    }
    assert "candidate-only" not in layer_keys
    assert [hint.references for hint in review.substantive_updates] == [["event-W31"]]


def test_editorial_review_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        EditorialReview.model_validate({"schema_version": "1.0", "unknown": True})


def test_unknown_codex_reference_discards_model_suggestion(
    tmp_path: Path,
) -> None:
    _seed_history(tmp_path, complete=True)

    class UnknownReferenceRunner:
        def run(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "kind": "trend",
                            "text": "不可接受的建议",
                            "references": ["unknown-event"],
                        }
                    ]
                }
            )

    review = build_editorial_review(
        tmp_path,
        "2026-W34",
        config=EditorialReviewConfig(use_codex=True),
        runner=UnknownReferenceRunner(),  # type: ignore[arg-type]
    )

    assert review.status == "partial"
    assert review.codex.mode == "partial"
    assert review.codex.accepted_count == 0
    assert review.codex.error == "unknown_codex_reference"
    assert all(
        item.kind not in {"trend", "model_suggestion"}
        for item in review.suggestions
    )


def test_editorial_codex_runner_uses_shared_process_adapter() -> None:
    captured: dict[str, object] = {}

    class Adapter:
        def run(self, request: object) -> str:
            captured["request"] = request
            return '{"suggestions": []}'

    output = CodexEditorialSuggestionRunner(adapter=Adapter()).run(  # type: ignore[arg-type]
        "只读提示",
        model="fixture-model",
        timeout=3.0,
        reasoning_effort="medium",
    )

    request = captured["request"]
    assert output == '{"suggestions": []}'
    assert request.temp_prefix == "mynews-editorial-codex-"  # type: ignore[union-attr]
    assert request.model == "fixture-model"  # type: ignore[union-attr]


def test_editorial_cli_is_offline_and_returns_partial_for_missing_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = main(
        [
            "editorial",
            "review",
            "--week",
            "2026-W34",
            "--out-dir",
            "output/editorial/reviews",
            "--no-codex",
        ]
    )

    assert result == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "partial"
    assert (tmp_path / "output/editorial/reviews/2026-W34.json").is_file()
    assert (tmp_path / "output/editorial/reviews/latest.md").is_file()
