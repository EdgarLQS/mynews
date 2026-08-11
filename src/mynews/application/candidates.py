"""Candidate Contract v1、稳定去重和 editorial 导出辅助。"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mynews.application.output_safety import OutputSafetyError, ensure_safe_output
from mynews.domain.models import Candidate
from mynews.domain.normalization import normalize_url

CANDIDATE_SCHEMA_VERSION = "1.0"
MAX_CANDIDATES = 500
MAX_SUMMARY_CHARS = 2000
MAX_CONTENT_CHARS = 6000
MAX_EVIDENCE = 20
MAX_PUBLICATION_HISTORY = 50
SOURCE_ROLES = {
    "primary",
    "discovery",
    "benchmark",
    "research",
    "incident",
    "monitor",
    "manual",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+", re.IGNORECASE)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "new",
    "of",
    "on",
    "that",
    "the",
    "their",
    "to",
    "with",
    "update",
    "updates",
}
_SOURCE_FAMILY_ALIASES = {
    "hn": "hacker-news",
    "hackernews": "hacker-news",
    "hacker-news-api": "hacker-news",
    "hacker-news": "hacker-news",
    "techcrunch-ai": "techcrunch",
    "techcrunch": "techcrunch",
}


def source_family(source_id: str, url: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source_id.casefold()).strip("-")
    if slug in _SOURCE_FAMILY_ALIASES:
        return _SOURCE_FAMILY_ALIASES[slug]
    host = (urlsplit(url).hostname or "").casefold()
    if host in {"news.ycombinator.com", "hnrss.org", "hacker-news.firebaseio.com"}:
        return "hacker-news"
    if host.endswith("techcrunch.com"):
        return "techcrunch"
    return slug or "unknown"


def candidate_contract_schema() -> dict[str, Any]:
    """Return the public Draft 2020-12 compatible schema."""
    url = {
        "type": "string",
        "minLength": 8,
        "maxLength": 2048,
        "pattern": r"^https?://",
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://mynews.local/schemas/candidate-contract-v1.json",
        "title": "mynews Candidate Contract v1",
        "type": "object",
        "additionalProperties": False,
        "required": ["schemaVersion", "date", "generatedAt", "candidates"],
        "properties": {
            "schemaVersion": {"const": CANDIDATE_SCHEMA_VERSION},
            "date": {"type": "string", "format": "date"},
            "generatedAt": {"type": "string", "format": "date-time"},
            "stats": {"$ref": "#/$defs/stats"},
            "candidates": {
                "type": "array",
                "maxItems": MAX_CANDIDATES,
                "items": {"$ref": "#/$defs/candidate"},
            },
        },
        "$defs": {
            "url": url,
            "stats": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "candidateCount",
                    "databaseMatchedCount",
                    "fallbackCount",
                    "matchRate",
                ],
                "properties": {
                    "candidateCount": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": MAX_CANDIDATES,
                    },
                    "databaseMatchedCount": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": MAX_CANDIDATES,
                    },
                    "fallbackCount": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": MAX_CANDIDATES,
                    },
                    "matchRate": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "match": {
                "type": "object",
                "additionalProperties": False,
                "required": ["method", "databaseMatched"],
                "properties": {
                    "method": {"enum": ["dedup_key", "normalized_url", "fallback"]},
                    "databaseMatched": {"type": "boolean"},
                },
            },
            "evidence": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "url"],
                "properties": {
                    "type": {
                        "enum": [
                            "source",
                            "official",
                            "paper",
                            "repository",
                            "secondary",
                        ]
                    },
                    "url": {"$ref": "#/$defs/url"},
                    "title": {"type": "string", "maxLength": 500},
                    "source": {"type": "string", "maxLength": 200},
                    "publishedAt": {"type": "string", "format": "date-time"},
                },
            },
            "publication": {
                "type": "object",
                "additionalProperties": False,
                "required": ["date", "platform", "url", "publishedAt"],
                "properties": {
                    "date": {"type": "string", "format": "date"},
                    "platform": {"type": "string", "maxLength": 100},
                    "url": {"$ref": "#/$defs/url"},
                    "publishedAt": {"type": "string", "format": "date-time"},
                },
            },
            "candidate": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "url", "source", "firstSeenAt"],
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": 200},
                    "candidateRef": {
                        "type": "string",
                        "minLength": 3,
                        "maxLength": 420,
                    },
                    "idScope": {"enum": ["global", "batch"]},
                    "match": {"$ref": "#/$defs/match"},
                    "title": {"type": "string", "minLength": 1, "maxLength": 500},
                    "url": {"$ref": "#/$defs/url"},
                    "source": {"type": "string", "minLength": 1, "maxLength": 200},
                    "sourceRole": {"enum": sorted(SOURCE_ROLES)},
                    "publishedAt": {"type": "string", "format": "date-time"},
                    "firstSeenAt": {"type": "string", "format": "date-time"},
                    "firstSeenPrecision": {"enum": ["date", "datetime"]},
                    "duplicateGroupId": {"type": "string", "maxLength": 200},
                    "multiSources": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 50,
                        "uniqueItems": True,
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                        },
                    },
                    "repeat_count": {"type": "integer", "minimum": 1},
                    "authors": {
                        "type": "array",
                        "maxItems": 20,
                        "uniqueItems": True,
                        "items": {"type": "string", "maxLength": 200},
                    },
                    "sourceHeat": {"type": "number", "minimum": 0},
                    "comments": {"type": "integer", "minimum": 0},
                    "language": {"type": "string", "maxLength": 35},
                    "summaryOriginal": {
                        "type": "string",
                        "maxLength": MAX_SUMMARY_CHARS,
                    },
                    "contentExcerpt": {
                        "type": "string",
                        "maxLength": MAX_CONTENT_CHARS,
                    },
                    "tags": {
                        "type": "array",
                        "maxItems": 30,
                        "uniqueItems": True,
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 100,
                        },
                    },
                    "publicationHistory": {
                        "type": "array",
                        "maxItems": MAX_PUBLICATION_HISTORY,
                        "items": {"$ref": "#/$defs/publication"},
                    },
                    "evidence": {
                        "type": "array",
                        "maxItems": MAX_EVIDENCE,
                        "items": {"$ref": "#/$defs/evidence"},
                    },
                    "externalLinks": {
                        "type": "array",
                        "maxItems": 5,
                        "uniqueItems": True,
                        "items": {"$ref": "#/$defs/url"},
                    },
                    "imageCandidates": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {"$ref": "#/$defs/imageCandidate"},
                    },
                    "extractionStatus": {
                        "enum": ["complete", "partial", "failed"]
                    },
                },
            },
            "imageCandidate": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url", "type"],
                "properties": {
                    "url": {"$ref": "#/$defs/url"},
                    "type": {"type": "string", "maxLength": 100},
                },
            },
        },
    }


def validate_candidate_payload(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    required = ("schemaVersion", "date", "generatedAt", "candidates")
    for field in required:
        if field not in payload:
            issues.append({"field": field, "message": "字段必填"})
    if payload.get("schemaVersion") != CANDIDATE_SCHEMA_VERSION:
        issues.append(
            {"field": "schemaVersion", "message": "只支持 Candidate Contract v1"}
        )
    business_date = str(payload.get("date", ""))
    if not _DATE_RE.fullmatch(business_date):
        issues.append({"field": "date", "message": "日期必须使用 YYYY-MM-DD"})
    generated = _parse_datetime(payload.get("generatedAt"))
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        issues.append({"field": "candidates", "message": "必须是数组"})
        return issues
    if len(candidates) > MAX_CANDIDATES:
        issues.append({"field": "candidates", "message": "候选最多 500 条"})
    seen_urls: set[str] = set()
    for index, item in enumerate(candidates):
        path = f"candidates.{index}"
        if not isinstance(item, Mapping):
            issues.append({"field": path, "message": "必须是对象"})
            continue
        for field in ("id", "title", "url", "source", "firstSeenAt"):
            if not item.get(field):
                issues.append({"field": f"{path}.{field}", "message": "字段必填"})
        if (
            item.get("sourceRole") is not None
            and item.get("sourceRole") not in SOURCE_ROLES
        ):
            issues.append({"field": f"{path}.sourceRole", "message": "来源角色无效"})
        url = str(item.get("url", ""))
        try:
            normalized = normalize_url(url)
        except ValueError:
            normalized = ""
            issues.append({"field": f"{path}.url", "message": "必须是 HTTPS URL"})
        if normalized in seen_urls:
            issues.append({"field": f"{path}.url", "message": "规范化 URL 重复"})
        if normalized:
            seen_urls.add(normalized)
        first_seen = _parse_datetime(item.get("firstSeenAt"))
        if generated and first_seen and first_seen > generated:
            issues.append(
                {
                    "field": f"{path}.firstSeenAt",
                    "message": "firstSeenAt 不能晚于 generatedAt",
                }
            )
        if (
            item.get("firstSeenPrecision") == "date"
            and first_seen
            and first_seen.time() != datetime.min.time()
        ):
            issues.append(
                {
                    "field": f"{path}.firstSeenPrecision",
                    "message": "date 精度必须是 UTC 零点",
                }
            )
        if (
            "repeat_count" in item
            and (
                not isinstance(item.get("repeat_count"), int)
            or isinstance(item.get("repeat_count"), bool)
            or item.get("repeat_count", 0) < 1
            )
        ):
            issues.append({"field": f"{path}.repeat_count", "message": "必须是正整数"})
    return sorted(issues, key=lambda item: (item["field"], item["message"]))


def read_candidate_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("候选文件必须是 JSON 对象")
    if payload.get("schemaVersion") == CANDIDATE_SCHEMA_VERSION:
        return payload
    if "categories" in payload:
        return _read_legacy_payload(payload)
    raise ValueError("候选文件缺少受支持的 schemaVersion")


def _read_legacy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    business_date = str(payload.get("date", ""))
    generated = str(
        payload.get("generated_at")
        or payload.get("generatedAt")
        or f"{business_date}T00:00:00Z"
    )
    items: list[dict[str, Any]] = []
    categories = payload.get("categories", {})
    for category in sorted(
        categories.values(), key=lambda value: int(value.get("order", 0))
    ):
        for item in category.get("items", []):
            item = dict(item)
            first_seen = str(item.get("first_seen") or generated)
            legacy_id = str(item.get("id") or f"candidate-{len(items) + 1:03d}")
            item_payload = {
                "id": legacy_id,
                "candidateRef": f"{business_date}:{legacy_id}",
                "idScope": "batch",
                "match": {"method": "fallback", "databaseMatched": False},
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "source": str(
                    item.get("source_name") or item.get("source_id") or "unknown"
                ),
                "sourceRole": str(item.get("source_role") or "primary"),
                "publishedAt": item.get("published_at"),
                "firstSeenAt": first_seen,
                "firstSeenPrecision": "date"
                if _DATE_RE.fullmatch(first_seen)
                else "datetime",
                "duplicateGroupId": str(
                    item.get("cluster_id") or item.get("id") or "legacy"
                ),
                "multiSources": list(
                    item.get("multi_sources") or [item.get("source_id") or "unknown"]
                ),
                "repeat_count": max(1, int(item.get("repeat_count") or 1)),
                "summaryOriginal": item.get("summary"),
                "contentExcerpt": item.get("content_excerpt"),
                "authors": list(item.get("authors") or []),
                "tags": list(item.get("tags") or []),
                "evidence": [{"type": "source", "url": str(item.get("url"))}],
            }
            if item_payload["publishedAt"] is None:
                item_payload.pop("publishedAt")
            items.append(item_payload)
    result = {
        "schemaVersion": CANDIDATE_SCHEMA_VERSION,
        "date": business_date,
        "generatedAt": generated,
        "stats": {
            "candidateCount": len(items),
            "databaseMatchedCount": 0,
            "fallbackCount": len(items),
            "matchRate": 0.0,
        },
        "candidates": items,
    }
    issues = validate_candidate_payload(result)
    if issues:
        raise ValueError("旧候选文件兼容读取失败")
    return result


def build_candidate_payload(
    candidates: Sequence[Candidate],
    *,
    business_date: str,
    generated_at: datetime,
    observations: Mapping[str, list[dict[str, str]]],
    database_matches: Mapping[str, str] | None = None,
    publication_history: Mapping[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    groups = _group_candidates(candidates)
    exported: list[dict[str, Any]] = []
    matched_count = 0
    match_index = database_matches or {}
    for index, group in enumerate(groups[:MAX_CANDIDATES], start=1):
        item = group[0]
        url = normalize_url(str(item.url))
        match_id = match_index.get(url)
        if match_id:
            matched_count += 1
        first_seen, precision, repeat_count = _observation_summary(
            group, observations, business_date, generated_at
        )
        families = _ordered_unique(
            source_family(str(candidate.source_id), str(candidate.url))
            for candidate in group
        )
        urls = sorted({normalize_url(str(candidate.url)) for candidate in group})
        group_id = _group_id(business_date, urls, len(families) > 1)
        candidate_id = match_id or f"candidate-{index:03d}"
        entry: dict[str, Any] = {
            "id": candidate_id,
            "candidateRef": f"{business_date}:candidate-{index:03d}",
            "idScope": "global" if match_id else "batch",
            "match": {
                "method": "normalized_url" if match_id else "fallback",
                "databaseMatched": bool(match_id),
            },
            "title": _clip(str(item.title_original), 500),
            "url": str(item.url),
            "source": _source_name(item),
            "sourceRole": str(item.source_role or "discovery"),
            "firstSeenAt": first_seen,
            "firstSeenPrecision": precision,
            "duplicateGroupId": group_id,
            "multiSources": families,
            "repeat_count": repeat_count,
            "evidence": _evidence(group),
        }
        external_links = _external_links(group)
        if external_links:
            entry["externalLinks"] = external_links
        image_candidates = _image_candidates(group)
        if image_candidates:
            entry["imageCandidates"] = image_candidates
        entry["extractionStatus"] = _extraction_status(group)
        published_at = _format_datetime(item.published_at)
        if published_at:
            entry["publishedAt"] = published_at
        if item.authors:
            entry["authors"] = _ordered_unique(
                _clip(str(value), 200) for value in item.authors
            )[:20]
        heat = _heat(item)
        if heat is not None:
            entry["sourceHeat"] = heat
        comments = _comments(item)
        if comments is not None:
            entry["comments"] = comments
        if item.language:
            entry["language"] = str(item.language)[:35]
        if item.excerpt:
            entry["summaryOriginal"] = _clip(
                _clean_text(item.excerpt), MAX_SUMMARY_CHARS
            )
        if item.content:
            entry["contentExcerpt"] = _clip(
                _clean_text(item.content), MAX_CONTENT_CHARS
            )
        if item.tags:
            entry["tags"] = _ordered_unique(
                _clip(str(value), 100) for value in item.tags
            )[:30]
        history = (publication_history or {}).get(group_id) or (
            publication_history or {}
        ).get(candidate_id)
        if history:
            entry["publicationHistory"] = history[-MAX_PUBLICATION_HISTORY:]
        exported.append(entry)
    payload = {
        "schemaVersion": CANDIDATE_SCHEMA_VERSION,
        "date": business_date,
        "generatedAt": _format_datetime(generated_at),
        "stats": {
            "candidateCount": len(exported),
            "databaseMatchedCount": matched_count,
            "fallbackCount": len(exported) - matched_count,
            "matchRate": round(matched_count / len(exported), 6) if exported else 0.0,
        },
        "candidates": exported,
    }
    issues = validate_candidate_payload(payload)
    if issues:
        raise ValueError(
            "候选契约校验失败：" + "; ".join(issue["field"] for issue in issues[:3])
        )
    try:
        ensure_safe_output(payload, root="candidate")
    except OutputSafetyError as error:
        raise ValueError("候选隐私门禁失败：" + error.field_path) from error
    return payload


def _group_candidates(candidates: Sequence[Candidate]) -> list[list[Candidate]]:
    groups: list[list[Candidate]] = []
    url_index: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        url = normalize_url(str(candidate.url))
        direct = url_index.get(url)
        if direct is not None:
            direct.append(candidate)
            continue
        matched: list[Candidate] | None = None
        for group in groups:
            if _same_family(candidate, group[0]) and _normalize_title(
                candidate.title_original
            ) == _normalize_title(group[0].title_original):
                matched = group
                break
            if _cross_source_match(candidate, group):
                matched = group
                break
        if matched is None:
            matched = []
            groups.append(matched)
        matched.append(candidate)
        url_index[url] = matched
    return groups


def _same_family(left: Candidate, right: Candidate) -> bool:
    return source_family(str(left.source_id), str(left.url)) == source_family(
        str(right.source_id), str(right.url)
    )


def _cross_source_match(candidate: Candidate, group: Sequence[Candidate]) -> bool:
    if any(_same_family(candidate, existing) for existing in group):
        return False
    left = _title_tokens(candidate.title_original)
    right = _title_tokens(group[0].title_original)
    return (
        len(left) >= 4
        and len(right) >= 4
        and len(left & right) >= 4
        and len(left & right) / min(len(left), len(right)) >= 0.6
    )


def _observation_summary(
    group: Sequence[Candidate],
    observations: Mapping[str, list[dict[str, str]]],
    business_date: str,
    generated_at: datetime,
) -> tuple[str, str, int]:
    facts: list[tuple[datetime, str]] = []
    repeat_count = 0
    for candidate in group:
        key = normalize_url(str(candidate.url))
        rows = observations.get(key, [])
        repeat_count += len(rows)
        for row in rows:
            parsed = _parse_datetime(row.get("observedAt"))
            if parsed:
                facts.append((parsed, "datetime"))
            elif _DATE_RE.fullmatch(str(row.get("observedAt", ""))):
                facts.append(
                    (
                        _parse_datetime(f"{row['observedAt']}T00:00:00Z")
                        or generated_at,
                        "date",
                    )
                )
    if not facts:
        facts = [
            (_parse_datetime(f"{business_date}T00:00:00Z") or generated_at, "date")
        ]
        repeat_count = max(1, len(group))
    facts.sort(key=lambda value: value[0])
    first_seen, precision = facts[0]
    if first_seen > generated_at:
        first_seen = generated_at
    if precision == "date":
        first_seen = first_seen.replace(hour=0, minute=0, second=0, microsecond=0)
        if first_seen > generated_at:
            first_seen = generated_at.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        _format_datetime(first_seen) or _format_datetime(generated_at) or "",
        precision,
        max(1, repeat_count),
    )


def _group_id(business_date: str, urls: Sequence[str], event: bool) -> str:
    digest = hashlib.sha256("\n".join(urls).encode("utf-8")).hexdigest()[:16]
    return f"event-{business_date}-{digest}" if event else f"cluster-{digest}"


def _evidence(group: Sequence[Candidate]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for candidate in group:
        for url in [
            str(candidate.url),
            *(str(value) for value in candidate.external_links),
        ]:
            if not url.startswith("https://") or any(
                item["url"] == url for item in result
            ):
                continue
            result.append(
                {"type": "source", "url": url, "source": str(candidate.source_id)}
            )
            if len(result) >= MAX_EVIDENCE:
                return result
    return result


def _external_links(group: Sequence[Candidate]) -> list[str]:
    links: list[str] = []
    for candidate in group:
        for raw_url in candidate.external_links:
            try:
                normalized = normalize_url(str(raw_url))
            except ValueError:
                continue
            if normalized not in links:
                links.append(normalized)
            if len(links) == 5:
                return links
    return links


def _image_candidates(group: Sequence[Candidate]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for candidate in group:
        for image in candidate.image_candidates:
            try:
                normalized = normalize_url(str(image.get("url", "")))
            except ValueError:
                continue
            value = {
                "url": normalized,
                "type": str(image.get("type") or "image/unknown")[:100],
            }
            if value not in images:
                images.append(value)
            if len(images) == 3:
                return images
    return images


def _extraction_status(group: Sequence[Candidate]) -> str:
    statuses = {candidate.extraction_status for candidate in group}
    if "failed" in statuses:
        return "failed"
    if "partial" in statuses:
        return "partial"
    return "complete"


def _source_name(candidate: Candidate) -> str:
    return str(candidate.source_name or candidate.source_id)


def _heat(candidate: Candidate) -> float | None:
    values = [value for value in candidate.heat_signals.values() if value >= 0]
    return max(values) if values else None


def _comments(candidate: Candidate) -> int | None:
    for key in ("comments", "descendants", "num_comments", "comment_count"):
        value = candidate.heat_signals.get(key)
        if value is not None and value >= 0:
            return int(value)
    return None


def _title_tokens(value: str) -> set[str]:
    return {
        token
        for token in (
            re.sub(r"[^a-z0-9\u3400-\u9fff]", "", item.casefold())
            for item in _TOKEN_RE.findall(html.unescape(value))
        )
        if len(token) >= 2 and token not in _STOP_WORDS
    }


def _normalize_title(value: str) -> str:
    return " ".join(sorted(_title_tokens(value)))


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


__all__ = [
    "CANDIDATE_SCHEMA_VERSION",
    "MAX_CANDIDATES",
    "build_candidate_payload",
    "candidate_contract_schema",
    "read_candidate_payload",
    "source_family",
    "validate_candidate_payload",
]
