"""发布前 RunReport、Schema 和已验证证据的可重复检查。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from mynews.domain.models import NewsItem, RunReport
from mynews.sources.protocol import SourceMetadata
from mynews.sources.registry import SourceRegistry, default_registry
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
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.schema_valid and not self.errors

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "passed" if self.passed else "failed",
            "run": self.run_path,
            "schema_valid": self.schema_valid,
            "verified_count": self.verified_count,
            "evidence_count": self.evidence_count,
            "evidence_checked": self.evidence_checked,
            "errors": list(self.errors),
        }
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload

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
            str(path),
            True,
            len(verified_items),
            evidence_count,
            False,
            (),
        )

    active_registry = registry or default_registry()
    verifier = CodexVerifier(active_registry.http)
    errors, warnings = _validate_verified_evidence(
        verified_items,
        active_registry,
        verifier,
        timeout,
    )
    return RunValidation(
        str(path),
        True,
        len(verified_items),
        evidence_count,
        True,
        tuple(errors),
        tuple(warnings),
    )


def _validate_verified_evidence(
    items: tuple[NewsItem, ...],
    registry: SourceRegistry,
    verifier: CodexVerifier,
    timeout: float,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for item in items:
        for evidence in item.primary_evidence:
            metadata = _metadata_for_evidence(item, evidence, registry)
            if metadata is None:
                errors.append(f"{item.event_key}: 找不到第一方来源元数据")
                continue
            target = VerificationTarget(
                item=item,
                source_id=metadata.source_id,
                publisher=metadata.name,
                excerpt=None,
                official_domains=metadata.official_domains,
                official_github_organizations=(
                    metadata.official_github_organizations
                ),
                source_role=metadata.role,
            )
            result = verifier.review_evidence(
                target,
                evidence,
                timeout=timeout,
            )
            if result.status == "failed":
                errors.append(
                    f"{item.event_key}: {result.reason}: {evidence.url}"
                )
            elif result.status == "changed_supporting":
                warnings.append(
                    f"{item.event_key}: {result.warning}: {evidence.url}"
                )
    return errors, warnings


def _metadata_for_evidence(
    item: NewsItem,
    evidence: object,
    registry: SourceRegistry,
) -> SourceMetadata | None:
    """根据证据 URL 在合并来源中选择对应的官方边界。"""
    evidence_url = str(getattr(evidence, "url", ""))
    try:
        parsed = urlsplit(evidence_url)
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold()
    organization = parsed.path.strip("/").split("/", 1)[0].casefold()
    source_metadata = registry.source_metadata
    direct_candidates = [
        source_metadata[source_id]
        for source_id in item.discovery_sources
        if source_id in source_metadata
        and source_metadata[source_id].role
        in {"primary", "monitor", "research", "incident"}
    ]
    matched = _match_evidence_metadata(direct_candidates, host, organization)
    if matched is not None:
        return matched
    has_discovery_source = any(
        source_metadata.get(source_id) is not None
        and source_metadata[source_id].role == "discovery"
        for source_id in item.discovery_sources
    )
    if not has_discovery_source:
        return None
    primary_candidates = [
        metadata
        for metadata in source_metadata.values()
        if metadata.role in {"primary", "monitor", "research", "incident"}
    ]
    return _match_evidence_metadata(primary_candidates, host, organization)


def _match_evidence_metadata(
    candidates: list[SourceMetadata], host: str, organization: str
) -> SourceMetadata | None:
    for metadata in candidates:
        domains = {domain.casefold().strip(".") for domain in metadata.official_domains}
        organizations = {
            value.casefold() for value in metadata.official_github_organizations
        }
        if host in domains or (
            host == "github.com" and organization in organizations
        ):
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
                RunReport.model_json_schema(),
                handle,
                ensure_ascii=False,
                indent=2,
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
