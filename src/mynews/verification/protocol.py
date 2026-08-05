"""证据核验的领域无关 Adapter seam 和运行配置。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from mynews.domain.models import Evidence, NewsItem

DEFAULT_CODEX_MODEL = "gpt-5.6-luna"
DEFAULT_VERIFICATION_BUDGET = 30
DEFAULT_VERIFICATION_BATCH_SIZE = 5
DEFAULT_VERIFICATION_TIMEOUT = 30.0
DEFAULT_PRIMARY_DOMAINS = (
    "openai.com",
    "developers.openai.com",
    "anthropic.com",
    "www.anthropic.com",
    "ai.google.dev",
    "github.blog",
    "cursor.com",
    "docs.devin.ai",
    "developer.nvidia.com",
    "huggingface.co",
    "qwenlm.github.io",
    "api-docs.deepseek.com",
    "kimi.com",
    "bigmodel.cn",
    "lingma.aliyun.com",
    "trae.cn",
    "www.trae.cn",
    "codebuddy.cn",
    "cloud.baidu.com",
    "minimaxi.com",
    "volcengine.com",
    "ccswitch.io",
)
DEFAULT_GITHUB_ORGANIZATIONS = (
    "anthropics",
    "farion1231",
    "github",
    "google",
    "openai",
    "QwenLM",
)


@dataclass(frozen=True, slots=True)
class VerificationConfig:
    """核验 Adapter 的可注入运行策略，不属于 JSON 领域模型。"""

    model: str = DEFAULT_CODEX_MODEL
    budget: int = DEFAULT_VERIFICATION_BUDGET
    batch_size: int = DEFAULT_VERIFICATION_BATCH_SIZE
    timeout: float = DEFAULT_VERIFICATION_TIMEOUT
    codex_executable: str = "codex"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("核验模型不能为空")
        if self.budget < 0:
            raise ValueError("核验预算不能为负数")
        if self.batch_size <= 0:
            raise ValueError("核验批大小必须是正整数")
        if self.timeout <= 0:
            raise ValueError("核验超时必须是正数")
        if not self.codex_executable.strip():
            raise ValueError("Codex 可执行文件不能为空")


@dataclass(frozen=True, slots=True)
class VerificationTarget:
    """把规范化条目与来源核验边界传给 Adapter。"""

    item: NewsItem
    source_id: str
    publisher: str
    excerpt: str | None
    official_domains: tuple[str, ...]
    official_github_organizations: tuple[str, ...] = ()
    source_role: str = "discovery"


@dataclass(frozen=True, slots=True)
class VerificationDecision:
    """一个条目的最终程序判定；Codex 不能直接构造 verified。"""

    item_id: str
    status: Literal["verified", "unverified"]
    reason: str
    evidence: Evidence | None = None

    def __post_init__(self) -> None:
        if not self.item_id.strip() or not self.reason.strip():
            raise ValueError("核验判定必须包含条目 ID 和原因")
        if self.status == "verified":
            if self.evidence is None:
                raise ValueError("verified 判定必须包含证据")
            if not (
                self.evidence.validation.reachable
                and self.evidence.validation.official_domain
                and self.evidence.validation.excerpt_matched
            ):
                raise ValueError("verified 判定的证据必须通过基础校验")
        elif self.evidence is not None:
            raise ValueError("unverified 判定不能携带证据")

    @classmethod
    def unverified(cls, item_id: str, reason: str) -> VerificationDecision:
        return cls(item_id=item_id, status="unverified", reason=reason)

    @classmethod
    def verified(
        cls,
        item_id: str,
        evidence: Evidence,
        reason: str = "verified_primary_evidence",
    ) -> VerificationDecision:
        return cls(
            item_id=item_id,
            status="verified",
            reason=reason,
            evidence=evidence,
        )


VerificationBatch = tuple[VerificationDecision, ...]


@runtime_checkable
class EvidenceVerifier(Protocol):
    """Collector 使用的可替换第一方证据核验 seam。"""

    def verify(
        self,
        candidates: Sequence[VerificationTarget],
        *,
        config: VerificationConfig,
    ) -> VerificationBatch: ...
