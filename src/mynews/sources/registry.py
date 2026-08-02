"""内置来源注册表、选择和隔离执行。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Literal

from mynews.domain.models import SourceError
from mynews.infrastructure.clock import Clock
from mynews.infrastructure.http import HttpClient, HttpClientError, SharedHttpClient
from mynews.sources.builtins.feed import QwenFeedPlugin
from mynews.sources.builtins.hacker_news import HackerNewsPlugin
from mynews.sources.cc_switch import CcSwitchSourcePlugin
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceCollection,
    SourceContext,
    SourceHealth,
    SourcePlugin,
    SourcePluginError,
    ensure_unique_source_ids,
)

HealthStatus = Literal["healthy", "degraded", "blocked", "failed"]


class SourceRegistry:
    """显式 built-in 插件的稳定注册表。"""

    def __init__(
        self,
        plugins: Iterable[SourcePlugin],
        *,
        http: HttpClient | None = None,
        max_workers: int = 4,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers 必须是正整数")
        ordered = ensure_unique_source_ids(plugins)
        _validate_plugin_metadata(ordered)
        self._plugins = {plugin.metadata.source_id: plugin for plugin in ordered}
        self._ordered_ids = tuple(self._plugins)
        self._http = http or SharedHttpClient()
        self._max_workers = max_workers

    @property
    def source_ids(self) -> tuple[str, ...]:
        return self._ordered_ids

    @property
    def source_roles(self) -> dict[str, str]:
        return {
            source_id: self._plugins[source_id].metadata.role
            for source_id in self._ordered_ids
        }

    @property
    def http(self) -> HttpClient:
        return self._http

    def collect_all(
        self, context: SourceContext, source_ids: Sequence[str] | None = None
    ) -> SourceCollection:
        selected = self._selected(source_ids)
        if not selected:
            return SourceCollection((), ())
        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(selected))
        ) as pool:
            futures = [
                pool.submit(self._collect_one, plugin, context) for plugin in selected
            ]
            results = [future.result() for future in futures]
        candidates = tuple(
            candidate for batch, _ in results for candidate in batch.candidates
        )
        health = tuple(snapshot for _, snapshot in results)
        return SourceCollection(candidates, health)

    def probe(
        self, context: ProbeContext, source_ids: Sequence[str] | None = None
    ) -> tuple[SourceHealth, ...]:
        selected = self._selected(source_ids)
        if not selected:
            return ()
        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(selected))
        ) as pool:
            futures = [
                pool.submit(self._probe_one, plugin, context) for plugin in selected
            ]
            return tuple(future.result() for future in futures)

    def _selected(self, source_ids: Sequence[str] | None) -> tuple[SourcePlugin, ...]:
        ids = (
            self._ordered_ids
            if source_ids is None
            else tuple(dict.fromkeys(source_ids))
        )
        unknown = [source_id for source_id in ids if source_id not in self._plugins]
        if unknown:
            raise KeyError(f"未知来源：{', '.join(unknown)}")
        return tuple(self._plugins[source_id] for source_id in ids)

    def _collect_one(
        self, plugin: SourcePlugin, context: SourceContext
    ) -> tuple[SourceBatch, SourceHealth]:
        started = perf_counter()
        try:
            batch = plugin.collect(context)
            if batch.source_id != plugin.metadata.source_id:
                raise SourcePluginError(
                    "source_id_mismatch", "Adapter 返回了错误的来源 ID"
                )
            fetched_count = batch.fetched_count or len(batch.candidates)
            health = self._healthy(
                plugin, fetched_count, len(batch.candidates), started, context
            )
            return batch, health
        except Exception as error:
            return SourceBatch(plugin.metadata.source_id, ()), self._failed(
                plugin, error, started, context.clock
            )

    def _probe_one(self, plugin: SourcePlugin, context: ProbeContext) -> SourceHealth:
        started = perf_counter()
        try:
            health = plugin.probe(context)
            if health.source_id != plugin.metadata.source_id:
                raise SourcePluginError(
                    "source_id_mismatch", "Adapter 返回了错误的来源 ID"
                )
            return health.model_copy(
                update={
                    "checked_at": context.clock.now(),
                    "duration_ms": _duration(started),
                }
            )
        except Exception as error:
            return self._failed(plugin, error, started, context.clock)

    def _healthy(
        self,
        plugin: SourcePlugin,
        fetched_count: int,
        accepted_count: int,
        started: float,
        context: SourceContext,
    ) -> SourceHealth:
        return SourceHealth(
            source_id=plugin.metadata.source_id,
            role=plugin.metadata.role,
            health="healthy",
            fetched_count=fetched_count,
            accepted_count=accepted_count,
            duration_ms=_duration(started),
            checked_at=context.clock.now(),
        )

    def _failed(
        self, plugin: SourcePlugin, error: Exception, started: float, clock: Clock
    ) -> SourceHealth:
        code, message, health = _error_details(error)
        return SourceHealth(
            source_id=plugin.metadata.source_id,
            role=plugin.metadata.role,
            health=health,
            fetched_count=0,
            accepted_count=0,
            duration_ms=_duration(started),
            error=SourceError(code=code, message=message),
            checked_at=clock.now(),
        )


def built_in_registry(*, http: HttpClient | None = None) -> SourceRegistry:
    client = http or SharedHttpClient()
    return SourceRegistry(
        [CcSwitchSourcePlugin(), HackerNewsPlugin(), QwenFeedPlugin()],
        http=client,
    )


def _duration(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _error_details(
    error: Exception,
) -> tuple[str, str, HealthStatus]:
    if isinstance(error, SourcePluginError):
        status: HealthStatus = "failed"
        return error.code, error.message, status
    if isinstance(error, HttpClientError):
        status = "blocked" if error.status_code in {401, 403, 429} else "failed"
        return error.code, str(error), status
    status = "failed"
    return "plugin_error", str(error) or error.__class__.__name__, status


def _validate_plugin_metadata(plugins: tuple[SourcePlugin, ...]) -> None:
    for plugin in plugins:
        metadata = plugin.metadata
        if metadata.plugin_api_version != "1.0":
            raise ValueError(
                f"不支持的来源插件协议版本：{metadata.plugin_api_version}"
            )
        if not metadata.capabilities:
            raise ValueError(f"来源必须声明能力：{metadata.source_id}")
