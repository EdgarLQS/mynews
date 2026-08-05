"""证据 URL、可见正文、日期和哈希的确定性检查。"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlsplit

_DATE_PATTERN = re.compile(
    r"(?:published_time|article:published_time)"
    r"[^>]*?(?:content|datetime)\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_TIME_PATTERN = re.compile(
    r"<time[^>]+datetime\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_JSON_DATE_PATTERN = re.compile(
    r"[\"']datePublished[\"']\s*:\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def visible_text(body: str) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(body)
        parser.close()
    except (AssertionError, ValueError):
        return body
    return " ".join(parser.parts)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def normalize_excerpt(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    without_format_chars = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Cf"
    )
    return normalize_text(without_format_chars)


def content_hash(body: str) -> str:
    normalized = normalize_text(visible_text(body))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def host(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold()


def is_search_url(value: str) -> bool:
    parsed = urlsplit(value)
    path_parts = parsed.path.casefold().strip("/").split("/")
    query_keys = {
        key.casefold()
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    }
    return "search" in path_parts or bool(
        query_keys & {"q", "query", "search"}
    )


def is_official_url(
    value: str,
    domains: Sequence[str],
    github_organizations: Sequence[str],
) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or not parsed.hostname
    ):
        return False
    hostname = parsed.hostname.casefold()
    if hostname == "github.com":
        organization = unquote(parsed.path).strip("/").split("/", 1)[0]
        allowed = {item.casefold() for item in github_organizations}
        return bool(organization) and organization.casefold() in allowed
    allowed_domains = {domain.casefold().strip(".") for domain in domains}
    return hostname in allowed_domains


def is_safe_candidate_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() in {"http", "https"}
        and not parsed.username
        and not parsed.password
        and port in {None, 80, 443}
        and bool(parsed.hostname)
    )


def body_dates(body: str) -> list[date]:
    values = (
        _DATE_PATTERN.findall(body)
        + _TIME_PATTERN.findall(body)
        + _JSON_DATE_PATTERN.findall(body)
    )
    result: list[date] = []
    for value in values:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            parsed = parsed.astimezone(UTC)
        result.append(parsed.date())
    return result


def date_matches(expected: datetime, body: str) -> bool:
    return expected.astimezone(UTC).date() in body_dates(body)
