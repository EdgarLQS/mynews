"""把证据生命周期复核结果应用到 RunReport。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from mynews.domain.models import (
    Evidence,
    EvidenceReview,
    NewsItem,
    RunReport,
)
from mynews.verification.lifecycle import EvidenceReviewResult
from mynews.verification.protocol import VerificationTarget


class EvidenceReviewer(Protocol):
    def review_evidence(
        self,
        target: VerificationTarget,
        evidence: Evidence,
        *,
        timeout: float,
    ) -> EvidenceReviewResult: ...


def review_report_evidence(
    report: RunReport,
    targets: Mapping[str, VerificationTarget],
    reviewer: EvidenceReviewer,
    *,
    timeout: float,
) -> RunReport:
    """返回包含显式复核结果与统计的 1.2 RunReport。"""
    updated_items: list[NewsItem] = []
    reviews: list[EvidenceReview] = []
    revalidated = 0
    changed_supporting = 0
    failed = 0

    for item in report.items:
        target = targets.get(item.event_key)
        if item.verification_status != "verified" or target is None:
            updated_items.append(item)
            continue
        updated_evidence: list[Evidence] = []
        failure_reason: str | None = None
        for evidence in item.primary_evidence:
            result = reviewer.review_evidence(
                target,
                evidence,
                timeout=timeout,
            )
            revalidated += 1
            reviews.append(
                EvidenceReview(
                    event_key=item.event_key,
                    evidence_url=str(evidence.url),
                    status=result.status,
                    reason=result.reason,
                    warning=result.warning,
                )
            )
            if result.status == "failed":
                failed += 1
                failure_reason = result.reason
                continue
            if result.status == "changed_supporting":
                changed_supporting += 1
            if result.evidence is not None:
                updated_evidence.append(result.evidence)

        if failure_reason is not None:
            updated_items.append(
                item.model_copy(
                    update={
                        "verification_status": "unverified",
                        "verification_reason": (
                            f"evidence_revalidation:{failure_reason}"
                        ),
                        "primary_evidence": [],
                    }
                )
            )
        else:
            updated_items.append(
                item.model_copy(update={"primary_evidence": updated_evidence})
            )

    stats = report.verification_stats.model_copy(
        update={
            "revalidated": revalidated,
            "changed_supporting": changed_supporting,
            "revalidation_failed": failed,
        }
    )
    legacy_stats = dict(report.stats)
    legacy_stats.update(
        {
            "evidence_revalidated": revalidated,
            "evidence_changed_supporting": changed_supporting,
            "evidence_revalidation_failed": failed,
        }
    )
    return report.model_copy(
        update={
            "schema_version": "1.2",
            "items": updated_items,
            "evidence_reviews": reviews,
            "verification_stats": stats,
            "stats": legacy_stats,
        }
    )
