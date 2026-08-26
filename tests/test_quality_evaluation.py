from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mynews.application.quality import (
    QualityEvaluationError,
    QualityEvaluator,
    load_quality_suite,
    render_quality_evaluation,
    write_quality_evaluation,
)
from mynews.domain.quality import QualityEvaluation, QualitySuite

CATEGORIES = (
    "official_direct",
    "discovery",
    "retry_failure",
    "multi_source_same_event",
    "similar_different_event",
    "pricing_change",
    "prompt_injection",
    "evidence_drift",
)


def _snapshot(*, event_key: str, verified: bool = True) -> dict[str, object]:
    return {
        "candidate_event_keys": [event_key],
        "verified_event_keys": [event_key] if verified else [],
        "merge_groups": [],
        "pending_before": [],
        "pending_after": [],
        "main_event_keys": [event_key] if verified else [],
        "lead_event_keys": [] if verified else [event_key],
        "ranking_runs": [[event_key], [event_key]],
    }


def _case(case_id: str, category: str) -> dict[str, object]:
    snapshot = _snapshot(event_key=case_id, verified=category != "discovery")
    return {
        "case_id": case_id,
        "category": category,
        "expected": snapshot,
        "actual": copy.deepcopy(snapshot),
    }


def _suite_payload() -> dict[str, object]:
    cases = [
        _case(f"{category}-{index}", category)
        for category in CATEGORIES
        for index in range(1, 4)
    ]
    return {"schema_version": "1.0", "suite_id": "test-suite", "cases": cases}


def test_quality_evaluator_passes_fixed_suite_and_reports_each_metric() -> None:
    suite = QualitySuite.model_validate(_suite_payload())

    evaluation = QualityEvaluator().evaluate(suite)

    assert evaluation.status == "passed"
    assert evaluation.case_count == 24
    assert evaluation.category_counts == {category: 3 for category in CATEGORIES}
    assert evaluation.candidate_coverage.missing == []
    assert evaluation.verified_escalations.count == 0
    assert evaluation.merge_quality.false_merge_count == 0
    assert evaluation.merge_quality.missed_merge_count == 0
    assert evaluation.pending_evolution.mismatch_count == 0
    assert evaluation.digest_isolation.main_contamination_count == 0
    assert evaluation.digest_isolation.lead_contamination_count == 0
    assert evaluation.ranking_stability.unstable_case_count == 0
    assert not hasattr(evaluation, "score")


def test_quality_evaluator_rejects_verified_escalation_and_main_pollution() -> None:
    payload = _suite_payload()
    first_case = payload["cases"][0]
    assert isinstance(first_case, dict)
    actual = first_case["actual"]
    assert isinstance(actual, dict)
    actual["verified_event_keys"] = ["unexpected-event"]
    actual["main_event_keys"] = ["unexpected-event"]

    evaluation = QualityEvaluator().evaluate(QualitySuite.model_validate(payload))

    assert evaluation.status == "failed"
    assert evaluation.verified_escalations.event_keys == [
        "official_direct-1:unexpected-event"
    ]
    assert evaluation.digest_isolation.main_contamination == [
        "official_direct-1:unexpected-event"
    ]
    assert {failure.rule for failure in evaluation.failures} >= {
        "verified_escalation",
        "main_pollution",
    }


def test_quality_evaluator_rejects_missing_items_and_unstable_ranking() -> None:
    payload = _suite_payload()
    first_case = payload["cases"][0]
    assert isinstance(first_case, dict)
    actual = first_case["actual"]
    assert isinstance(actual, dict)
    actual["verified_event_keys"] = []
    actual["main_event_keys"] = []
    actual["ranking_runs"] = [["official_direct-1"], ["different-order"]]

    evaluation = QualityEvaluator().evaluate(QualitySuite.model_validate(payload))

    assert evaluation.status == "failed"
    assert {failure.rule for failure in evaluation.failures} >= {
        "verified_missing",
        "main_missing",
        "ranking_instability",
    }


def test_quality_suite_requires_three_cases_per_category() -> None:
    payload = _suite_payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    cases.pop()

    with pytest.raises(ValueError, match="每个评估类别至少需要 3 个案例"):
        QualitySuite.model_validate(payload)


def test_quality_evaluation_outputs_are_atomic_and_deterministic(
    tmp_path: Path,
) -> None:
    suite = QualitySuite.model_validate(_suite_payload())
    evaluation = QualityEvaluator().evaluate(suite)

    paths = write_quality_evaluation(evaluation, tmp_path)

    assert paths == (
        tmp_path / "quality-evaluation.json",
        tmp_path / "quality-evaluation.md",
    )
    first_json = paths[0].read_text(encoding="utf-8")
    first_markdown = paths[1].read_text(encoding="utf-8")
    write_quality_evaluation(evaluation, tmp_path)
    assert paths[0].read_text(encoding="utf-8") == first_json
    assert paths[1].read_text(encoding="utf-8") == first_markdown
    assert json.loads(first_json)["schema_version"] == "1.0"
    assert QualityEvaluation.model_validate_json(first_json) == evaluation
    assert QualityEvaluation.model_json_schema()["properties"]["schema_version"]
    assert "# mynews 情报质量评估" in first_markdown


def test_quality_evaluation_write_failure_keeps_previous_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = QualitySuite.model_validate(_suite_payload())
    evaluation = QualityEvaluator().evaluate(suite)
    write_quality_evaluation(evaluation, tmp_path)
    before = (tmp_path / "quality-evaluation.json").read_bytes()

    def fail_commit(self: object, writes: object) -> None:
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(
        "mynews.application.quality.ArtifactCommitter.commit", fail_commit
    )

    with pytest.raises(QualityEvaluationError, match="质量评估输出提交失败"):
        write_quality_evaluation(evaluation, tmp_path)
    assert (tmp_path / "quality-evaluation.json").read_bytes() == before


def test_quality_evaluation_rejects_unsafe_output_without_writing(
    tmp_path: Path,
) -> None:
    payload = _suite_payload()
    payload["suite_id"] = "/Users/private-suite"
    evaluation = QualityEvaluator().evaluate(QualitySuite.model_validate(payload))

    with pytest.raises(QualityEvaluationError, match="质量评估输出不安全"):
        write_quality_evaluation(evaluation, tmp_path)
    assert not (tmp_path / "quality-evaluation.json").exists()
    assert not (tmp_path / "quality-evaluation.md").exists()


def test_load_quality_suite_rejects_unknown_major_without_echoing_path(
    tmp_path: Path,
) -> None:
    suite_path = tmp_path / "suite.json"
    payload = _suite_payload()
    payload["schema_version"] = "2.0"
    suite_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityEvaluationError, match="质量评估样本无效") as raised:
        load_quality_suite(suite_path)
    assert str(suite_path) not in str(raised.value)


def test_render_quality_evaluation_is_chinese_and_has_no_composite_score() -> None:
    suite = QualitySuite.model_validate(_suite_payload())
    evaluation = QualityEvaluator().evaluate(suite)

    markdown = render_quality_evaluation(evaluation)

    assert "## 候选覆盖" in markdown
    assert "## verified 错误升级" in markdown
    assert "## 主榜/线索隔离" in markdown
    assert "综合分" not in markdown
