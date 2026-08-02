"""阶段 2 来源插件的稳定内部 seam。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, field_validator, model_validator

from mynews.domain.models import (
    Candidate,
    CollectionRequest,
    ContractModel,
    SourceError,
)
from mynews.infrastructure.clock import Clock, SystemClock
from mynews.infrastructure.http import HttpClient


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """来源的稳定身份和第一方入口描述。"""

    source_id: str
    name: str
    role: str
    homepage: str
    official_domains: tuple[str, ...]
    official_github_organizations: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    region: str = "global"
    stability: str = "stable-planned"
    publication_time_semantics: str = "source-provided"
    plugin_api_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("来源 ID 不能为空")
        if not self.official_domains:
            raise ValueError("来源必须声明官方域名")


class SourcePluginError(RuntimeError):
    """Adapter 可预期的结构化失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SourceContext:
    request: CollectionRequest
    http: HttpClient
    limit: int = 30
    clock: Clock = field(default_factory=SystemClock)

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("来源 limit 必须是正整数")


@dataclass(frozen=True, slots=True)
class ProbeContext:
    http: HttpClient
    limit: int = 5
    clock: Clock = field(default_factory=SystemClock)

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("probe limit 必须是正整数")


@dataclass(frozen=True, slots=True)
class SourceBatch:
    source_id: str
    candidates: tuple[Candidate, ...]
    fetched_count: int | None = None

    def __post_init__(self) -> None:
        if self.fetched_count is not None and self.fetched_count < len(self.candidates):
            raise ValueError("fetched_count 不能小于候选数")


class SourceHealth(ContractModel):
    """来源采集或 probe 的结构化健康快照。"""

    source_id: str
    role: str
    health: Literal["healthy", "degraded", "blocked", "failed"]
    fetched_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    checked_at: datetime
    error: SourceError | None = None

    @field_validator("checked_at")
    @classmethod
    def require_aware_checked_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("健康检查时间必须包含时区")
        return value

    @model_validator(mode="after")
    def require_error_for_unhealthy(self) -> SourceHealth:
        if self.health != "healthy" and self.error is None:
            raise ValueError("非 healthy 来源必须提供 error")
        return self

    @classmethod
    def healthy_result(
        cls,
        *,
        source_id: str,
        role: str,
        fetched_count: int,
        accepted_count: int,
        checked_at: datetime,
        duration_ms: int = 0,
    ) -> SourceHealth:
        return cls(
            source_id=source_id,
            role=role,
            health="healthy",
            fetched_count=fetched_count,
            accepted_count=accepted_count,
            duration_ms=duration_ms,
            checked_at=checked_at,
        )


@runtime_checkable
class SourcePlugin(Protocol):
    metadata: SourceMetadata

    def collect(self, context: SourceContext) -> SourceBatch: ...

    def probe(self, context: ProbeContext) -> SourceHealth: ...


@dataclass(frozen=True, slots=True)
class SourceCollection:
    candidates: tuple[Candidate, ...]
    health: tuple[SourceHealth, ...]


def ensure_unique_source_ids(
    plugins: Iterable[SourcePlugin],
) -> tuple[SourcePlugin, ...]:
    selected: list[SourcePlugin] = []
    seen: set[str] = set()
    for plugin in plugins:
        source_id = plugin.metadata.source_id
        if source_id in seen:
            raise ValueError(f"重复来源 ID：{source_id}")
        seen.add(source_id)
        selected.append(plugin)
    return tuple(selected)
