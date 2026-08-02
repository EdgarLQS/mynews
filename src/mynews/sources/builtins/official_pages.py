"""官方更新页、价格页和实验公开元数据页 Adapter。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from mynews.domain.models import Candidate, PriceSnapshot
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceBlockedError,
    SourceContext,
    SourceHealth,
    SourceMetadata,
    SourcePluginError,
)

OPENAI_NEWS_URL = "https://developers.openai.com/api/docs/models"
ANTHROPIC_NEWS_URL = "https://www.anthropic.com/news"
GOOGLE_GEMINI_URL = "https://ai.google.dev/gemini-api/docs/changelog"
DEEPSEEK_UPDATES_URL = "https://api-docs.deepseek.com/zh-cn/updates"
TRAE_CHANGELOG_URL = "https://www.trae.cn/changelog"
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/models"
DEEPSEEK_PRICING_URL = (
    "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
)
ZHIHU_HOT_URL = "https://www.zhihu.com/hot"
BLOOMBERG_AI_URL = "https://www.bloomberg.com/technology"


@dataclass(slots=True)
class _RawEntry:
    title: str = ""
    url: str = ""
    text: list[str] | None = None
    published_at: datetime | None = None


class _PublicHtmlParser(HTMLParser):
    """只读取可见 HTML 文本、文章卡片和公开 time 元素。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[_RawEntry] = []
        self.document_title = ""
        self.document_text: list[str] = []
        self._current: _RawEntry | None = None
        self._article_depth = 0
        self._capture_tag: str | None = None
        self._capture_text: list[str] = []
        self._ignored_depth = 0
        self.first_published_at: datetime | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "article" and self._current is None:
            self._current = _RawEntry(text=[])
            self._article_depth = 1
        elif tag == "article" and self._current is not None:
            self._article_depth += 1
        if tag == "a" and self._current is not None and not self._current.url:
            self._current.url = attributes.get("href") or ""
        if tag in {"h1", "h2", "h3", "h4"} and self._current is not None:
            self._start_capture(tag)
        if tag == "time":
            value = attributes.get("datetime")
            if value:
                parsed = _parse_datetime(value)
                if self._current is not None:
                    self._current.published_at = parsed
                if self.first_published_at is None:
                    self.first_published_at = parsed
            if self._current is not None:
                self._start_capture(tag)
        if tag == "title":
            self._start_capture(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if self._capture_tag == tag:
            captured = _clean_text(" ".join(self._capture_text))
            if tag == "title":
                self.document_title = captured
            elif self._current is not None and tag in {"h1", "h2", "h3", "h4"}:
                if not self._current.title:
                    self._current.title = captured
            self._capture_tag = None
            self._capture_text = []
        if tag == "article" and self._current is not None:
            if self._article_depth == 1:
                self.entries.append(self._current)
                self._current = None
                self._article_depth = 0
            else:
                self._article_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = _clean_text(data)
        if not cleaned:
            return
        self.document_text.append(cleaned)
        if self._current is not None and self._current.text is not None:
            self._current.text.append(cleaned)
        if self._capture_tag is not None:
            self._capture_text.append(cleaned)

    def _start_capture(self, tag: str) -> None:
        if self._capture_tag is None:
            self._capture_tag = tag
            self._capture_text = []


class OfficialHtmlPlugin:
    """解析公开文章卡片，不抓取登录后或付费墙内的正文。"""

    def __init__(
        self,
        metadata: SourceMetadata,
        page_url: str,
        *,
        event_type: str = "product_update",
        allow_page_fallback: bool = True,
    ) -> None:
        self.metadata = metadata
        self.page_url = page_url
        self._event_type = event_type
        self._allow_page_fallback = allow_page_fallback

    def collect(self, context: SourceContext) -> SourceBatch:
        entries = self._parse(context.http.get_text(self.page_url))
        candidates = tuple(
            candidate
            for candidate in self._candidates(entries, context.limit)
            if _in_requested_range(candidate, context)
        )
        return SourceBatch(
            self.metadata.source_id,
            candidates,
            fetched_count=min(len(entries), context.limit),
        )

    def probe(self, context: ProbeContext) -> SourceHealth:
        entries = self._parse(context.http.get_text(self.page_url))
        selected = self._candidates(entries, context.limit)
        return SourceHealth.healthy_result(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            fetched_count=len(entries),
            accepted_count=len(selected),
            checked_at=context.clock.now(),
        )

    def _parse(self, payload: str) -> list[_RawEntry]:
        parser = _PublicHtmlParser()
        try:
            parser.feed(payload)
            parser.close()
        except (ValueError, AssertionError) as error:
            raise SourcePluginError(
                "invalid_html", "官方页面不是可解析 HTML"
            ) from error
        entries = [
            entry
            for entry in parser.entries
            if entry.title or entry.url
            if _is_official_url(
                urljoin(self.page_url, entry.url or self.page_url),
                self.metadata.official_domains,
            )
        ]
        if entries:
            return entries
        if not self._allow_page_fallback:
            raise SourceBlockedError(
                "public_metadata_unavailable", "页面没有可公开读取的元数据卡片"
            )
        title = parser.document_title or self.metadata.name
        excerpt = _clean_text(" ".join(parser.document_text))
        if not excerpt:
            raise SourcePluginError("empty_page", "官方页面没有可读取的公开文本")
        return [
            _RawEntry(
                title=title,
                url=self.page_url,
                text=[excerpt],
                published_at=parser.first_published_at,
            )
        ]

    def _candidates(
        self, entries: list[_RawEntry], limit: int
    ) -> list[Candidate]:
        candidates: list[Candidate] = []
        for entry in entries[:limit]:
            url = urljoin(self.page_url, entry.url or self.page_url)
            if not _is_official_url(url, self.metadata.official_domains):
                raise SourcePluginError(
                    "unofficial_entry", "页面条目链接不属于官方域名"
                )
            title = _clean_text(entry.title or self.metadata.name)
            excerpt = _clean_text(" ".join(entry.text or [])) or title
            candidates.append(
                Candidate.model_validate(
                    {
                        "source_id": self.metadata.source_id,
                        "title_original": title,
                        "url": url,
                        "published_at": entry.published_at,
                        "excerpt": excerpt[:1000],
                        "heat_signals": {"official_page": 1.0},
                        "event_type": self._event_type,
                        "source_role": self.metadata.role,
                    }
                )
            )
        return candidates


class OfficialPricingPlugin:
    """将官方价格页转成待持久化的规范化快照。"""

    def __init__(self, metadata: SourceMetadata, page_url: str) -> None:
        self.metadata = metadata
        self.page_url = page_url

    def collect(self, context: SourceContext) -> SourceBatch:
        payload = context.http.get_text(self.page_url)
        snapshot = _snapshot(
            self.metadata.source_id,
            self.page_url,
            payload,
            context.clock.now(),
        )
        return SourceBatch(
            self.metadata.source_id,
            (),
            fetched_count=1,
            price_snapshot=snapshot,
        )

    def probe(self, context: ProbeContext) -> SourceHealth:
        payload = context.http.get_text(self.page_url)
        _snapshot(self.metadata.source_id, self.page_url, payload, context.clock.now())
        return SourceHealth.healthy_result(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            fetched_count=1,
            accepted_count=1,
            checked_at=context.clock.now(),
        )


class OpenAiNewsPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata("openai", "OpenAI", "primary", "openai.com", ("html", "updates")),
            OPENAI_NEWS_URL,
            event_type="product_update",
        )


class AnthropicNewsPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "anthropic",
                "Anthropic",
                "primary",
                "anthropic.com",
                ("html", "updates"),
            ),
            ANTHROPIC_NEWS_URL,
            event_type="product_update",
        )


class GoogleGeminiPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "google-gemini",
                "Google Gemini",
                "primary",
                "ai.google.dev",
                ("html", "updates"),
            ),
            GOOGLE_GEMINI_URL,
            event_type="product_update",
        )


class DeepSeekUpdatesPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "deepseek",
                "DeepSeek",
                "primary",
                "api-docs.deepseek.com",
                ("html", "updates"),
            ),
            DEEPSEEK_UPDATES_URL,
            event_type="model_release",
        )


class TraeChangelogPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata("trae", "TRAE", "primary", "trae.cn", ("html", "changelog")),
            TRAE_CHANGELOG_URL,
            event_type="product_update",
        )


class OpenAiPricingPlugin(OfficialPricingPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "openai-pricing",
                "OpenAI API Pricing",
                "monitor",
                "openai.com",
                ("html", "pricing", "snapshot"),
            ),
            OPENAI_PRICING_URL,
        )


class DeepSeekPricingPlugin(OfficialPricingPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "deepseek-pricing",
                "DeepSeek 模型与价格",
                "monitor",
                "api-docs.deepseek.com",
                ("html", "pricing", "snapshot"),
            ),
            DEEPSEEK_PRICING_URL,
        )


class ZhihuHotPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "zhihu-hot",
                "知乎热榜",
                "discovery",
                "zhihu.com",
                ("html", "public-metadata"),
                stability="experimental",
                region="cn",
            ),
            ZHIHU_HOT_URL,
            allow_page_fallback=False,
        )


class BloombergAiPlugin(OfficialHtmlPlugin):
    def __init__(self) -> None:
        super().__init__(
            _metadata(
                "bloomberg-ai",
                "Bloomberg AI/Technology",
                "discovery",
                "bloomberg.com",
                ("html", "public-metadata"),
                stability="experimental",
            ),
            BLOOMBERG_AI_URL,
            allow_page_fallback=False,
        )


def _metadata(
    source_id: str,
    name: str,
    role: str,
    domain: str,
    capabilities: tuple[str, ...],
    *,
    stability: str = "adapter-planned",
    region: str = "global",
) -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        name=name,
        role=role,
        homepage="https://" + domain,
        official_domains=(domain,),
        capabilities=capabilities,
        stability=stability,
        region=region,
        publication_time_semantics="page-provided-or-null",
    )


def _snapshot(
    source_id: str, url: str, payload: str, observed_at: datetime
) -> PriceSnapshot:
    parser = _PublicHtmlParser()
    parser.feed(payload)
    normalized = _normalize_snapshot_text(parser.document_text)
    if not normalized:
        raise SourcePluginError("empty_price_page", "官方价格页没有公开价格文本")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return PriceSnapshot(
        source_id=source_id,
        url=url,
        observed_at=observed_at,
        published_at=parser.first_published_at,
        content_hash=f"sha256:{digest}",
        values={"text": normalized, "line_count": len(normalized.split("\n"))},
    )


def _normalize_snapshot_text(values: list[str]) -> str:
    lines = [_clean_text(value) for value in values]
    lines = [line for line in lines if line]
    return "\n".join(dict.fromkeys(lines))


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError as error:
            raise SourcePluginError("invalid_date", "官方页面日期无法解析") from error
        parsed = datetime.combine(parsed_date, time.min, tzinfo=UTC)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _is_official_url(url: str, domains: tuple[str, ...]) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    return any(
        parsed.hostname == domain or parsed.hostname.endswith("." + domain)
        for domain in domains
    )


def _in_requested_range(candidate: Candidate, context: SourceContext) -> bool:
    return candidate.published_at is None or (
        context.request.from_ <= candidate.published_at < context.request.to
    )
