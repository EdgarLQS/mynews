"""待核验条目的纯内存重试状态机。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from mynews.domain.models import (
    PendingVerificationEntry,
    PendingVerificationState,
)
from mynews.verification.protocol import VerificationTarget

RETRIABLE_REASONS = frozenset(
    {
        "candidate_page_unreachable",
        "codex_failed",
        "codex_no_suggestion",
        "codex_timeout",
        "codex_unavailable",
        "evidence_unreachable",
        "verification_budget_exhausted",
        "verifier_failed",
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: timedelta = timedelta()
    maximum_delay: timedelta = timedelta(hours=12)
    ttl: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts 必须是正整数")
        if self.base_delay < timedelta():
            raise ValueError("base_delay 不能为负数")
        if self.maximum_delay < timedelta():
            raise ValueError("maximum_delay 不能为负数")
        if self.ttl <= timedelta():
            raise ValueError("ttl 必须大于零")


class PendingVerificationManager:
    """只修改传入状态副本，由最终 Store 事务统一持久化。"""

    def __init__(
        self,
        state: PendingVerificationState,
        policy: RetryPolicy | None = None,
    ) -> None:
        self._state = state.model_copy(deep=True)
        self._policy = policy or RetryPolicy()

    @property
    def state(self) -> PendingVerificationState:
        return self._state

    def entries(self) -> tuple[PendingVerificationEntry, ...]:
        return tuple(
            self._state.entries[key]
            for key in sorted(self._state.entries)
        )

    def due(self, now: datetime) -> tuple[VerificationTarget, ...]:
        targets: list[VerificationTarget] = []
        for event_key in sorted(self._state.entries):
            entry = self._state.entries[event_key]
            if entry.status == "pending" and now >= entry.expires_at:
                self._state.entries[event_key] = entry.model_copy(
                    update={
                        "status": "expired",
                        "terminal_reason": "verification_ttl_expired",
                        "next_retry_at": None,
                        "updated_at": now,
                    }
                )
                continue
            if (
                entry.status == "pending"
                and entry.next_retry_at is not None
                and now >= entry.next_retry_at
            ):
                targets.append(entry.target)
        return tuple(targets)

    def record_failure(
        self,
        target: VerificationTarget,
        reason: str,
        *,
        now: datetime,
    ) -> PendingVerificationEntry | None:
        if reason not in RETRIABLE_REASONS:
            self.resolve(target.item.event_key)
            return None
        existing = self._state.entries.get(target.item.event_key)
        attempt_count = (existing.attempt_count if existing else 0) + 1
        created_at = existing.created_at if existing else now
        expires_at = existing.expires_at if existing else now + self._policy.ttl
        status = "pending"
        terminal_reason: str | None = None
        next_retry_at: datetime | None = now + self._delay(attempt_count)
        if attempt_count >= self._policy.max_attempts:
            status = "expired"
            terminal_reason = "verification_attempt_limit_reached"
            next_retry_at = None
        elif now >= expires_at:
            status = "expired"
            terminal_reason = "verification_ttl_expired"
            next_retry_at = None
        entry = PendingVerificationEntry(
            event_key=target.item.event_key,
            target=target,
            status=status,
            attempt_count=attempt_count,
            last_reason=reason,
            terminal_reason=terminal_reason,
            next_retry_at=next_retry_at,
            max_attempts=self._policy.max_attempts,
            created_at=created_at,
            updated_at=now,
            expires_at=expires_at,
        )
        self._state.entries[target.item.event_key] = entry
        return entry

    def resolve(self, event_key: str) -> None:
        self._state.entries.pop(event_key, None)

    def target(self, event_key: str) -> VerificationTarget | None:
        entry = self._state.entries.get(event_key)
        return entry.target if entry is not None else None

    def _delay(self, attempt_count: int) -> timedelta:
        seconds = self._policy.base_delay.total_seconds() * (
            2 ** max(0, attempt_count - 1)
        )
        return min(
            timedelta(seconds=seconds),
            self._policy.maximum_delay,
        )
