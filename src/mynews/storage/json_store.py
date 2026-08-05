"""使用同目录临时文件和 os.replace 的 JSON NewsStore。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from mynews.domain.deduplication import DedupState
from mynews.domain.models import PriceSnapshot, RunReport, SourceSnapshot
from mynews.domain.normalization import normalize_url
from mynews.storage.protocol import StoredRun


class JsonStoreError(RuntimeError):
    """JSON Store 无法安全提交或恢复状态。"""


class JsonNewsStore:
    """保存 output/、state/，并保证单个文件替换是原子的。"""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._output = self._root / "output"
        self._runs = self._output / "runs"
        self._state = self._root / "state"
        self._prices = self._state / "price_snapshots"
        self._snapshots = self._state / "source_snapshots"

    @property
    def root(self) -> Path:
        return self._root

    def commit(
        self, report: RunReport, *, dedup_state: DedupState | None = None
    ) -> StoredRun:
        validated = RunReport.model_validate(report)
        payload = validated.model_dump(mode="json", by_alias=True)
        run_path = self._runs / f"{_safe_filename(validated.run_id)}.json"
        if run_path.exists():
            raise JsonStoreError(f"运行文件已存在：{run_path.name}")
        _atomic_write_json(run_path, payload)
        if dedup_state is not None:
            self.save_dedup_state(dedup_state)
        latest_updated = validated.status in {"complete", "partial"}
        if latest_updated:
            _atomic_write_json(self._output / "latest.json", payload)
        return StoredRun(run_path=run_path, latest_updated=latest_updated)

    def load_dedup_state(self) -> DedupState:
        path = self._state / "dedup.json"
        if not path.exists():
            return DedupState()
        try:
            return DedupState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise JsonStoreError(f"无法恢复去重状态：{path}") from error

    def save_dedup_state(self, state: DedupState) -> Path:
        validated = DedupState.model_validate(state)
        path = self._state / "dedup.json"
        _atomic_write_json(path, validated.model_dump(mode="json"))
        return path

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


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
