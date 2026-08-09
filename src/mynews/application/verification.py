"""把新候选和跨运行 pending 条目合并为一次核验。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from mynews.domain.models import PendingVerificationEntry, VerificationStats
from mynews.verification.pending import PendingVerificationManager
from mynews.verification.protocol import (
    EvidenceVerifier,
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)


@dataclass(frozen=True, slots=True)
class CoordinatedVerification:
    targets: tuple[VerificationTarget, ...]
    decisions: tuple[VerificationDecision, ...]
    pending: tuple[PendingVerificationEntry, ...]
    stats: VerificationStats


class VerificationCoordinator:
    def __init__(
        self,
        verifier: EvidenceVerifier,
        pending: PendingVerificationManager,
    ) -> None:
        self._verifier = verifier
        self._pending = pending

    def verify(
        self,
        new_targets: Sequence[VerificationTarget],
        *,
        now: datetime,
        config: VerificationConfig,
    ) -> CoordinatedVerification:
        due_targets = self._pending.due(now)
        merged = {
            target.item.event_key: target for target in due_targets
        }
        for target in new_targets:
            merged[target.item.event_key] = target
        targets = tuple(merged.values())
        if not targets:
            return self._result((), (), due_targets)

        decisions = self._verify(targets, config)
        for target, decision in zip(targets, decisions, strict=True):
            if decision.status == "verified":
                self._pending.resolve(target.item.event_key)
            else:
                self._pending.record_failure(
                    target,
                    decision.reason,
                    now=now,
                )
        return self._result(targets, decisions, due_targets)

    def _verify(
        self,
        targets: tuple[VerificationTarget, ...],
        config: VerificationConfig,
    ) -> tuple[VerificationDecision, ...]:
        try:
            decisions = tuple(self._verifier.verify(targets, config=config))
        except Exception:
            decisions = ()
        if len(decisions) == len(targets):
            return decisions
        return tuple(
            VerificationDecision.unverified(
                target.item.event_key,
                "verifier_failed",
            )
            for target in targets
        )

    def _result(
        self,
        targets: tuple[VerificationTarget, ...],
        decisions: tuple[VerificationDecision, ...],
        due_targets: Sequence[VerificationTarget],
    ) -> CoordinatedVerification:
        pending = self._pending.entries()
        due_keys = {
            target.item.event_key for target in due_targets
        }
        stats = VerificationStats(
            attempted=len(targets),
            retried=sum(
                target.item.event_key in due_keys for target in targets
            ),
            pending=sum(entry.status == "pending" for entry in pending),
            expired=sum(entry.status == "expired" for entry in pending),
        )
        return CoordinatedVerification(
            targets,
            decisions,
            pending,
            stats,
        )
