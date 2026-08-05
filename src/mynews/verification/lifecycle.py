"""已保存第一方证据的复核生命周期。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mynews.domain.models import Evidence, EvidenceValidation
from mynews.domain.normalization import normalize_url
from mynews.infrastructure.clock import Clock, SystemClock
from mynews.infrastructure.http import HttpClient
from mynews.verification.protocol import VerificationTarget
from mynews.verification.security import (
    content_hash,
    date_matches,
    host,
    is_official_url,
    is_search_url,
    normalize_excerpt,
    visible_text,
)


@dataclass(frozen=True, slots=True)
class EvidenceReviewResult:
    status: Literal["current", "changed_supporting", "failed"]
    reason: str
    evidence: Evidence | None = None
    warning: str | None = None


class EvidenceLifecycleReviewer:
    """整页变化不自动失效，但支持事实与安全边界必须仍然成立。"""

    def __init__(
        self,
        http: HttpClient,
        *,
        clock: Clock | None = None,
        official_domains: tuple[str, ...] = (),
        github_organizations: tuple[str, ...] = (),
    ) -> None:
        self._http = http
        self._clock = clock or SystemClock()
        self._domains = tuple(official_domains)
        self._organizations = tuple(github_organizations)

    def review(
        self,
        target: VerificationTarget,
        evidence: Evidence,
        *,
        timeout: float,
    ) -> EvidenceReviewResult:
        domains = tuple(
            dict.fromkeys((*target.official_domains, *self._domains))
        )
        organizations = tuple(
            dict.fromkeys(
                (
                    *target.official_github_organizations,
                    *self._organizations,
                )
            )
        )
        url = str(evidence.url)
        if not is_official_url(url, domains, organizations):
            return EvidenceReviewResult("failed", "evidence_not_official")
        if is_search_url(url):
            return EvidenceReviewResult(
                "failed",
                "search_summary_not_evidence",
            )
        if evidence.published_at is None:
            return EvidenceReviewResult("failed", "evidence_date_missing")
        try:
            response = self._http.get(url, timeout=timeout)
        except Exception:
            return EvidenceReviewResult("failed", "evidence_unreachable")
        final_url = response.final_url or url
        if not is_official_url(final_url, domains, organizations):
            return EvidenceReviewResult("failed", "redirect_not_official")
        if is_search_url(final_url):
            return EvidenceReviewResult(
                "failed",
                "search_summary_not_evidence",
            )
        if host(url) != host(final_url):
            return EvidenceReviewResult("failed", "redirect_anomaly")
        body = response.text()
        if normalize_excerpt(evidence.excerpt) not in normalize_excerpt(
            visible_text(body)
        ):
            return EvidenceReviewResult(
                "failed",
                "evidence_excerpt_mismatch",
            )
        if not date_matches(evidence.published_at, body):
            return EvidenceReviewResult("failed", "evidence_date_mismatch")
        digest = content_hash(body)
        reviewed_at = self._clock.now()
        if digest == evidence.content_hash:
            current = evidence.model_copy(
                update={
                    "url": normalize_url(final_url),
                    "reviewed_at": reviewed_at,
                    "validation": EvidenceValidation(
                        reachable=True,
                        official_domain=True,
                        redirect_safe=True,
                        excerpt_matched=True,
                        date_matched=True,
                        content_hash_matched=True,
                        lifecycle_status="current",
                    ),
                }
            )
            return EvidenceReviewResult("current", "", current)
        changed = evidence.model_copy(
            update={
                "url": normalize_url(final_url),
                "content_hash": digest,
                "previous_content_hash": evidence.content_hash,
                "reviewed_at": reviewed_at,
                "validation": EvidenceValidation(
                    reachable=True,
                    official_domain=True,
                    redirect_safe=True,
                    excerpt_matched=True,
                    date_matched=True,
                    content_hash_matched=False,
                    lifecycle_status="changed_supporting",
                ),
            }
        )
        return EvidenceReviewResult(
            "changed_supporting",
            "",
            changed,
            "evidence_body_changed_support_still_present",
        )
