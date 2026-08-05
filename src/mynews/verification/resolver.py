"""按固定顺序解析并复核第一方证据。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

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
    is_safe_candidate_url,
    is_search_url,
    normalize_excerpt,
    visible_text,
)


@dataclass(frozen=True, slots=True)
class EvidenceSuggestion:
    url: str
    publisher: str
    title: str
    published_at: datetime | None
    excerpt: str
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    evidence: Evidence | None
    reason: str
    source: str | None = None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "a":
            return
        href = next(
            (
                value
                for name, value in attrs
                if name.casefold() == "href" and value
            ),
            None,
        )
        if href:
            self.links.append(href)


def _links(body: str, base_url: str) -> list[str]:
    parser = _LinkParser()
    try:
        parser.feed(body)
        parser.close()
    except (AssertionError, ValueError):
        return []
    return [urljoin(base_url, value) for value in parser.links]


class EvidenceResolver:
    """模型只提供建议，不能改变官方边界或最终判定。"""

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

    def resolve(
        self,
        target: VerificationTarget,
        *,
        timeout: float,
        codex_suggestion: EvidenceSuggestion | None = None,
    ) -> ResolutionResult:
        domains, organizations = self._allowed_boundaries(target)
        candidate_url = target.item.canonical_url
        last_reason = "no_primary_evidence"

        if (
            candidate_url
            and is_official_url(candidate_url, domains, organizations)
            and not is_search_url(candidate_url)
        ):
            return self._validate(
                candidate_url,
                excerpt=target.excerpt,
                expected_date=target.item.published_at,
                expected_hash=None,
                require_expected_hash=False,
                publisher=target.publisher,
                title=target.item.title_original,
                timeout=timeout,
                domains=domains,
                organizations=organizations,
                source="candidate_official_url",
            )

        if candidate_url and is_safe_candidate_url(candidate_url):
            result = self._resolve_page_link(
                target,
                candidate_url,
                timeout=timeout,
                domains=domains,
                organizations=organizations,
            )
            if result.evidence is not None:
                return result
            if result.reason in {
                "candidate_redirect_anomaly",
                "candidate_redirect_unsafe",
            }:
                return result
            if result.reason:
                last_reason = result.reason

        if codex_suggestion is not None:
            return self.resolve_suggestion(
                target,
                codex_suggestion,
                timeout=timeout,
            )
        return ResolutionResult(None, last_reason)

    def resolve_suggestion(
        self,
        target: VerificationTarget,
        suggestion: EvidenceSuggestion,
        *,
        timeout: float,
    ) -> ResolutionResult:
        domains, organizations = self._allowed_boundaries(target)
        if not is_official_url(
            suggestion.url,
            domains,
            organizations,
        ):
            return ResolutionResult(None, "evidence_not_official")
        return self._validate(
            suggestion.url,
            excerpt=suggestion.excerpt,
            expected_date=suggestion.published_at or target.item.published_at,
            expected_hash=suggestion.content_hash,
            require_expected_hash=True,
            publisher=suggestion.publisher,
            title=suggestion.title,
            timeout=timeout,
            domains=domains,
            organizations=organizations,
            source="codex_suggestion",
        )

    def _resolve_page_link(
        self,
        target: VerificationTarget,
        candidate_url: str,
        *,
        timeout: float,
        domains: tuple[str, ...],
        organizations: tuple[str, ...],
    ) -> ResolutionResult:
        try:
            response = self._http.get(candidate_url, timeout=timeout)
        except Exception:
            return ResolutionResult(None, "candidate_page_unreachable")
        final_url = response.final_url or candidate_url
        if not is_safe_candidate_url(final_url):
            return ResolutionResult(None, "candidate_redirect_unsafe")
        if host(candidate_url) != host(final_url):
            return ResolutionResult(None, "candidate_redirect_anomaly")
        for link in _links(response.text(), final_url):
            if not is_official_url(link, domains, organizations):
                continue
            if is_search_url(link):
                continue
            return self._validate(
                link,
                excerpt=target.excerpt,
                expected_date=target.item.published_at,
                expected_hash=None,
                require_expected_hash=False,
                publisher=target.publisher,
                title=target.item.title_original,
                timeout=timeout,
                domains=domains,
                organizations=organizations,
                source="page_first_party_link",
            )
        return ResolutionResult(None, "page_first_party_link_missing")

    def _allowed_boundaries(
        self,
        target: VerificationTarget,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
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
        return domains, organizations

    def _validate(
        self,
        url: str,
        *,
        excerpt: str | None,
        expected_date: datetime | None,
        expected_hash: str | None,
        require_expected_hash: bool,
        publisher: str,
        title: str,
        timeout: float,
        domains: tuple[str, ...],
        organizations: tuple[str, ...],
        source: str,
    ) -> ResolutionResult:
        if not excerpt:
            return ResolutionResult(None, "evidence_excerpt_missing")
        if expected_date is None:
            return ResolutionResult(None, "evidence_date_missing")
        if require_expected_hash and expected_hash is None:
            return ResolutionResult(None, "evidence_content_hash_missing")
        if not is_official_url(url, domains, organizations):
            return ResolutionResult(None, "evidence_not_official")
        if is_search_url(url):
            return ResolutionResult(None, "search_summary_not_evidence")
        try:
            response = self._http.get(url, timeout=timeout)
        except Exception:
            return ResolutionResult(None, "evidence_unreachable")
        final_url = response.final_url or url
        if not is_official_url(final_url, domains, organizations):
            return ResolutionResult(None, "redirect_not_official")
        if is_search_url(final_url):
            return ResolutionResult(None, "search_summary_not_evidence")
        if host(url) != host(final_url):
            return ResolutionResult(None, "redirect_anomaly")
        body = response.text()
        if normalize_excerpt(excerpt) not in normalize_excerpt(
            visible_text(body)
        ):
            return ResolutionResult(None, "evidence_excerpt_mismatch")
        if not date_matches(expected_date, body):
            return ResolutionResult(None, "evidence_date_mismatch")
        digest = content_hash(body)
        if expected_hash is not None and expected_hash != digest:
            return ResolutionResult(
                None,
                "evidence_content_hash_mismatch",
            )
        evidence = Evidence.model_validate(
            {
                "url": normalize_url(final_url),
                "publisher": publisher,
                "title": title,
                "published_at": expected_date,
                "retrieved_at": self._clock.now(),
                "excerpt": excerpt,
                "content_hash": digest,
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
        return ResolutionResult(evidence, "", source)
