"""离线情报质量评估的独立 1.0 数据契约。"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QualityCategory = Literal[
    "official_direct",
    "discovery",
    "retry_failure",
    "multi_source_same_event",
    "similar_different_event",
    "pricing_change",
    "prompt_injection",
    "evidence_drift",
]

QUALITY_CATEGORIES: tuple[QualityCategory, ...] = (
    "official_direct",
    "discovery",
    "retry_failure",
    "multi_source_same_event",
    "similar_different_event",
    "pricing_change",
    "prompt_injection",
    "evidence_drift",
)


class QualityContractModel(BaseModel):
    """评估契约拒绝未知字段，避免样本语义悄悄漂移。"""

    model_config = ConfigDict(extra="forbid")


class QualitySnapshot(QualityContractModel):
    """一个案例的期望或实际结果快照。"""

    candidate_event_keys: list[str] = Field(default_factory=list)
    verified_event_keys: list[str] = Field(default_factory=list)
    merge_groups: list[list[str]] = Field(default_factory=list)
    pending_before: list[str] = Field(default_factory=list)
    pending_after: list[str] = Field(default_factory=list)
    main_event_keys: list[str] = Field(default_factory=list)
    lead_event_keys: list[str] = Field(default_factory=list)
    ranking_runs: list[list[str]] = Field(default_factory=list)


class QualityCase(QualityContractModel):
    """单个固定质量评估案例。"""

    case_id: str = Field(min_length=1)
    category: QualityCategory
    expected: QualitySnapshot
    actual: QualitySnapshot


class QualitySuite(QualityContractModel):
    """自包含的离线评估样本集。"""

    schema_version: Literal["1.0"] = "1.0"
    suite_id: str = Field(min_length=1)
    cases: list[QualityCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fixed_categories(self) -> QualitySuite:
        counts = Counter(case.category for case in self.cases)
        if any(counts[category] < 3 for category in QUALITY_CATEGORIES):
            raise ValueError("每个评估类别至少需要 3 个案例")
        if len(self.cases) < 24:
            raise ValueError("评估样本至少需要 24 个案例")
        if len(set(case.case_id for case in self.cases)) != len(self.cases):
            raise ValueError("评估案例 ID 必须唯一")
        return self


class CandidateCoverage(QualityContractModel):
    expected_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    covered_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)
    missing: list[str] = Field(default_factory=list)


class VerifiedEscalations(QualityContractModel):
    count: int = Field(ge=0)
    event_keys: list[str] = Field(default_factory=list)


class MergeQuality(QualityContractModel):
    false_merge_count: int = Field(ge=0)
    false_merge_groups: list[list[str]] = Field(default_factory=list)
    missed_merge_count: int = Field(ge=0)
    missed_merge_groups: list[list[str]] = Field(default_factory=list)


class PendingEvolution(QualityContractModel):
    mismatch_count: int = Field(ge=0)
    mismatches: list[str] = Field(default_factory=list)


class DigestIsolation(QualityContractModel):
    main_contamination_count: int = Field(ge=0)
    main_contamination: list[str] = Field(default_factory=list)
    lead_contamination_count: int = Field(ge=0)
    lead_contamination: list[str] = Field(default_factory=list)


class RankingStability(QualityContractModel):
    unstable_case_count: int = Field(ge=0)
    unstable_cases: list[str] = Field(default_factory=list)


class QualityFailure(QualityContractModel):
    case_id: str = Field(min_length=1)
    category: QualityCategory
    rule: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class QualityEvaluation(QualityContractModel):
    """QualityEvaluation 1.0，不含综合评分。"""

    schema_version: Literal["1.0"] = "1.0"
    suite_id: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    case_count: int = Field(ge=0)
    category_counts: dict[str, int] = Field(default_factory=dict)
    candidate_coverage: CandidateCoverage
    verified_escalations: VerifiedEscalations
    merge_quality: MergeQuality
    pending_evolution: PendingEvolution
    digest_isolation: DigestIsolation
    ranking_stability: RankingStability
    failures: list[QualityFailure] = Field(default_factory=list)


__all__ = [
    "QUALITY_CATEGORIES",
    "CandidateCoverage",
    "DigestIsolation",
    "MergeQuality",
    "PendingEvolution",
    "QualityCase",
    "QualityCategory",
    "QualityEvaluation",
    "QualityFailure",
    "QualitySnapshot",
    "QualitySuite",
    "RankingStability",
    "VerifiedEscalations",
]
