"""离线测试使用的确定性 EvidenceVerifier。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mynews.verification.protocol import (
    EvidenceVerifier,
    VerificationBatch,
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)


class FakeVerifier:
    """只返回测试预先配置的判定，未配置项安全保持 unverified。"""

    def __init__(
        self,
        decisions: Mapping[str, VerificationDecision] | None = None,
    ) -> None:
        self._decisions = dict(decisions or {})

    def verify(
        self,
        candidates: Sequence[VerificationTarget],
        *,
        config: VerificationConfig,
    ) -> VerificationBatch:
        del config
        return tuple(
            self._decisions.get(
                candidate.item.event_key,
                VerificationDecision.unverified(
                    candidate.item.event_key, "fake_not_configured"
                ),
            )
            for candidate in candidates
        )


def is_evidence_verifier(value: object) -> bool:
    """为外部调用者提供不依赖具体 Adapter 的运行时检查。"""

    return isinstance(value, EvidenceVerifier)
