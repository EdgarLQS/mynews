"""稳定领域模型与向后兼容的 RunReport 1.2 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from mynews.verification.protocol import VerificationTarget

ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max"]


class ContractModel(BaseModel):
    """允许消费者忽略 1.x minor 版本新增字段。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CollectionRequest(ContractModel):
    """一次采集请求的精确时间范围和运行约束。"""

    from_: datetime = Field(alias="from")
    to: datetime
    timezone: str = "Asia/Shanghai"
    source_ids: list[str] = Field(default_factory=list)
    verification_budget: int | None = Field(default=None, ge=0)
    verification_reasoning_effort: ReasoningEffort | None = None

    @field_validator("from_", "to")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"未知时区：{value}") from error
        return value

    @model_validator(mode="after")
    def require_forward_range(self) -> CollectionRequest:
        if self.from_ >= self.to:
            raise ValueError("开始时间必须早于结束时间")
        return self


class Candidate(ContractModel):
    """来源 Adapter 产生的未经规范化候选。"""

    source_id: str = Field(min_length=1)
    title_original: str = Field(min_length=1)
    url: AnyHttpUrl
    published_at: datetime | None = None
    excerpt: str | None = None
    heat_signals: dict[str, float] = Field(default_factory=dict)
    content: str | None = None
    language: str | None = None
    language_original: str | None = None
    entities: list[str] = Field(default_factory=list)
    event_type: str | None = None
    source_role: str | None = None
    title_zh: str | None = None
    summary_zh: str | None = None
    heat_score: int | None = Field(default=None, ge=0, le=100)
    relevance_score: int | None = Field(default=None, ge=0, le=100)

    @field_validator("published_at")
    @classmethod
    def validate_published_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("发布时间必须包含时区")
        return value


class EvidenceValidation(ContractModel):
    """程序对第一方证据执行的可复查校验结果。"""

    reachable: bool = False
    official_domain: bool = False
    redirect_safe: bool = False
    excerpt_matched: bool = False
    date_matched: bool = False
    content_hash_matched: bool = False
    lifecycle_status: Literal[
        "current",
        "changed_supporting",
        "failed",
    ] = "current"


class Evidence(ContractModel):
    """支持新闻事实的第一方证据。"""

    url: AnyHttpUrl
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    published_at: datetime | None = None
    retrieved_at: datetime
    excerpt: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    previous_content_hash: str | None = None
    reviewed_at: datetime | None = None
    validation: EvidenceValidation = Field(default_factory=EvidenceValidation)

    @field_validator("published_at", "retrieved_at", "reviewed_at")
    @classmethod
    def validate_evidence_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("证据时间必须包含时区")
        return value


class VerificationRetry(ContractModel):
    """RunReport 中仅展示已经持久化的待核验事实。"""

    status: Literal["pending", "expired"]
    attempt_count: int = Field(ge=1)
    last_reason: str = Field(min_length=1)
    terminal_reason: str | None = None
    next_retry_at: datetime | None = None
    max_attempts: int = Field(ge=1)
    expires_at: datetime

    @field_validator("next_retry_at", "expires_at")
    @classmethod
    def validate_retry_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("重试时间必须包含时区")
        return value


class NewsItem(ContractModel):
    """规范化后的新闻事件及其真实性状态。"""

    id: str = Field(min_length=1)
    event_key: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    title_original: str = Field(min_length=1)
    language_original: str = Field(min_length=1)
    title_zh: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)
    published_at: datetime | None = None
    first_seen_at: datetime
    heat_score: int = Field(ge=0, le=100)
    relevance_score: int = Field(ge=0, le=100)
    discovery_sources: list[str] = Field(default_factory=list)
    verification_status: Literal["verified", "unverified"] = "unverified"
    verification_reason: str = Field(min_length=1)
    primary_evidence: list[Evidence] = Field(default_factory=list)
    verification_retry: VerificationRetry | None = None
    content_hash: str = Field(min_length=1)
    canonical_url: str | None = None
    entities: list[str] = Field(default_factory=list)
    source_roles: list[str] = Field(default_factory=list)

    @field_validator("published_at", "first_seen_at")
    @classmethod
    def validate_news_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("新闻时间必须包含时区")
        return value

    @model_validator(mode="after")
    def verify_evidence_requirement(self) -> NewsItem:
        if self.verification_status != "verified":
            return self
        if not self.primary_evidence:
            raise ValueError("verified 条目必须包含 primary_evidence")
        if not any(
            evidence.validation.reachable
            and evidence.validation.official_domain
            and evidence.validation.excerpt_matched
            for evidence in self.primary_evidence
        ):
            raise ValueError(
                "verified 条目的 primary_evidence 必须通过 validation"
            )
        return self


class PendingVerificationEntry(ContractModel):
    """独立于 DedupState 的待核验持久化条目。"""

    event_key: str = Field(min_length=1)
    item: NewsItem
    source_id: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    excerpt: str | None = None
    official_domains: list[str] = Field(default_factory=list)
    official_github_organizations: list[str] = Field(default_factory=list)
    source_role: str = "discovery"
    attempt_count: int = Field(ge=1)
    last_reason: str = Field(min_length=1)
    terminal_reason: str | None = None
    next_retry_at: datetime | None = None
    max_attempts: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    status: Literal["pending", "expired"] = "pending"

    @field_validator(
        "next_retry_at",
        "created_at",
        "updated_at",
        "expires_at",
    )
    @classmethod
    def validate_pending_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("pending 时间必须包含时区")
        return value

    @model_validator(mode="after")
    def require_matching_event_key(self) -> PendingVerificationEntry:
        if self.event_key != self.item.event_key:
            raise ValueError("pending event_key 必须匹配 item")
        return self

    @property
    def target(self) -> VerificationTarget:
        from mynews.verification.protocol import VerificationTarget

        return VerificationTarget(
            item=self.item,
            source_id=self.source_id,
            publisher=self.publisher,
            excerpt=self.excerpt,
            official_domains=tuple(self.official_domains),
            official_github_organizations=tuple(
                self.official_github_organizations
            ),
            source_role=self.source_role,
        )

    def retry_view(self) -> VerificationRetry:
        return VerificationRetry(
            status=self.status,
            attempt_count=self.attempt_count,
            last_reason=self.last_reason,
            terminal_reason=self.terminal_reason,
            next_retry_at=self.next_retry_at,
            max_attempts=self.max_attempts,
            expires_at=self.expires_at,
        )


class PendingVerificationState(ContractModel):
    schema_version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+$")
    entries: dict[str, PendingVerificationEntry] = Field(default_factory=dict)


class PriceSnapshot(ContractModel):
    """官方价格页的规范化快照和可选的页面发布日期。"""

    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    observed_at: datetime
    first_observed_at: datetime | None = None
    published_at: datetime | None = None
    content_hash: str = Field(min_length=1)
    values: dict[str, object] = Field(default_factory=dict)

    @field_validator("observed_at", "first_observed_at", "published_at")
    @classmethod
    def validate_snapshot_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("价格快照时间必须包含时区")
        return value

    @model_validator(mode="after")
    def require_first_observation_before_current(self) -> PriceSnapshot:
        if (
            self.first_observed_at is not None
            and self.first_observed_at > self.observed_at
        ):
            raise ValueError("first_observed_at 不能晚于 observed_at")
        return self


class SourceSnapshot(ContractModel):
    """没有可确认日期的来源目录页快照。"""

    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    observed_at: datetime
    content_hash: str = Field(min_length=1)
    values: dict[str, object] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def validate_source_snapshot_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("来源快照时间必须包含时区")
        return value


class SourceError(ContractModel):
    """来源失败的稳定机器可读错误。"""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class SourceResult(ContractModel):
    """一个来源在本次运行中的健康和计数结果。"""

    source_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    stability: str = Field(default="stable", min_length=1)
    health: Literal["healthy", "degraded", "blocked", "failed"]
    fetched_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    error: SourceError | None = None

    @model_validator(mode="after")
    def require_error_for_unhealthy_source(self) -> SourceResult:
        if self.health != "healthy" and self.error is None:
            raise ValueError("非 healthy 来源必须提供 error")
        return self


class VerificationStats(ContractModel):
    attempted: int = Field(default=0, ge=0)
    retried: int = Field(default=0, ge=0)
    pending: int = Field(default=0, ge=0)
    expired: int = Field(default=0, ge=0)
    revalidated: int = Field(default=0, ge=0)
    changed_supporting: int = Field(default=0, ge=0)
    revalidation_failed: int = Field(default=0, ge=0)


class EvidenceReview(ContractModel):
    event_key: str = Field(min_length=1)
    evidence_url: str = Field(min_length=1)
    status: Literal["current", "changed_supporting", "failed"]
    reason: str = ""
    warning: str | None = None


class DigestEvidenceRef(ContractModel):
    """Digest 只能引用 RunReport 已保存的第一方证据。"""

    url: AnyHttpUrl
    excerpt: str = Field(min_length=1)
    published_at: datetime | None = None
    content_hash: str = Field(min_length=1)

    @field_validator("published_at")
    @classmethod
    def validate_digest_evidence_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Digest 证据时间必须包含时区")
        return value


class DigestItem(ContractModel):
    """简报中的一个聚合事件，主榜与线索观察共享此结构。"""

    event_key: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    title_zh: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)
    impact_zh: str = Field(min_length=1)
    lifecycle: Literal["new", "updated", "ongoing"]
    verification_status: Literal["verified", "unverified"]
    verification_reason: str = Field(min_length=1)
    verification_retry: VerificationRetry | None = None
    evidence_refs: list[DigestEvidenceRef] = Field(default_factory=list)
    source_item_keys: list[str] = Field(default_factory=list)
    source_content_hash: str = Field(min_length=1)
    source_title_original: str = Field(min_length=1)
    canonical_url: str | None = None
    published_at: datetime | None = None
    relevance_score: int = Field(ge=0, le=100)
    heat_score: int = Field(ge=0, le=100)
    freshness_score: int = Field(ge=0, le=100)
    event_type_score: int = Field(ge=0, le=100)
    rank_score: float = Field(ge=0, le=100)
    summary_status: Literal["codex", "fallback", "not_requested"]
    summary_reason: str | None = None

    @field_validator("published_at")
    @classmethod
    def validate_digest_item_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Digest 条目时间必须包含时区")
        return value


class Digest(ContractModel):
    """独立 Digest Schema 1.0。"""

    schema_version: Literal["1.0"] = "1.0"
    digest_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    generated_at: datetime
    status: Literal["complete", "partial"]
    main_items: list[DigestItem] = Field(default_factory=list)
    lead_items: list[DigestItem] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    summary_errors: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def validate_digest_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Digest 生成时间必须包含时区")
        return value

    @model_validator(mode="after")
    def enforce_fact_lead_isolation(self) -> Digest:
        if any(item.verification_status != "verified" for item in self.main_items):
            raise ValueError("Digest 主榜只能包含 verified 条目")
        if any(item.verification_status != "unverified" for item in self.lead_items):
            raise ValueError("Digest 线索观察只能包含 unverified 条目")
        keys = [item.event_key for item in (*self.main_items, *self.lead_items)]
        if len(keys) != len(set(keys)):
            raise ValueError("Digest 不得重复输出同一事件")
        return self

    @property
    def all_items(self) -> tuple[DigestItem, ...]:
        return (*self.main_items, *self.lead_items)


class RunReport(ContractModel):
    """一次运行的完整可序列化报告。"""

    schema_version: str = Field(default="1.2", pattern=r"^[0-9]+\.[0-9]+$")
    run_id: str = Field(min_length=1)
    status: Literal["complete", "partial", "failed"]
    requested_range: CollectionRequest
    started_at: datetime
    finished_at: datetime
    sources: list[SourceResult] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    reason_counts: dict[str, int] = Field(default_factory=dict)
    verification_stats: VerificationStats = Field(
        default_factory=VerificationStats
    )
    evidence_reviews: list[EvidenceReview] = Field(default_factory=list)
    items: list[NewsItem] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def require_supported_major(cls, value: str) -> str:
        if value.split(".", 1)[0] != "1":
            raise ValueError(f"不支持的 schema major 版本：{value}")
        return value

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_run_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("运行时间必须包含时区")
        return value

    @model_validator(mode="after")
    def require_valid_run(self) -> RunReport:
        if self.started_at > self.finished_at:
            raise ValueError("运行开始时间不能晚于结束时间")
        if self.requested_range.verification_budget is None:
            raise ValueError("RunReport 必须记录实际核验预算")
        if self.schema_version == "1.2":
            for item in self.items:
                self._require_strict_verified_item(item)
        return self

    @staticmethod
    def _require_strict_verified_item(item: NewsItem) -> None:
        if item.verification_status != "verified":
            return
        valid = any(
            _strict_evidence_valid(evidence)
            for evidence in item.primary_evidence
        )
        if not valid:
            raise ValueError(
                "RunReport 1.2 的 verified 条目必须通过完整证据校验"
            )


def _strict_evidence_valid(evidence: Evidence) -> bool:
    validation = evidence.validation
    if evidence.published_at is None:
        return False
    support_valid = (
        validation.reachable
        and validation.official_domain
        and validation.redirect_safe
        and validation.excerpt_matched
        and validation.date_matched
    )
    if not support_valid:
        return False
    if validation.lifecycle_status == "changed_supporting":
        return evidence.previous_content_hash is not None
    return (
        validation.lifecycle_status == "current"
        and validation.content_hash_matched
    )
