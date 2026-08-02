"""发布前 RunReport、Schema 和已验证证据的可重复检查。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mynews.domain.models import NewsItem, RunReport
from mynews.sources.protocol import SourceMetadata
from mynews.sources.registry import SourceRegistry, built_in_registry
from mynews.verification.codex import CodexVerifier
from mynews.verification.protocol import VerificationTarget


@dataclass(frozen=True, slots=True)
class RunValidation:
    run_path: str
    schema_valid: bool
    verified_count: int
    evidence_count: int
    evidence_checked: bool
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.schema_valid and not self.errors

    def as_payload(self) -> dict[str, object]:
        return {
            "status": "passed" if self.passed else "failed",
            "run": self.run_path,
            "schema_valid": self.schema_valid,
            "verified_count": self.verified_count,
            "evidence_count": self.evidence_count,
            "evidence_checked": self.evidence_checked,
            "errors": list(self.errors),
        }

    @classmethod
    def failed(cls, run_path: str, error: str) -> RunValidation:
        return cls(run_path, False, 0, 0, False, (error,))


def validate_run_file(
    path: Path,
    *,
    check_evidence: bool = False,
    timeout: float = 30.0,
    registry: SourceRegistry | None = None,
) -> RunValidation:
    """检查一个 RunReport；可选地重新抓取所有 verified 证据。"""
    try:
        report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return RunValidation.failed(str(path), str(error))

    verified_items = tuple(
        item for item in report.items if item.verification_status == "verified"
    )
    evidence_count = sum(len(item.primary_evidence) for item in verified_items)
    if not check_evidence or not evidence_count:
        return RunValidation(
            str(path), True, len(verified_items), evidence_count, False, ()
        )

    active_registry = registry or built_in_registry()
    verifier = CodexVerifier(active_registry.http)
    errors = _validate_verified_evidence(
        verified_items, active_registry, verifier, timeout
    )
    return RunValidation(
        str(path), True, len(verified_items), evidence_count, True, tuple(errors)
    )


def _validate_verified_evidence(
    items: tuple[NewsItem, ...],
    registry: SourceRegistry,
    verifier: CodexVerifier,
    timeout: float,
) -> list[str]:
    errors: list[str] = []
    for item in items:
        metadata = _metadata_for_item(item, registry)
        if metadata is None:
            errors.append(f"{item.event_key}: 找不到第一方来源元数据")
            continue
        target = VerificationTarget(
            item=item,
            source_id=metadata.source_id,
            publisher=metadata.name,
            excerpt=None,
            official_domains=metadata.official_domains,
            official_github_organizations=metadata.official_github_organizations,
            source_role=metadata.role,
        )
        for evidence in item.primary_evidence:
            _, reason = verifier.revalidate_evidence(
                target, evidence, timeout=timeout
            )
            if reason:
                errors.append(f"{item.event_key}: {reason}: {evidence.url}")
    return errors


def _metadata_for_item(
    item: NewsItem, registry: SourceRegistry
) -> SourceMetadata | None:
    for source_id in item.discovery_sources:
        metadata = registry.source_metadata.get(source_id)
        if metadata is not None and metadata.role in {"primary", "monitor"}:
            return metadata
    return None


def write_schema(path: Path) -> None:
    """导出与运行时校验同源的 RunReport JSON Schema。"""
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
            json.dump(
                RunReport.model_json_schema(), handle, ensure_ascii=False, indent=2
            )
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
