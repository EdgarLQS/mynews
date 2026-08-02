"""第一方证据核验 Adapter。"""

from mynews.verification.codex import CodexVerifier
from mynews.verification.fake import FakeVerifier
from mynews.verification.protocol import (
    EvidenceVerifier,
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)

__all__ = [
    "CodexVerifier",
    "EvidenceVerifier",
    "FakeVerifier",
    "VerificationConfig",
    "VerificationDecision",
    "VerificationTarget",
]
