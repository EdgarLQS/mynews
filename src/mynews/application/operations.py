"""离线运行可靠性诊断、保留计划和隔离恢复检查。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from mynews.application.automation import validate_automation_state
from mynews.application.output_safety import OutputSafetyError, ensure_safe_output
from mynews.domain.deduplication import DedupState
from mynews.domain.models import (
    Digest,
    PendingVerificationState,
    PriceSnapshot,
    RunReport,
    SourceSnapshot,
)
from mynews.domain.operations import (
    OperationIssueCategory,
    OperationsCheck,
    OperationsFile,
    OperationsIssue,
    OperationsReport,
    OperationsSummary,
    RetentionCandidate,
)
from mynews.storage.artifact_committer import ArtifactCommitter, ArtifactWrite

RECOVERY_EXACT_PATHS = (
    "output/latest.json",
    "output/digest-latest.json",
    "output/digest-latest.md",
    "output/editorial/publication-ledger.csv",
    "output/editorial/weekly-feedback.md",
    "state/dedup.json",
    "state/pending_verifications.json",
    "state/editorial/automation/state.json",
    "state/editorial-observations.json",
)
RECOVERY_GLOBS = (
    "output/runs/*.json",
    "output/digests/*.json",
    "output/editorial/automation/reports/*.md",
    "state/price_snapshots/*.json",
    "state/source_snapshots/*.json",
)
DIAGNOSTIC_GLOBS = (*RECOVERY_GLOBS, "logs/*.log")
LATEST_PATHS = {"output/latest.json", "output/digest-latest.json"}
MANUAL_PATHS = {
    "output/editorial/publication-ledger.csv",
    "output/editorial/weekly-feedback.md",
}


class OperationsError(RuntimeError):
    """运行可靠性命令无法安全完成。"""


def diagnose(
    root: Path,
    *,
    days: int,
    now: datetime | None = None,
) -> OperationsReport:
    """只读检查运行结果、状态和日志，并按故障类别汇总。"""

    try:
        return _diagnose(root, days=days, now=now)
    except OperationsError:
        raise
    except (OSError, TypeError, ValueError, KeyError) as error:
        raise OperationsError("运行可靠性诊断失败") from error


def _diagnose(
    root: Path,
    *,
    days: int,
    now: datetime | None = None,
) -> OperationsReport:


    _require_positive(days, "诊断天数")
    base = _require_directory(root, "运行根目录")
    current = _aware_now(now)
    issues: list[OperationsIssue] = []
    paths = _inventory(base, include_logs=True)
    files = _summarize_files(paths, base, issues)
    reports = _inspect_reports(paths, base, issues)
    pending_count = _pending_count(base, issues)
    automation = _automation_summary(base, issues)
    latest_age = _latest_age(reports, days, current, issues)
    failures = max(_consecutive_failures(reports.values()), automation[1])
    summary = OperationsSummary(
        files_scanned=len(files),
        pending_count=pending_count,
        latest_age_days=latest_age,
        last_successful_slot=automation[0],
        consecutive_failures=failures,
    )
    return OperationsReport(
        operation="diagnose",
        status="partial" if issues else "complete",
        summary=summary,
        files=files,
        issues=sorted(issues, key=_issue_sort_key),
    )


def build_retention_plan(
    root: Path,
    *,
    older_than_days: int,
    now: datetime | None = None,
) -> OperationsReport:
    """生成只读候选清单，不移动、删除或修改任何运行文件。"""

    try:
        return _build_retention_plan(
            root, older_than_days=older_than_days, now=now
        )
    except OperationsError:
        raise
    except (OSError, TypeError, ValueError, KeyError) as error:
        raise OperationsError("运行可靠性保留计划失败") from error


def _build_retention_plan(
    root: Path,
    *,
    older_than_days: int,
    now: datetime | None = None,
) -> OperationsReport:


    _require_positive(older_than_days, "保留期限")
    base = _require_directory(root, "运行根目录")
    current = _aware_now(now)
    issues: list[OperationsIssue] = []
    paths = _inventory(base, include_logs=True)
    files = _summarize_files(paths, base, issues)
    protected = _protected_paths(base, paths, issues)
    cutoff = current - timedelta(days=older_than_days)
    candidates = _retention_candidates(paths, base, protected, cutoff, issues)
    summary = OperationsSummary(
        files_scanned=len(files),
        candidate_count=len(candidates),
        protected_count=len(protected),
    )
    return OperationsReport(
        operation="retention-plan",
        status="partial" if issues else "complete",
        summary=summary,
        files=files,
        protected_paths=sorted(protected),
        candidates=candidates,
        issues=sorted(issues, key=_issue_sort_key),
    )


def recovery_check(source_root: Path, target: Path) -> OperationsReport:
    """将白名单数据恢复到全新目录，并校验 Schema、引用和哈希。"""

    try:
        return _recovery_check(source_root, target)
    except OperationsError:
        raise
    except (OSError, TypeError, ValueError, KeyError) as error:
        raise OperationsError("运行可靠性恢复检查失败") from error


def _recovery_check(source_root: Path, target: Path) -> OperationsReport:

    source = _require_directory(source_root, "恢复源目录")
    destination = _validate_target(source, target)
    issues: list[OperationsIssue] = []
    paths = _inventory(source, include_logs=False)
    if not paths:
        raise OperationsError("恢复源目录缺少可恢复数据")
    files = _summarize_files(paths, source, issues)
    checks = _validate_recovery_source(paths, source, issues)
    if issues:
        return _recovery_report(files, checks, issues, copied_count=0)
    stage = _stage_recovery(paths, source, destination, issues)
    if stage is None:
        return _recovery_report(files, checks, issues, copied_count=0)
    copied = _summarize_files(_inventory(stage, include_logs=False), stage, issues)
    _check_hashes(files, copied, issues)
    if issues:
        _cleanup_stage(stage)
        return _recovery_report(files, checks, issues, copied_count=0)
    if not _install_stage(stage, destination, issues):
        return _recovery_report(files, checks, issues, copied_count=0)
    checks.append(OperationsCheck(name="hashes", status="passed", count=len(files)))
    return _recovery_report(files, checks, issues, copied_count=len(copied))


def write_operations_report(
    report: OperationsReport,
    out_dir: Path,
) -> tuple[Path, Path]:
    """原子写入 Operations JSON 和中文 Markdown。"""

    json_path = out_dir / "operations.json"
    markdown_path = out_dir / "operations.md"
    try:
        validated = OperationsReport.model_validate(report)
        payload = validated.model_dump(mode="json")
        markdown = render_operations_report(validated)
        ensure_safe_output(payload, root="operations")
        ensure_safe_output(markdown, root="operationsMarkdown")
        ArtifactCommitter().commit(
            (
                ArtifactWrite.json(json_path, payload),
                ArtifactWrite.text(markdown_path, markdown),
            )
        )
    except OutputSafetyError as error:
        raise OperationsError("运行可靠性输出不安全") from error
    except Exception as error:
        raise OperationsError("运行可靠性报告提交失败") from error
    return json_path, markdown_path


def render_operations_report(report: OperationsReport) -> str:
    """将报告渲染为不含正文和秘密的中文摘要。"""

    summary = report.summary
    lines = [
        "# mynews 运行可靠性",
        "",
        f"- 操作：`{report.operation}`",
        f"- 状态：`{report.status}`",
        f"- Schema：`{report.schema_version}`",
        "",
        "## 汇总",
        "",
        f"- 扫描文件：{summary.files_scanned}",
        f"- 保留候选：{summary.candidate_count}",
        f"- 受保护文件：{summary.protected_count}",
        f"- 已复制文件：{summary.copied_count}",
        f"- 校验数量：{summary.check_count}",
        f"- pending：{summary.pending_count}",
        f"- 连续失败：{summary.consecutive_failures}",
        "",
    ]
    lines.extend(_render_operations_section("问题", report.issues))
    lines.extend(_render_operations_section("保留候选", report.candidates))
    lines.extend(_render_operations_section("校验", report.checks))
    lines.extend(_render_paths("受保护路径", report.protected_paths))
    return "\n".join(lines).rstrip() + "\n"


def _render_operations_section(title: str, values: Iterable[object]) -> list[str]:
    items = list(values)
    lines = [f"## {title}", ""]
    if not items:
        return lines + ["- 无", ""]
    for value in items:
        if isinstance(value, OperationsIssue):
            path = value.path or "-"
            lines.append(f"- `{value.category}/{value.code}`：`{path}`")
        elif isinstance(value, RetentionCandidate):
            lines.append(f"- `{value.path}`：{value.sha256}")
        elif isinstance(value, OperationsCheck):
            lines.append(f"- `{value.name}`：`{value.status}`（{value.count}）")
    return lines + [""]


def _render_paths(title: str, paths: Iterable[str]) -> list[str]:
    values = list(paths)
    lines = [f"## {title}", ""]
    return lines + ([f"- `{path}`" for path in values] or ["- 无"]) + [""]


def _require_positive(value: int, label: str) -> None:
    if value <= 0:
        raise OperationsError(f"{label}必须是正整数")


def _require_directory(path: Path, label: str) -> Path:
    candidate = path.resolve()
    if not candidate.is_dir():
        raise OperationsError(f"{label}不存在或不是目录")
    return candidate


def _validate_target(source: Path, target: Path) -> Path:
    raw_target = Path(target)
    if raw_target.exists() and raw_target.is_symlink():
        raise OperationsError("恢复目标不能是符号链接")
    destination = raw_target.absolute().parent.resolve() / raw_target.name
    if destination == source or destination.is_relative_to(source):
        raise OperationsError("恢复目标不能位于源目录内")
    if raw_target.exists() and not raw_target.is_dir():
        raise OperationsError("恢复目标必须是目录")
    try:
        if raw_target.exists() and any(raw_target.iterdir()):
            raise OperationsError("目标目录必须为空")
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OperationsError:
        raise
    except OSError as error:
        raise OperationsError("恢复目标目录不可访问") from error
    return destination


def _inventory(root: Path, *, include_logs: bool) -> list[Path]:
    patterns = DIAGNOSTIC_GLOBS if include_logs else RECOVERY_GLOBS
    values = [root / relative for relative in RECOVERY_EXACT_PATHS]
    values.extend(path for pattern in patterns for path in root.glob(pattern))
    return sorted(
        {path for path in values if path.is_file() and not path.is_symlink()},
        key=lambda path: _relative(path, root),
    )


def _summarize_files(
    paths: Iterable[Path], root: Path, issues: list[OperationsIssue]
) -> list[OperationsFile]:
    files: list[OperationsFile] = []
    for path in paths:
        relative = _relative(path, root)
        try:
            content = path.read_bytes()
        except OSError:
            issues.append(_issue("storage", "file_unreadable", relative))
            continue
        digest = hashlib.sha256(content).hexdigest()
        files.append(
            OperationsFile(
                path=relative,
                size_bytes=len(content),
                sha256=f"sha256:{digest}",
            )
        )
    return files


def _inspect_reports(
    paths: Iterable[Path], root: Path, issues: list[OperationsIssue]
) -> dict[str, RunReport]:
    reports: dict[str, RunReport] = {}
    for path in paths:
        relative = _relative(path, root)
        if not _is_run_report_path(relative):
            continue
        try:
            report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if relative.startswith("logs/"):
                _inspect_text_log(path, relative, issues)
            else:
                issues.append(_issue("schema", "run_report_invalid", relative))
            continue
        reports[relative] = report
        _inspect_run(report, relative, issues)
    return reports


def _inspect_text_log(
    path: Path,
    relative: str,
    issues: list[OperationsIssue],
) -> None:
    try:
        content = path.read_text(encoding="utf-8").casefold()
    except OSError:
        issues.append(_issue("storage", "log_unreadable", relative))
        return
    categories: dict[str, OperationIssueCategory] = {
        "codex": "codex",
        "network": "network",
        "timeout": "network",
        "evidence": "evidence",
        "verification": "evidence",
        "schedule": "scheduling",
    }
    found: set[str] = set()
    for token, category in categories.items():
        if token in content and category not in found:
            found.add(category)
            issues.append(_issue(category, f"{category}_failure", relative))


def _is_run_report_path(relative: str) -> bool:
    return (
        relative == "output/latest.json"
        or relative.startswith("output/runs/")
        or relative.startswith("logs/")
    )


def _inspect_run(
    report: RunReport,
    relative: str,
    issues: list[OperationsIssue],
) -> None:
    if report.status == "failed":
        issues.append(_issue("storage", "run_failed", relative))
    for source in report.sources:
        if source.health == "healthy":
            continue
        issues.append(_issue("source", "source_unhealthy", relative))
        if source.error is not None:
            category = _failure_category(source.error.code)
            if category is not None:
                issues.append(_issue(category, f"{category}_failure", relative))
    for reason, count in report.reason_counts.items():
        if count <= 0:
            continue
        category = _failure_category(reason)
        if category is not None:
            issues.append(_issue(category, f"{category}_failure", relative))


def _failure_category(value: str) -> OperationIssueCategory | None:
    lowered = value.casefold()
    if "codex" in lowered:
        return "codex"
    if any(token in lowered for token in ("network", "timeout", "http_", "dns")):
        return "network"
    if any(token in lowered for token in ("evidence", "verification", "primary")):
        return "evidence"
    return None


def _pending_count(root: Path, issues: list[OperationsIssue]) -> int:
    path = root / "state/pending_verifications.json"
    if not path.is_file():
        return 0
    relative = _relative(path, root)
    entries: object = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("entries", {})
        count = len(entries) if isinstance(entries, dict) else 0
        PendingVerificationState.model_validate(payload)
        return count
    except (OSError, ValueError, TypeError):
        issues.append(_issue("schema", "pending_invalid", relative))
        return len(entries) if isinstance(entries, dict) else 0


def _automation_summary(
    root: Path,
    issues: list[OperationsIssue],
) -> tuple[str | None, int]:
    path = root / "state/editorial/automation/state.json"
    if not path.is_file():
        return None, 0
    relative = _relative(path, root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_automation_state(payload)
    except (OSError, ValueError, TypeError):
        issues.append(_issue("schema", "automation_state_invalid", relative))
        return None, 0
    attempt = _parse_datetime(payload.get("lastAttemptAt"))
    success = _parse_datetime(payload.get("lastSuccessAt"))
    consecutive = int(attempt is not None and (success is None or attempt > success))
    if consecutive:
        issues.append(_issue("scheduling", "automation_not_successful", relative))
    return payload.get("lastCompletedSlot"), consecutive


def _latest_age(
    reports: dict[str, RunReport],
    threshold: int,
    now: datetime,
    issues: list[OperationsIssue],
) -> int | None:
    latest = reports.get("output/latest.json")
    if latest is None:
        return None
    age = max(0, int((now - latest.finished_at).total_seconds() // 86400))
    if age > threshold:
        issues.append(_issue("storage", "latest_stale", "output/latest.json"))
    return age


def _consecutive_failures(reports: Iterable[RunReport]) -> int:
    ordered = sorted(reports, key=lambda report: report.finished_at, reverse=True)
    count = 0
    for report in ordered:
        if report.status != "failed":
            break
        count += 1
    return count


def _protected_paths(
    root: Path,
    paths: Iterable[Path],
    issues: list[OperationsIssue],
) -> set[str]:
    available = {_relative(path, root) for path in paths}
    protected = {
        path for path in available if path in MANUAL_PATHS or path in LATEST_PATHS
    }
    protected.update(path for path in available if path.startswith("state/"))
    _protect_latest_references(root, available, protected, issues)
    return protected


def _protect_latest_references(
    root: Path,
    available: set[str],
    protected: set[str],
    issues: list[OperationsIssue],
) -> None:
    latest = root / "output/latest.json"
    payload = _read_payload(latest, "output/latest.json", issues)
    if isinstance(payload, dict):
        _protect_identifier(
            payload, "run_id", "output/runs", available, protected, issues
        )
    digest_latest = root / "output/digest-latest.json"
    payload = _read_payload(digest_latest, "output/digest-latest.json", issues)
    if isinstance(payload, dict):
        _protect_identifier(
            payload, "digest_id", "output/digests", available, protected, issues
        )
    _protect_digest_run_references(root, available, protected, issues)
    automation = root / "state/editorial/automation/state.json"
    payload = _read_payload(automation, "state/editorial/automation/state.json", issues)
    if isinstance(payload, dict):
        reported = payload.get("reportedEvents", {})
        if not isinstance(reported, dict):
            issues.append(
                _issue(
                    "schema",
                    "automation_state_invalid",
                    "state/editorial/automation/state.json",
                )
            )
            reported = {}
        references = [payload.get("lastReport")]
        references.extend(
            event.get("reportPath")
            for event in reported.values()
            if isinstance(event, dict)
        )
        for value in references:
            _protect_relative_reference(value, available, protected, issues)


def _protect_digest_run_references(
    root: Path,
    available: set[str],
    protected: set[str],
    issues: list[OperationsIssue],
) -> None:
    digest_paths = sorted(
        path
        for path in available
        if path == "output/digest-latest.json" or path.startswith("output/digests/")
    )
    for relative in digest_paths:
        payload = _read_payload(root / relative, relative, issues)
        if isinstance(payload, dict):
            _protect_identifier(
                payload, "run_id", "output/runs", available, protected, issues
            )


def _protect_identifier(
    payload: dict[str, Any],
    field: str,
    directory: str,
    available: set[str],
    protected: set[str],
    issues: list[OperationsIssue],
) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return
    relative = f"{directory}/{_safe_filename(value)}.json"
    if relative in available:
        protected.add(relative)
    else:
        issues.append(_issue("reference", "latest_history_missing", relative))


def _protect_relative_reference(
    value: object,
    available: set[str],
    protected: set[str],
    issues: list[OperationsIssue],
) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not _is_safe_relative(value):
        issues.append(
            _issue(
                "reference",
                "automation_reference_invalid",
                "state/editorial/automation/state.json",
            )
        )
        return
    if value in available:
        protected.add(value)
    else:
        issues.append(_issue("reference", "automation_reference_missing", value))


def _retention_candidates(
    paths: Iterable[Path],
    root: Path,
    protected: set[str],
    cutoff: datetime,
    issues: list[OperationsIssue],
) -> list[RetentionCandidate]:
    candidates: list[RetentionCandidate] = []
    for path in paths:
        relative = _relative(path, root)
        if relative in protected or not _retention_path(relative):
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            content = path.read_bytes()
        except OSError:
            issues.append(_issue("storage", "file_changed_during_scan", relative))
            continue
        if modified >= cutoff:
            continue
        candidates.append(
            RetentionCandidate(
                path=relative,
                size_bytes=len(content),
                sha256=f"sha256:{hashlib.sha256(content).hexdigest()}",
                reason="超过保留期限，待人工确认",
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.path)


def _retention_path(relative: str) -> bool:
    return (
        relative.startswith("output/runs/")
        or relative.startswith("output/digests/")
        or relative.startswith("output/editorial/automation/reports/")
        or relative.startswith("logs/")
    )


def _validate_recovery_source(
    paths: Iterable[Path],
    root: Path,
    issues: list[OperationsIssue],
) -> list[OperationsCheck]:
    checks: list[OperationsCheck] = []
    _validate_required_recovery_data(paths, root, issues, checks)
    for path in paths:
        relative = _relative(path, root)
        if relative.endswith(".csv") or relative.endswith(".md"):
            continue
        if _validate_json_schema(path, relative, issues):
            checks.append(
                OperationsCheck(name=f"schema:{relative}", status="passed", count=1)
            )
        else:
            checks.append(
                OperationsCheck(name=f"schema:{relative}", status="failed", count=0)
            )
    _validate_references(root, paths, issues, checks)
    return checks


def _validate_required_recovery_data(
    paths: Iterable[Path],
    root: Path,
    issues: list[OperationsIssue],
    checks: list[OperationsCheck],
) -> None:
    available = {_relative(path, root) for path in paths}
    required = {
        "output/latest.json",
        "state/dedup.json",
        "state/pending_verifications.json",
    }
    missing = required - available
    if not any(path.startswith("output/runs/") for path in available):
        missing.add("output/runs/*.json")
    if missing:
        issues.append(_issue("input", "recovery_required_data_missing", None))
        checks.append(OperationsCheck(name="required-data", status="failed", count=0))
    else:
        checks.append(OperationsCheck(name="required-data", status="passed", count=1))


def _validate_json_schema(
    path: Path,
    relative: str,
    issues: list[OperationsIssue],
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _is_run_report_path(relative) and relative != "logs/collect.log":
            RunReport.model_validate(payload)
        elif relative == "output/digest-latest.json" or relative.startswith(
            "output/digests/"
        ):
            Digest.model_validate(payload)
        elif relative == "state/dedup.json":
            DedupState.model_validate(payload)
        elif relative == "state/pending_verifications.json":
            PendingVerificationState.model_validate(payload)
        elif relative == "state/editorial/automation/state.json":
            validate_automation_state(payload)
        elif relative.startswith("state/price_snapshots/"):
            PriceSnapshot.model_validate(payload)
        elif relative.startswith("state/source_snapshots/"):
            SourceSnapshot.model_validate(payload)
    except (OSError, ValueError, TypeError):
        issues.append(_issue("schema", "recovery_schema_invalid", relative))
        return False
    return True


def _validate_references(
    root: Path,
    paths: Iterable[Path],
    issues: list[OperationsIssue],
    checks: list[OperationsCheck],
) -> None:
    available = {_relative(path, root) for path in paths}
    before = len(issues)
    _protect_latest_references(root, available, set(), issues)
    checks.append(
        OperationsCheck(
            name="references",
            status="failed" if len(issues) > before else "passed",
            count=0 if len(issues) > before else 1,
        )
    )


def _stage_recovery(
    paths: Iterable[Path],
    source: Path,
    destination: Path,
    issues: list[OperationsIssue],
) -> Path | None:
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        for path in paths:
            relative = _relative(path, source)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    except OSError:
        issues.append(_issue("storage", "recovery_copy_failed", None))
        _cleanup_stage(stage)
        return None
    return stage


def _check_hashes(
    source_files: Iterable[OperationsFile],
    copied_files: Iterable[OperationsFile],
    issues: list[OperationsIssue],
) -> None:
    source_map = {item.path: item.sha256 for item in source_files}
    copied_map = {item.path: item.sha256 for item in copied_files}
    for path, digest in source_map.items():
        if copied_map.get(path) != digest:
            issues.append(_issue("storage", "recovery_hash_mismatch", path))


def _install_stage(
    stage: Path, destination: Path, issues: list[OperationsIssue]
) -> bool:
    try:
        if destination.exists():
            destination.rmdir()
        os.replace(stage, destination)
        return True
    except OSError:
        if not destination.exists():
            try:
                destination.mkdir(parents=False)
            except OSError:
                pass
        issues.append(_issue("storage", "recovery_install_failed", None))
        _cleanup_stage(stage)
        return False


def _cleanup_stage(stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)


def _recovery_report(
    files: list[OperationsFile],
    checks: list[OperationsCheck],
    issues: list[OperationsIssue],
    *,
    copied_count: int,
) -> OperationsReport:
    failed_checks = sum(check.status == "failed" for check in checks)
    summary = OperationsSummary(
        files_scanned=len(files),
        copied_count=copied_count,
        check_count=len(checks),
        failed_check_count=failed_checks,
    )
    return OperationsReport(
        operation="recovery-check",
        status="failed" if issues else "complete",
        summary=summary,
        files=files,
        checks=checks,
        issues=sorted(issues, key=_issue_sort_key),
    )


def _read_payload(
    path: Path,
    relative: str,
    issues: list[OperationsIssue],
) -> object | None:
    if not path.is_file():
        return None
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        issues.append(_issue("schema", "json_invalid", relative))
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _aware_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise OperationsError("当前时间必须包含时区")
    return current


def _issue(
    category: OperationIssueCategory,
    code: str,
    path: str | None,
) -> OperationsIssue:
    return OperationsIssue(
        category=category,
        code=code,
        path=path,
        detail="检测到需要人工处理的运行可靠性问题",
    )


def _issue_sort_key(issue: OperationsIssue) -> tuple[str, str, str]:
    return issue.category, issue.code, issue.path or ""


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _safe_filename(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(":", "-")


def _is_safe_relative(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


__all__ = [
    "OperationsError",
    "build_retention_plan",
    "diagnose",
    "recovery_check",
    "render_operations_report",
    "write_operations_report",
]
