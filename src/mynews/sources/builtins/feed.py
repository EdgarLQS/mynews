"""内置 Qwen Feed；通用 RSS/Atom Adapter 位于公共 sources.feed seam。"""

from __future__ import annotations

from mynews.sources.feed import RssFeedPlugin
from mynews.sources.protocol import SourceMetadata

QWEN_FEED_URL = "https://qwenlm.github.io/blog/index.xml"


class QwenFeedPlugin(RssFeedPlugin):
    def __init__(self) -> None:
        super().__init__(
            SourceMetadata(
                source_id="qwen",
                name="Qwen",
                role="primary",
                homepage=QWEN_FEED_URL,
                official_domains=("qwenlm.github.io",),
                capabilities=("rss",),
                region="cn",
                publication_time_semantics="feed-date",
            ),
            QWEN_FEED_URL,
            allow_empty=False,
        )


__all__ = ["QWEN_FEED_URL", "QwenFeedPlugin", "RssFeedPlugin"]
