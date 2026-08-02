"""带有统一策略的、可注入的共享 HTTP 客户端。"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class HttpClientError(RuntimeError):
    """HTTP 边界的稳定错误。"""

    def __init__(
        self, code: str, message: str, *, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """对来源 Adapter 隐藏 urllib 实现的响应。"""

    status_code: int
    headers: Mapping[str, str]
    body: bytes
    from_cache: bool = False
    final_url: str | None = None

    def text(self, encoding: str | None = None) -> str:
        selected = encoding or _charset_from_headers(self.headers) or "utf-8"
        return self.body.decode(selected, errors="replace")


@dataclass(frozen=True, slots=True)
class HttpClientConfig:
    """共享 HTTP 客户端的运行策略。"""

    timeout: float = 10.0
    max_retries: int = 2
    user_agent: str = "mynews/0.1"
    concurrency_limit: int = 4
    retry_backoff_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("timeout 必须是正数")
        if self.max_retries < 0:
            raise ValueError("max_retries 不能为负数")
        if not self.user_agent.strip():
            raise ValueError("user_agent 不能为空")
        if self.concurrency_limit <= 0:
            raise ValueError("concurrency_limit 必须是正整数")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds 不能为负数")


class HttpTransport(Protocol):
    def __call__(
        self, url: str, *, headers: dict[str, str], timeout: float
    ) -> HttpResponse: ...


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse: ...

    def get_json(self, url: str, *, timeout: float | None = None) -> object: ...

    def get_text(self, url: str, *, timeout: float | None = None) -> str: ...


class SharedHttpClient:
    """所有内置来源共享的 HTTP 策略和短期验证缓存。"""

    def __init__(
        self,
        *,
        config: HttpClientConfig | None = None,
        transport: HttpTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or HttpClientConfig()
        self._transport = transport or _urlopen_transport
        self._sleep = sleep
        self._limiter = threading.BoundedSemaphore(self.config.concurrency_limit)
        self._cache: dict[str, HttpResponse] = {}
        self._cache_lock = threading.Lock()

    def get(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        request_headers = self._request_headers(url, headers)
        response = self._request_with_retries(
            url, headers=request_headers, timeout=timeout or self.config.timeout
        )
        cached = self._cached(url)
        if response.status_code == 304 and cached is not None:
            return HttpResponse(
                200,
                cached.headers,
                cached.body,
                from_cache=True,
                final_url=cached.final_url or url,
            )
        if 200 <= response.status_code < 300:
            response = response if response.final_url else HttpResponse(
                response.status_code,
                response.headers,
                response.body,
                response.from_cache,
                url,
            )
            self._save_cache(url, response)
            return response
        raise _http_status_error(response)

    def get_json(self, url: str, *, timeout: float | None = None) -> object:
        response = self.get(url, timeout=timeout)
        try:
            return json.loads(response.text())
        except json.JSONDecodeError as error:
            raise HttpClientError(
                "invalid_json", f"响应不是有效 JSON：{url}"
            ) from error

    def get_text(self, url: str, *, timeout: float | None = None) -> str:
        return self.get(url, timeout=timeout).text()

    def _request_headers(
        self, url: str, headers: Mapping[str, str] | None
    ) -> dict[str, str]:
        request_headers = {
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "User-Agent": self.config.user_agent,
        }
        request_headers.update(headers or {})
        cached = self._cached(url)
        if cached is not None:
            for name, request_name in (
                ("ETag", "If-None-Match"),
                ("Last-Modified", "If-Modified-Since"),
            ):
                value = _header(cached.headers, name)
                if value:
                    request_headers[request_name] = value
        return request_headers

    def _request_with_retries(
        self, url: str, *, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        for attempt in range(self.config.max_retries + 1):
            try:
                with self._limiter:
                    response = self._transport(url, headers=headers, timeout=timeout)
                if (
                    _is_retryable_status(response.status_code)
                    and attempt < self.config.max_retries
                ):
                    self._backoff(attempt)
                    continue
                return response
            except (TimeoutError, OSError, URLError) as error:
                if attempt >= self.config.max_retries:
                    raise HttpClientError(
                        "network_error", str(error) or "网络请求失败"
                    ) from error
                self._backoff(attempt)
        raise AssertionError("unreachable retry loop")

    def _backoff(self, attempt: int) -> None:
        delay = self.config.retry_backoff_seconds * (2**attempt)
        if delay:
            self._sleep(delay)

    def _cached(self, url: str) -> HttpResponse | None:
        with self._cache_lock:
            return self._cache.get(url)

    def _save_cache(self, url: str, response: HttpResponse) -> None:
        with self._cache_lock:
            self._cache[url] = response


def _urlopen_transport(
    url: str, *, headers: dict[str, str], timeout: float
) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return HttpResponse(
                status_code=response.status,
                headers=dict(response.headers.items()),
                body=response.read(),
                final_url=response.geturl(),
            )
    except HTTPError as error:
        return HttpResponse(
            status_code=error.code,
            headers=dict(error.headers.items()),
            body=error.read(),
        )


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _http_status_error(response: HttpResponse) -> HttpClientError:
    return HttpClientError(
        f"http_{response.status_code}",
        f"HTTP 请求失败：{response.status_code}",
        status_code=response.status_code,
    )


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    return next(
        (value for key, value in headers.items() if key.lower() == lowered), None
    )


def _charset_from_headers(headers: Mapping[str, str]) -> str | None:
    content_type = _header(headers, "Content-Type") or ""
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else None
