"""15 个无参数 entry-point 工厂及来源元数据。"""

from __future__ import annotations

from dataclasses import dataclass

from mynews.sources.feed import RssFeedPlugin
from mynews.sources.protocol import SourceMetadata, SourcePlugin


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    name: str
    feed_url: str
    role: str
    stability: str
    official_domains: tuple[str, ...]
    official_github_organizations: tuple[str, ...] = ()

    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id=self.source_id,
            name=self.name,
            role=self.role,
            homepage=self.feed_url,
            official_domains=self.official_domains,
            official_github_organizations=self.official_github_organizations,
            capabilities=("rss", "atom"),
            stability=self.stability,
            publication_time_semantics="feed-date",
        )

    def plugin(self) -> RssFeedPlugin:
        return RssFeedPlugin(self.metadata(), self.feed_url)


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        "openai-news",
        "OpenAI News",
        "https://openai.com/news/rss.xml",
        "primary",
        "stable-planned",
        ("openai.com",),
    ),
    SourceSpec(
        "google-blog",
        "Google Blog",
        "https://blog.google/rss/",
        "primary",
        "stable-planned",
        ("blog.google",),
    ),
    SourceSpec(
        "github-changelog",
        "GitHub Changelog",
        "https://github.blog/changelog/feed/",
        "primary",
        "stable-planned",
        ("github.blog",),
    ),
    SourceSpec(
        "hugging-face-blog",
        "Hugging Face Blog",
        "https://huggingface.co/blog/feed.xml",
        "primary",
        "stable-planned",
        ("huggingface.co",),
    ),
    SourceSpec(
        "google-deepmind",
        "Google DeepMind",
        "https://deepmind.google/blog/rss.xml",
        "primary",
        "stable-planned",
        ("deepmind.google",),
    ),
    SourceSpec(
        "nvidia-ai",
        "NVIDIA AI",
        "https://blogs.nvidia.com/blog/category/deep-learning/feed/",
        "primary",
        "stable-planned",
        ("blogs.nvidia.com",),
    ),
    SourceSpec(
        "aws-machine-learning",
        "AWS Machine Learning",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        "primary",
        "stable-planned",
        ("aws.amazon.com",),
    ),
    SourceSpec(
        "kimi-k2-releases",
        "Kimi K2 Releases",
        "https://github.com/MoonshotAI/Kimi-K2/releases.atom",
        "research",
        "stable-planned",
        ("github.com",),
        ("MoonshotAI",),
    ),
    SourceSpec(
        "glm-releases",
        "GLM Releases",
        "https://github.com/THUDM/GLM/releases.atom",
        "research",
        "stable-planned",
        ("github.com",),
        ("THUDM",),
    ),
    SourceSpec(
        "deepseek-status",
        "DeepSeek Status",
        "https://status.deepseek.com/history.atom",
        "incident",
        "experimental",
        ("status.deepseek.com",),
    ),
    SourceSpec(
        "openai-status",
        "OpenAI Status",
        "https://status.openai.com/history.rss",
        "incident",
        "experimental",
        ("status.openai.com",),
    ),
    SourceSpec(
        "anthropic-status",
        "Anthropic Status",
        "https://status.anthropic.com/history.rss",
        "incident",
        "experimental",
        ("status.anthropic.com",),
    ),
    SourceSpec(
        "github-status",
        "GitHub Status",
        "https://www.githubstatus.com/history.atom",
        "incident",
        "experimental",
        ("githubstatus.com",),
    ),
    SourceSpec(
        "techcrunch-ai",
        "TechCrunch AI",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "discovery",
        "experimental",
        ("techcrunch.com",),
    ),
    SourceSpec(
        "paperswithcode-daily",
        "Papers with Code Daily",
        "https://paperswithcode.co/feeds/daily.xml",
        "benchmark",
        "experimental",
        ("paperswithcode.co",),
    ),
)


def plugin_for(source_id: str) -> RssFeedPlugin:
    for spec in SOURCE_SPECS:
        if spec.source_id == source_id:
            return spec.plugin()
    raise KeyError(source_id)


def _factory(source_id: str) -> SourcePlugin:
    return plugin_for(source_id)


def openai_news() -> SourcePlugin:
    return _factory("openai-news")


def google_blog() -> SourcePlugin:
    return _factory("google-blog")


def github_changelog() -> SourcePlugin:
    return _factory("github-changelog")


def hugging_face_blog() -> SourcePlugin:
    return _factory("hugging-face-blog")


def google_deepmind() -> SourcePlugin:
    return _factory("google-deepmind")


def nvidia_ai() -> SourcePlugin:
    return _factory("nvidia-ai")


def aws_machine_learning() -> SourcePlugin:
    return _factory("aws-machine-learning")


def kimi_k2_releases() -> SourcePlugin:
    return _factory("kimi-k2-releases")


def glm_releases() -> SourcePlugin:
    return _factory("glm-releases")


def deepseek_status() -> SourcePlugin:
    return _factory("deepseek-status")


def openai_status() -> SourcePlugin:
    return _factory("openai-status")


def anthropic_status() -> SourcePlugin:
    return _factory("anthropic-status")


def github_status() -> SourcePlugin:
    return _factory("github-status")


def techcrunch_ai() -> SourcePlugin:
    return _factory("techcrunch-ai")


def paperswithcode_daily() -> SourcePlugin:
    return _factory("paperswithcode-daily")


FACTORIES: dict[str, object] = {
    "openai-news": openai_news,
    "google-blog": google_blog,
    "github-changelog": github_changelog,
    "hugging-face-blog": hugging_face_blog,
    "google-deepmind": google_deepmind,
    "nvidia-ai": nvidia_ai,
    "aws-machine-learning": aws_machine_learning,
    "kimi-k2-releases": kimi_k2_releases,
    "glm-releases": glm_releases,
    "deepseek-status": deepseek_status,
    "openai-status": openai_status,
    "anthropic-status": anthropic_status,
    "github-status": github_status,
    "techcrunch-ai": techcrunch_ai,
    "paperswithcode-daily": paperswithcode_daily,
}


__all__ = ["FACTORIES", "SOURCE_SPECS", "SourceSpec", "plugin_for"]
