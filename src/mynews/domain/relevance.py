"""不依赖模型的 AI/科技候选相关性策略。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from mynews.domain.models import Candidate

_AI_TERMS = (
    "ai",
    "openai",
    "anthropic",
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "llm", "gpt", "claude", "gemini", "qwen", "deepseek", "codex",
    "copilot", "cursor", "模型", "人工智能", "大模型", "智能体",
)
_TECH_TERMS = (
    "software", "developer", "programming", "developer tools", "api",
    "cloud", "chip", "gpu", "semiconductor", "cybersecurity", "rust",
    "编程", "开发者", "软件", "芯片", "云计算", "科技",
)
_HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
_URL_PATTERN = re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RelevanceDecision:
    relevant: bool
    score: int
    reason: str


class AiTechnologyRelevanceFilter:
    """用固定词表筛选 discovery，模型不能改变筛选边界。"""

    def evaluate(self, candidate: Candidate) -> RelevanceDecision:
        text = _searchable_text(
            " ".join(
                value
                for value in (
                    candidate.title_original,
                    candidate.excerpt,
                    candidate.content,
                )
                if value
            )
        )
        ai_matches = sum(_contains_term(text, term) for term in _AI_TERMS)
        tech_matches = sum(_contains_term(text, term) for term in _TECH_TERMS)
        score = min(100, (ai_matches + tech_matches) * 25)
        if ai_matches or tech_matches:
            return RelevanceDecision(True, score, "ai_or_technology_match")
        return RelevanceDecision(False, 0, "irrelevant_ai_technology")


def _contains_term(text: str, term: str) -> bool:
    normalized = term.casefold()
    if not normalized.isascii():
        return normalized in text
    pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _searchable_text(value: str) -> str:
    """只保留候选可读文本，避免 URL/HTML 元数据制造词命中。"""
    unescaped = unescape(value)
    without_tags = _HTML_TAG_PATTERN.sub(" ", unescaped)
    return _URL_PATTERN.sub(" ", without_tags).casefold()
