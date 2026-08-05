"""使用同目录临时文件和 os.replace 的事务化 JSON NewsStore。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from mynews.domain.deduplication import DedupState
from mynews.domain.models import (
    PendingVerificationState,
    PriceSnapshot,
    RunReport,
    SourceSnapshot,
)
from mynews.domain.normalization import normalize_url
from mynews.storage.protocol import StoredRun


class JsonStoreError(RuntimeError):
    """JSON Store 无法安全提交或恢复状态。"""


class JsonNewsStore:
    """保存 output/、state/，并对一次运行的相关文件提供回滚。"""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._output = self._root / "output"
        self._runs = self._output / "runs"
        self._state = self._root / "state"
        self._prices = self._state / "price_snapshots"
        self._snapshots = self._state / "source_snapshots"
        self._pending = self._state / "pending_verifications.json"

    @property
    def root(self) -> Path:
        return self._root

    def commit(
        self,
        report: RunReport,
        *,
        dedup_state: DedupState | None = None,
        pending_state: PendingVerificationState | None = None,
    ) -> StoredRun:
        validated = RunReport.model_validate(report)
        payload = validated.model_dump(mode="json", by_alias=True)
        run_path = self._runs / f"{_safe_filename(validated.run_id)}.json"
        if run_path.exists():
            raise JsonStoreError(f"运行文件已存在：{run_path.name}")
        writes: list[tuple[Path, object]] = [(run_path, payload)]
        if dedup_state is not None:
            validated_dedup = DedupState.model_validate(dedup_state)
            writes.append(
                (
                    self._state / "dedup.json",
                    validated_dedup.model_dump(mode="json"),
                )
            )
        if pending_state is not None:
            validated_pending = PendingVerificationState.model_validate(
                pending_state
            )
            writes.append(
                (
                    self._pending,
                    validated_pending.model_dump(mode="json"),
                )
            )
        latest_updated = validated.status in {"complete", "partial"}
        if latest_updated:
            writes.append((self._output / "latest.json", payload))
        _transactional_write_json(writes)
        return StoredRun(run_path=run_path, latest_updated=latest_updated)

    def load_dedup_state(self) -> DedupState:
        path = self._state / "dedup.json"
        if not path.exists():
            return DedupState()
        try:
            return DedupState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise JsonStoreError(f"无法恢复去重状态：{path}") from error

    def load_pending_verifications(self) -> PendingVerificationState:
        if not self._pending.exists():
            return PendingVerificationState()
        try:
            return PendingVerificationState.model_validate_json(
                self._pending.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise JsonStoreError(
                f"无法恢复待核验状态：{self._pending}"
            ) from error

    def save_dedup_state(self, state: DedupState) -> Path:
        validated = DedupState.model_validate(state)
        path = self._state / "dedup.json"
        _atomic_write_json(path, validated.model_dump(mode="json"))
        return path

    def save_pending_verifications(
        self,
        state: PendingVerificationState,
    ) -> Path:
        validated = PendingVerificationState.model_validate(state)
        _atomic_write_json(
            self._pending,
            validated.model_dump(mode="json"),
        )
        return self._pending

    def save_price_snapshot(self, snapshot: PriceSnapshot) -> PriceSnapshot:
        path = self._prices / f"{_safe_filename(snapshot.source_id)}.json"
        canonical_url = normalize_url(snapshot.url)
        normalized = snapshot.model_copy(update={"url": canonical_url})
        first_observed_at = normalized.first_observed_at or normalized.observed_at
        previous = self._load_price_snapshot(path)
        if previous is not None and previous.url == canonical_url:
            first_observed_at = min(
                first_observed_at,
                previous.first_observed_at or previous.observed_at,
            )
        stored = normalized.model_copy(update={"first_observed_at": first_observed_at})
        _atomic_write_json(path, stored.model_dump(mode="json"))
        return stored

    def load_price_snapshot(self, source_id: str) -> PriceSnapshot | None:
        return self._load_price_snapshot(
            self._prices / f"{_safe_filename(source_id)}.json"
        )

    def save_source_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        path = self._snapshots / f"{_safe_filename(snapshot.source_id)}.json"
        stored = snapshot.model_copy(update={"url": normalize_url(snapshot.url)})
        _atomic_write_json(path, stored.model_dump(mode="json"))
        return stored

    def load_source_snapshot(self, source_id: str) -> SourceSnapshot | None:
        path = self._snapshots / f"{_safe_filename(source_id)}.json"
        if not path.exists():
            return None
        try:
            return SourceSnapshot.model_validate(self._read_json(path))
        except (OSError, ValueError) as error:
            raise JsonStoreError(f"无法恢复来源快照：{path.name}") from error

    @staticmethod
    def _read_json(path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_price_snapshot(self, path: Path) -> PriceSnapshot | None:
        if not path.exists():
            return None
        try:
            return PriceSnapshot.model_validate(self._read_json(path))
        except (OSError, ValueError) as error:
            raise JsonStoreError(f"无法恢复价格快照：{path.name}") from error


def _safe_filename(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(":", "-")


def _transactional_write_json(writes: list[tuple[Path, object]]) -> None:
    previous = {
        path: path.read_bytes() if path.exists() else None
        for path, _ in writes
    }
    staged: dict[Path, str] = {}
    try:
        for path, payload in writes:
            staged[path] = _stage_json(path, payload)
        for path, _ in writes:
            temporary = staged[path]
            os.replace(temporary, path)
            staged.pop(path)
    except Exception as error:
        rollback_errors: list[Exception] = []
        for path, _ in reversed(writes):
            try:
                old = previous[path]
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(path, old)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise JsonStoreError(
                "提交失败且无法完整恢复先前状态"
            ) from error
        raise JsonStoreError("提交失败，已恢复先前状态") from error
    finally:
        for temporary in staged.values():
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _stage_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.unlink(handle.name)
        except FileNotFoundError:
            pass
        raise
    return handle.name


def _atomic_write_json(path: Path, payload: object) -> None:
    temporary = _stage_json(path, payload)
    try:
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = handle.name
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
