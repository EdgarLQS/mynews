"""NewsStore 的可替换公共 seam。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mynews.domain.deduplication import DedupState
from mynews.domain.models import (
    PendingVerificationState,
    PriceSnapshot,
    RunReport,
    SourceSnapshot,
)


@dataclass(frozen=True, slots=True)
class StoredRun:
    run_path: Path
    latest_updated: bool


class NewsStore(Protocol):
    def commit(
        self,
        report: RunReport,
        *,
        dedup_state: DedupState | None = None,
        pending_state: PendingVerificationState | None = None,
    ) -> StoredRun: ...

    def load_dedup_state(self) -> DedupState: ...

    def load_pending_verifications(self) -> PendingVerificationState: ...

    def load_price_snapshot(self, source_id: str) -> PriceSnapshot | None: ...

    def save_dedup_state(self, state: DedupState) -> Path: ...

    def save_pending_verifications(
        self,
        state: PendingVerificationState,
    ) -> Path: ...

    def save_price_snapshot(self, snapshot: PriceSnapshot) -> PriceSnapshot: ...

    def load_source_snapshot(self, source_id: str) -> SourceSnapshot | None: ...

    def save_source_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot: ...
