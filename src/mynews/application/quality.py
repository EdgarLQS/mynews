"""执行确定性的离线情报质量评估并原子输出结果。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from mynews.application.output_safety import ensure_safe_output
from mynews.domain.quality import (
    CandidateCoverage,
    DigestIsolation,
    MergeQuality,
    PendingEvolution,
    QualityCase,
    QualityEvaluation,
    QualityFailure,
    QualitySnapshot,
    QualitySuite,
    RankingStability,
    VerifiedEscalations,
)
from mynews.storage.artifact_committer import ArtifactCommitter, ArtifactWrite


class QualityEvaluationError(ValueError):
    """质量评估样本或输出无效。"""


class QualityEvaluator:
    """比较 suite 中的期望与实际快照，不执行任何外部 I/O。"""

    def evaluate(self, suite: QualitySuite) -> QualityEvaluation:
        failures: list[QualityFailure] = []
        coverage, coverage_failures = _candidate_coverage(suite)
        failures.extend(coverage_failures)
        escalations, escalation_failures = _verified_escalations(suite)
        failures.extend(escalation_failures)
        merges, merge_failures = _merge_quality(suite)
        failures.extend(merge_failures)
        pending, pending_failures = _pending_evolution(suite)
        failures.extend(pending_failures)
        isolation, isolation_failures = _digest_isolation(suite)
        failures.extend(isolation_failures)
        ranking, ranking_failures = _ranking_stability(suite)
        failures.extend(ranking_failures)
        failures.sort(key=lambda item: (item.case_id, item.rule, item.detail))
        return QualityEvaluation(
            suite_id=suite.suite_id,
            status="failed" if failures else "passed",
            case_count=len(suite.cases),
            category_counts=dict(
                sorted(Counter(case.category for case in suite.cases).items())
            ),
            candidate_coverage=coverage,
            verified_escalations=escalations,
            merge_quality=merges,
            pending_evolution=pending,
            digest_isolation=isolation,
            ranking_stability=ranking,
            failures=failures,
        )


def load_quality_suite(path: Path) -> QualitySuite:
    """读取并校验自包含 suite.json，不访问网络或项目运行目录。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return QualitySuite.model_validate(payload)
    except (OSError, TypeError, ValueError) as error:
        raise QualityEvaluationError("质量评估样本无效") from error


def write_quality_evaluation(
    evaluation: QualityEvaluation, out_dir: Path
) -> tuple[Path, Path]:
    """以一个 ArtifactCommitter 批次提交 JSON 与 Markdown。"""

    json_path = out_dir / "quality-evaluation.json"
    markdown_path = out_dir / "quality-evaluation.md"
    payload = evaluation.model_dump(mode="json")
    _ensure_safe_evaluation(evaluation)
    try:
        ArtifactCommitter().commit(
            (
                ArtifactWrite.json(json_path, payload),
                ArtifactWrite.text(
                    markdown_path, render_quality_evaluation(evaluation)
                ),
            )
        )
    except Exception as error:
        raise QualityEvaluationError("质量评估输出提交失败") from error
    return json_path, markdown_path


def render_quality_evaluation(evaluation: QualityEvaluation) -> str:
    """渲染不含正文和路径的确定性中文质量报告。"""

    _ensure_safe_evaluation(evaluation)
    lines = _render_overview(evaluation)
    lines.extend(_render_metrics(evaluation))
    lines.extend(_render_failures(evaluation))
    return "\n".join(lines).rstrip() + "\n"


def _ensure_safe_evaluation(evaluation: QualityEvaluation) -> None:
    try:
        ensure_safe_output(
            evaluation.model_dump(mode="json"), root="quality_evaluation"
        )
    except ValueError as error:
        raise QualityEvaluationError("质量评估输出不安全") from error


def _render_overview(evaluation: QualityEvaluation) -> list[str]:
    return [
        "# mynews 情报质量评估",
        "",
        f"- 样本集：`{evaluation.suite_id}`",
        f"- 状态：`{evaluation.status}`",
        f"- 案例数：`{evaluation.case_count}`",
        "",
    ]


def _render_metrics(evaluation: QualityEvaluation) -> list[str]:
    coverage = evaluation.candidate_coverage
    return _render_coverage(coverage) + _render_quality_sections(evaluation)


def _render_coverage(coverage: CandidateCoverage) -> list[str]:
    return [
        "## 候选覆盖",
        "",
        f"- 期望：`{coverage.expected_count}`；实际：`{coverage.observed_count}`；",
        f"  覆盖：`{coverage.covered_count}`；比例：`{coverage.coverage_ratio:.6f}`",
        f"- 缺失：{_items(coverage.missing)}",
        "",
    ]


def _render_quality_sections(evaluation: QualityEvaluation) -> list[str]:
    verified = evaluation.verified_escalations
    merge = evaluation.merge_quality
    pending = evaluation.pending_evolution
    isolation = evaluation.digest_isolation
    ranking = evaluation.ranking_stability
    return [
        "## verified 错误升级",
        "",
        f"- 数量：`{verified.count}`；事件：{_items(verified.event_keys)}",
        "",
        "## 合并质量",
        "",
        (
            f"- 不安全合并：`{merge.false_merge_count}`；"
            f"漏合并：`{merge.missed_merge_count}`"
        ),
        f"- 不安全分组：{_groups(merge.false_merge_groups)}",
        f"- 漏合并分组：{_groups(merge.missed_merge_groups)}",
        "",
        "## pending 演进",
        "",
        f"- 不匹配：`{pending.mismatch_count}`；案例：{_items(pending.mismatches)}",
        "",
        "## 主榜/线索隔离",
        "",
        (
            f"- 主榜污染：`{isolation.main_contamination_count}`；"
            f"事件：{_items(isolation.main_contamination)}"
        ),
        (
            f"- 线索污染：`{isolation.lead_contamination_count}`；"
            f"事件：{_items(isolation.lead_contamination)}"
        ),
        "",
        "## 排序稳定性",
        "",
        (
            f"- 不稳定案例：`{ranking.unstable_case_count}`；"
            f"案例：{_items(ranking.unstable_cases)}"
        ),
        "",
        "## 失败规则",
        "",
    ]


def _render_failures(evaluation: QualityEvaluation) -> list[str]:
    if evaluation.failures:
        return [
            f"- `{failure.case_id}` `{failure.rule}`：{failure.detail}"
            for failure in evaluation.failures
        ]
    return ["- 无"]


def _candidate_coverage(
    suite: QualitySuite,
) -> tuple[CandidateCoverage, list[QualityFailure]]:
    expected_count = observed_count = covered_count = 0
    missing: list[str] = []
    failures: list[QualityFailure] = []
    for case in suite.cases:
        expected = set(case.expected.candidate_event_keys)
        actual = set(case.actual.candidate_event_keys)
        case_missing = sorted(expected - actual)
        expected_count += len(expected)
        observed_count += len(actual)
        covered_count += len(expected - set(case_missing))
        missing.extend(f"{case.case_id}:{key}" for key in case_missing)
        if case_missing:
            failures.append(
                _failure(case, "candidate_coverage", ", ".join(case_missing))
            )
    ratio = covered_count / expected_count if expected_count else 1.0
    return (
        CandidateCoverage(
            expected_count=expected_count,
            observed_count=observed_count,
            covered_count=covered_count,
            coverage_ratio=round(ratio, 6),
            missing=sorted(missing),
        ),
        failures,
    )


def _verified_escalations(
    suite: QualitySuite,
) -> tuple[VerifiedEscalations, list[QualityFailure]]:
    event_keys: list[str] = []
    failures: list[QualityFailure] = []
    for case in suite.cases:
        unexpected = sorted(
            set(case.actual.verified_event_keys)
            - set(case.expected.verified_event_keys)
        )
        missing = sorted(
            set(case.expected.verified_event_keys)
            - set(case.actual.verified_event_keys)
        )
        event_keys.extend(f"{case.case_id}:{key}" for key in unexpected)
        if unexpected:
            failures.append(
                _failure(case, "verified_escalation", ", ".join(unexpected))
            )
        if missing:
            failures.append(_failure(case, "verified_missing", ", ".join(missing)))
    event_keys.sort()
    return VerifiedEscalations(count=len(event_keys), event_keys=event_keys), failures


def _merge_quality(
    suite: QualitySuite,
) -> tuple[MergeQuality, list[QualityFailure]]:
    false_groups: list[list[str]] = []
    missed_groups: list[list[str]] = []
    failures: list[QualityFailure] = []
    for case in suite.cases:
        expected = _groups_as_set(case.expected.merge_groups)
        actual = _groups_as_set(case.actual.merge_groups)
        false = sorted(actual - expected)
        missed = sorted(expected - actual)
        false_groups.extend([list(group) for group in false])
        missed_groups.extend([list(group) for group in missed])
        if false:
            failures.append(_failure(case, "unsafe_merge", _format_groups(false)))
        if missed:
            failures.append(_failure(case, "missed_merge", _format_groups(missed)))
    return (
        MergeQuality(
            false_merge_count=len(false_groups),
            false_merge_groups=false_groups,
            missed_merge_count=len(missed_groups),
            missed_merge_groups=missed_groups,
        ),
        failures,
    )


def _pending_evolution(
    suite: QualitySuite,
) -> tuple[PendingEvolution, list[QualityFailure]]:
    mismatches: list[str] = []
    failures: list[QualityFailure] = []
    for case in suite.cases:
        expected = _pending_pair(case.expected)
        actual = _pending_pair(case.actual)
        if expected != actual:
            mismatches.append(case.case_id)
            failures.append(_failure(case, "pending_evolution", "前后状态不匹配"))
    return PendingEvolution(
        mismatch_count=len(mismatches), mismatches=sorted(mismatches)
    ), failures


def _digest_isolation(
    suite: QualitySuite,
) -> tuple[DigestIsolation, list[QualityFailure]]:
    main_pollution: list[str] = []
    lead_pollution: list[str] = []
    failures: list[QualityFailure] = []
    for case in suite.cases:
        expected_main = set(case.expected.main_event_keys)
        actual_main = set(case.actual.main_event_keys)
        actual_verified = set(case.actual.verified_event_keys)
        expected_lead = set(case.expected.lead_event_keys)
        actual_lead = set(case.actual.lead_event_keys)
        main_bad = sorted(
            (actual_main - expected_main) | (actual_main - actual_verified)
        )
        lead_bad = sorted(
            (actual_lead & actual_verified) | (actual_lead - expected_lead)
        )
        main_missing = sorted(expected_main - actual_main)
        lead_missing = sorted(expected_lead - actual_lead)
        main_pollution.extend(f"{case.case_id}:{key}" for key in main_bad)
        lead_pollution.extend(f"{case.case_id}:{key}" for key in lead_bad)
        if main_bad:
            failures.append(_failure(case, "main_pollution", ", ".join(main_bad)))
        if lead_bad:
            failures.append(_failure(case, "lead_pollution", ", ".join(lead_bad)))
        if main_missing:
            failures.append(_failure(case, "main_missing", ", ".join(main_missing)))
        if lead_missing:
            failures.append(_failure(case, "lead_missing", ", ".join(lead_missing)))
    return (
        DigestIsolation(
            main_contamination_count=len(main_pollution),
            main_contamination=sorted(main_pollution),
            lead_contamination_count=len(lead_pollution),
            lead_contamination=sorted(lead_pollution),
        ),
        failures,
    )


def _ranking_stability(
    suite: QualitySuite,
) -> tuple[RankingStability, list[QualityFailure]]:
    unstable: list[str] = []
    failures: list[QualityFailure] = []
    for case in suite.cases:
        expected_runs = case.expected.ranking_runs
        actual_runs = case.actual.ranking_runs
        baseline = expected_runs[0] if expected_runs else []
        if any(run != baseline for run in actual_runs) or (
            bool(expected_runs) and not actual_runs
        ) or len(actual_runs) < len(expected_runs):
            unstable.append(case.case_id)
            failures.append(_failure(case, "ranking_instability", "重复排序结果不稳定"))
    return RankingStability(
        unstable_case_count=len(unstable), unstable_cases=sorted(unstable)
    ), failures


def _groups_as_set(groups: list[list[str]]) -> set[tuple[str, ...]]:
    return {tuple(sorted(set(group))) for group in groups if len(set(group)) >= 2}


def _pending_pair(snapshot: QualitySnapshot) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(sorted(snapshot.pending_before)), tuple(sorted(snapshot.pending_after))


def _failure(case: QualityCase, rule: str, detail: str) -> QualityFailure:
    return QualityFailure(
        case_id=case.case_id,
        category=case.category,
        rule=rule,
        detail=detail,
    )


def _items(items: list[str]) -> str:
    return "、".join(f"`{item}`" for item in items) if items else "无"


def _groups(groups: list[list[str]]) -> str:
    return "；".join(_format_groups([tuple(group)]) for group in groups) or "无"


def _format_groups(groups: list[tuple[str, ...]]) -> str:
    return "；".join("(" + ",".join(group) + ")" for group in groups)


__all__ = [
    "QualityEvaluationError",
    "QualityEvaluator",
    "load_quality_suite",
    "render_quality_evaluation",
    "write_quality_evaluation",
]
