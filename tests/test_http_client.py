from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from mynews.infrastructure.http import (
    HttpClientConfig,
    HttpResponse,
    SharedHttpClient,
)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def __call__(
        self, url: str, *, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        self.calls.append((url, headers, timeout))
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def response(body: bytes, *, etag: str | None = None) -> HttpResponse:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if etag is not None:
        headers["ETag"] = etag
    return HttpResponse(status_code=200, headers=headers, body=body)


def test_shared_client_uses_timeout_user_agent_and_cache_validators() -> None:
    transport = FakeTransport(
        [
            response(b'{"ok": true}', etag='"v1"'),
            HttpResponse(status_code=304, headers={}, body=b""),
        ]
    )
    client = SharedHttpClient(
        transport=transport,
        config=HttpClientConfig(timeout=4.5, user_agent="mynews-test/1"),
    )

    assert client.get_json("https://example.test/data") == {"ok": True}
    cached = client.get("https://example.test/data")

    assert cached.body == b'{"ok": true}'
    assert cached.from_cache is True
    assert transport.calls[0][1]["User-Agent"] == "mynews-test/1"
    assert transport.calls[0][2] == 4.5
    assert transport.calls[1][1]["If-None-Match"] == '"v1"'
    assert transport.calls[1][1]["Cache-Control"] == "no-cache"


def test_shared_client_retries_only_within_configured_limit() -> None:
    transport = FakeTransport(
        [TimeoutError("first"), TimeoutError("second"), response(b"ok")]
    )
    sleeps: list[float] = []
    client = SharedHttpClient(
        transport=transport,
        config=HttpClientConfig(max_retries=2),
        sleep=sleeps.append,
    )

    assert client.get("https://example.test/retry").body == b"ok"
    assert len(transport.calls) == 3
    assert len(sleeps) == 2


def test_shared_client_limits_concurrent_transport_calls() -> None:
    active = 0
    maximum = 0

    def transport(
        url: str, *, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        sleep(0.02)
        active -= 1
        return response(url.encode())

    client = SharedHttpClient(
        transport=transport,
        config=HttpClientConfig(concurrency_limit=2),
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda index: client.get(f"https://example.test/{index}"), range(4)
            )
        )

    assert [result.body for result in results] == [
        b"https://example.test/0",
        b"https://example.test/1",
        b"https://example.test/2",
        b"https://example.test/3",
    ]
    assert maximum == 2


@pytest.mark.parametrize("value", [0, -1])
def test_http_config_rejects_non_positive_limits(value: int) -> None:
    with pytest.raises(ValueError):
        HttpClientConfig(concurrency_limit=value)
