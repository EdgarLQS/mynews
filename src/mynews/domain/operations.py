"""运行可靠性命令的独立 Operations 1.0 数据契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OperationName = Literal["diagnose", "retention-plan", "recovery-check"]
OperationStatus = Literal["complete", "partial", "failed"]
OperationIssueCategory = Literal[
    "source",
    "network",
    "codex",
    "evidence",
    "storage",
    "scheduling",
    "schema",
    "reference",
    "input",
]


class OperationsContractModel(BaseModel):
    """拒绝未知字段，避免运维报告语义漂移。"""

    model_config = ConfigDict(extra="forbid")


class OperationsFile(OperationsContractModel):
    """只保存相对路径、大小和内容哈希。"""

    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def require_relative_path(cls, value: str) -> str:
        if not _is_relative_path(value):
            raise ValueError("Operations 文件路径必须是相对路径")
        return value


class OperationsIssue(OperationsContractModel):
    """不回显正文或秘密的结构化问题。"""

    category: OperationIssueCategory
    code: str = Field(min_length=1)
    path: str | None = None
    detail: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def require_relative_issue_path(cls, value: str | None) -> str | None:
        if value is not None and not _is_relative_path(value):
            raise ValueError("Operations 问题路径必须是相对路径")
        return value


class RetentionCandidate(OperationsFile):
    """可由人工后续处理的旧文件候选；命令本身不会处理它。"""

    reason: str = Field(min_length=1)


class OperationsCheck(OperationsContractModel):
    """恢复检查中的一个确定性校验。"""

    name: str = Field(min_length=1)
    status: Literal["passed", "failed", "skipped"]
    count: int = Field(ge=0)


class OperationsSummary(OperationsContractModel):
    """三个运维命令共享的统计字段。"""

    files_scanned: int = Field(default=0, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    protected_count: int = Field(default=0, ge=0)
    copied_count: int = Field(default=0, ge=0)
    check_count: int = Field(default=0, ge=0)
    failed_check_count: int = Field(default=0, ge=0)
    pending_count: int = Field(default=0, ge=0)
    latest_age_days: int | None = Field(default=None, ge=0)
    last_successful_slot: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)


class OperationsReport(OperationsContractModel):
    """Operations 1.0；不修改 RunReport、Candidate、Digest 或任务状态。"""

    schema_version: Literal["1.0"] = "1.0"
    operation: OperationName
    status: OperationStatus
    summary: OperationsSummary = Field(default_factory=OperationsSummary)
    files: list[OperationsFile] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    candidates: list[RetentionCandidate] = Field(default_factory=list)
    checks: list[OperationsCheck] = Field(default_factory=list)
    issues: list[OperationsIssue] = Field(default_factory=list)

    @field_validator("protected_paths")
    @classmethod
    def require_relative_protected_paths(cls, value: list[str]) -> list[str]:
        if any(not _is_relative_path(path) for path in value):
            raise ValueError("Operations 受保护路径必须是相对路径")
        return value

    @classmethod
    def empty(cls, operation: OperationName) -> OperationsReport:
        """构造没有运行数据的空报告，供 CLI 和测试使用。"""

        return cls(operation=operation, status="complete")


def _is_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return bool(normalized) and not normalized.startswith("/") and not (
        len(normalized) >= 2 and normalized[1] == ":"
    ) and all(part not in {"", ".", ".."} for part in normalized.split("/"))


__all__ = [
    "OperationIssueCategory",
    "OperationName",
    "OperationStatus",
    "OperationsCheck",
    "OperationsFile",
    "OperationsIssue",
    "OperationsReport",
    "OperationsSummary",
    "RetentionCandidate",
]
