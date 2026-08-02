"""把来源候选转换成稳定的阶段 3 新闻事件。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mynews.domain.models import Candidate, NewsItem

_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "ref", "referrer"}
_SOURCE_ROLES = {"discovery", "primary", "monitor", "manual"}
_ROLE_ALIASES = {
    "official": "primary",
    "source": "primary",
    "news": "discovery",
    "price": "monitor",
}
_EVENT_ALIASES = {
    "release": "model_release",
    "model": "model_release",
    "model_release": "model_release",
    "price": "pricing_change",
    "pricing": "pricing_change",
    "pricing_change": "pricing_change",
    "update": "product_update",
    "product_update": "product_update",
    "research": "research",
    "security": "security",
    "funding": "funding",
}
_KNOWN_ENTITIES = (
    "OpenAI",
    "Anthropic",
    "Google",
    "Gemini",
    "Qwen",
    "DeepSeek",
    "GitHub",
    "NVIDIA",
    "Claude",
    "Codex",
    "Cursor",
)


class Normalizer:
    """负责候选的规范化，不访问来源、核验器或文件系统。"""

    def __init__(self, source_roles: Mapping[str, str] | None = None) -> None:
        self._source_roles = dict(source_roles or {})

    def normalize(
        self,
        candidates: Iterable[Candidate],
        *,
        observed_at: datetime | None = None,
    ) -> tuple[NewsItem, ...]:
        observed = observed_at or datetime.now(UTC)
        _require_aware(observed)
        return tuple(
            self.normalize_candidate(candidate, observed_at=observed)
            for candidate in candidates
        )

    def normalize_candidate(
        self, candidate: Candidate, *, observed_at: datetime | None = None
    ) -> NewsItem:
        observed = observed_at or datetime.now(UTC)
        _require_aware(observed)
        title = _clean_text(candidate.title_original)
        canonical_url = normalize_url(str(candidate.url))
        content = _clean_text(candidate.content or candidate.excerpt or title)
        content_hash = _content_hash(content)
        entities = normalize_entities(candidate.entities, title, content)
        published_at = _as_utc(candidate.published_at)
        event_key = build_event_key(
            canonical_url=canonical_url,
            entities=entities,
            title=title,
            published_at=published_at,
            content_hash=content_hash,
        )
        role = normalize_source_role(
            candidate.source_role or self._source_roles.get(candidate.source_id)
        )
        return NewsItem(
            id=event_key,
            event_key=event_key,
            event_type=normalize_event_type(candidate.event_type, title, content),
            title_original=title,
            language_original=normalize_language(
                candidate.language_original or candidate.language or title
            ),
            title_zh=_clean_text(candidate.title_zh or title),
            summary_zh=_clean_text(candidate.summary_zh or content),
            published_at=published_at,
            first_seen_at=observed.astimezone(UTC),
            heat_score=heat_score(candidate),
            relevance_score=candidate.relevance_score
            if candidate.relevance_score is not None
            else 50,
            discovery_sources=[candidate.source_id],
            verification_status="unverified",
            verification_reason="stage4_not_implemented",
            content_hash=content_hash,
            canonical_url=canonical_url,
            entities=entities,
            source_roles=[role],
        )


def normalize_url(value: str) -> str:
    """删除跟踪参数、片段和无意义尾斜线，保留业务查询参数。"""

    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("候选 URL 必须是带主机名的 HTTP(S) URL")
    hostname = parsed.hostname.lower()
    port = parsed.port
    netloc = hostname
    if parsed.username or parsed.password:
        raise ValueError("候选 URL 不得包含用户名或密码")
    if port is not None and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    query.sort()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(query), ""))


def normalize_language(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    aliases = {
        "zh-cn": "zh",
        "zh-tw": "zh",
        "zh-hans": "zh",
        "zh-hant": "zh",
        "en-us": "en",
        "en-gb": "en",
    }
    if normalized in {"zh", "en", "mixed", "und"}:
        return normalized
    if normalized in aliases:
        return aliases[normalized]
    cjk = len(re.findall(r"[\u3400-\u9fff]", value))
    latin = len(re.findall(r"[A-Za-z]", value))
    if cjk and latin:
        return "mixed"
    if cjk:
        return "zh"
    if latin:
        return "en"
    return "und"


def normalize_source_role(value: str | None) -> str:
    if value is None or not value.strip():
        return "discovery"
    normalized = value.strip().lower().replace("_", "-")
    normalized = _ROLE_ALIASES.get(normalized, normalized)
    if normalized not in _SOURCE_ROLES:
        raise ValueError(f"不支持的来源角色：{value}")
    return normalized


def normalize_event_type(value: str | None, title: str, content: str) -> str:
    if value:
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in _EVENT_ALIASES:
            return _EVENT_ALIASES[normalized]
    text = f"{title} {content}".lower()
    if any(word in text for word in ("price", "pricing", "价格", "收费", "套餐")):
        return "pricing_change"
    if any(word in text for word in ("security", "漏洞", "安全")):
        return "security"
    if any(word in text for word in ("funding", "融资", "投资")):
        return "funding"
    if any(word in text for word in ("research", "论文", "研究")):
        return "research"
    if any(word in text for word in ("release", "launch", "发布", "模型")):
        return "model_release"
    if any(word in text for word in ("update", "更新", "changelog")):
        return "product_update"
    return "other"


def normalize_entities(values: Iterable[str], title: str, content: str) -> list[str]:
    candidates = list(values)
    text = f"{title} {content}"
    for entity in _KNOWN_ENTITIES:
        if re.search(rf"(?<!\w){re.escape(entity)}(?!\w)", text, re.IGNORECASE):
            candidates.append(entity)
    return sorted({_clean_text(item).casefold() for item in candidates if item.strip()})


def build_event_key(
    *,
    canonical_url: str,
    entities: Iterable[str],
    title: str,
    published_at: datetime | None,
    content_hash: str,
) -> str:
    payload = {
        "url": canonical_url,
        "entities": sorted(set(entities)),
        "title": _stable_text(title),
        "date": published_at.date().isoformat() if published_at else None,
        "content_hash": content_hash,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return f"evt_{digest}"


def heat_score(candidate: Candidate) -> int:
    if candidate.heat_score is not None:
        return candidate.heat_score
    signals = candidate.heat_signals
    score = max(signals.get("score", 0.0), signals.get("descendants", 0.0))
    return max(0, min(100, round(score)))


def _content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(_stable_text(content).encode('utf-8')).hexdigest()}"


def _stable_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _clean_text(value: str) -> str:
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if not cleaned:
        raise ValueError("候选文本不能为空")
    return cleaned


def _as_utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("观察时间必须包含时区")
