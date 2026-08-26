"""周复盘与只读编辑建议的独立 1.0 数据契约。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EditorialLayer = Literal["published", "unpublished", "pending"]
EditorialHintKind = Literal["duplicate_topic", "substantive_update"]
EditorialSuggestionKind = Literal[
    "duplicate_topic",
    "substantive_update",
    "trend",
    "model_suggestion",
]
EditorialCodexMode = Literal[
    "disabled",
    "skipped_incomplete",
    "used",
    "partial",
]


class EditorialContractModel(BaseModel):
    """拒绝未知字段，保证周报告的机器可读契约稳定。"""

    model_config = ConfigDict(extra="forbid")


class EditorialEvent(EditorialContractModel):
    """一个可追溯的周复盘事件。"""

    event_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    layer: EditorialLayer


class EditorialHint(EditorialContractModel):
    """确定性生成的重复选题或实质更新提示。"""

    kind: EditorialHintKind
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    references: list[str] = Field(min_length=1)


class EditorialSuggestion(EditorialContractModel):
    """Codex 或确定性规则生成的可追溯建议。"""

    kind: EditorialSuggestionKind
    text: str = Field(min_length=1)
    references: list[str] = Field(min_length=1)


class EditorialInputSummary(EditorialContractModel):
    """输入覆盖和真实输入门槛，不回写输入文件。"""

    candidate_batch_count: int = Field(ge=0)
    digest_count: int = Field(ge=0)
    publication_count: int = Field(ge=0)
    feedback_count: int = Field(ge=0)
    complete_iso_week_count: int = Field(ge=0)
    available_iso_weeks: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)


class EditorialFeedbackSummary(EditorialContractModel):
    """已保存周反馈的可重复聚合，不代表新闻事实。"""

    record_count: int = Field(ge=0)
    weeks: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    reads: int = Field(ge=0)
    favorites: int = Field(ge=0)
    shares: int = Field(ge=0)
    new_followers: int = Field(ge=0)


class EditorialStats(EditorialContractModel):
    """周复盘的确定性统计，不是综合评分。"""

    candidate_count: int = Field(ge=0)
    digest_item_count: int = Field(ge=0)
    published_count: int = Field(ge=0)
    unpublished_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    publication_record_count: int = Field(ge=0)
    feedback_record_count: int = Field(ge=0)
    duplicate_topic_count: int = Field(ge=0)
    substantive_update_count: int = Field(ge=0)


class EditorialCodexStatus(EditorialContractModel):
    """Codex 状态只描述建议生成，不代表事实核验。"""

    mode: EditorialCodexMode
    accepted_count: int = Field(ge=0)
    error: str | None = None


class EditorialReview(EditorialContractModel):
    """EditorialReview 1.0 周复盘报告。"""

    schema_version: Literal["1.0"] = "1.0"
    week: str
    generated_at: datetime
    status: Literal["complete", "partial"]
    inputs: EditorialInputSummary
    feedback: EditorialFeedbackSummary
    stats: EditorialStats
    published: list[EditorialEvent] = Field(default_factory=list)
    unpublished: list[EditorialEvent] = Field(default_factory=list)
    pending: list[EditorialEvent] = Field(default_factory=list)
    duplicate_topics: list[EditorialHint] = Field(default_factory=list)
    substantive_updates: list[EditorialHint] = Field(default_factory=list)
    suggestions: list[EditorialSuggestion] = Field(default_factory=list)
    codex: EditorialCodexStatus

    @field_validator("week")
    @classmethod
    def validate_iso_week(cls, value: str) -> str:
        try:
            year, week = value.split("-W", 1)
            date.fromisocalendar(int(year), int(week), 1)
        except (ValueError, TypeError):
            raise ValueError("周必须是有效的 YYYY-Www ISO 周") from None
        if len(value) != 8 or value[4] != "-" or value[5] != "W":
            raise ValueError("周必须是有效的 YYYY-Www ISO 周")
        return value

    @field_validator("generated_at")
    @classmethod
    def require_aware_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("编辑复盘生成时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_suggestion_limit(self) -> EditorialReview:
        if len(self.suggestions) > 5:
            raise ValueError("编辑建议最多 5 条")
        return self


__all__ = [
    "EditorialCodexMode",
    "EditorialCodexStatus",
    "EditorialEvent",
    "EditorialFeedbackSummary",
    "EditorialHint",
    "EditorialHintKind",
    "EditorialInputSummary",
    "EditorialLayer",
    "EditorialReview",
    "EditorialStats",
    "EditorialSuggestion",
    "EditorialSuggestionKind",
]
