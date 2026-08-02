from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mynews.domain.models import CollectionRequest
from mynews.sources.cc_switch import (
    CcSwitchPayloadError,
    CcSwitchReleaseAdapter,
    CcSwitchSourcePlugin,
)
from mynews.sources.protocol import ProbeContext, SourceContext

FIXTURE = Path(__file__).parent / "fixtures/cc-switch-v3.19.1.json"


class FixtureFetcher:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requested: list[tuple[str, float]] = []

    def get_json(self, url: str, *, timeout: float) -> object:
        self.requested.append((url, timeout))
        return self.payload


def fixture_payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_adapter_emits_one_candidate_for_each_new_feature() -> None:
    fetcher = FixtureFetcher([fixture_payload()])

    candidates = CcSwitchReleaseAdapter().collect(fetcher)

    assert [candidate.title_original for candidate in candidates] == [
        "CC Switch v3.19.1：官方厂商模型目录镜像（DeepSeek 首发）",
        "CC Switch v3.19.1：腾讯混元（TokenHub）Codex 预设",
        "CC Switch v3.19.1：8 个此前按 $0 记账的模型补上内置定价",
        "CC Switch v3.19.1：Grok Build 加入故障转移页签与环境变量冲突检测",
    ]
    assert all(
        str(candidate.url) == "https://ccswitch.io/zh/changelog/3.19.1"
        for candidate in candidates
    )
    assert candidates[0].published_at is not None
    assert "官方模型目录镜像" in (candidates[0].excerpt or "")


def test_adapter_uses_official_releases_api_with_timeout() -> None:
    fetcher = FixtureFetcher([fixture_payload()])

    CcSwitchReleaseAdapter().collect(fetcher, timeout=7.5)

    assert fetcher.requested == [
        ("https://api.github.com/repos/farion1231/cc-switch/releases", 7.5)
    ]


def test_adapter_rejects_non_official_release_url() -> None:
    payload = fixture_payload()
    payload["html_url"] = "https://example.com/releases/v3.19.1"

    with pytest.raises(CcSwitchPayloadError, match="官方 Release URL"):
        CcSwitchReleaseAdapter().collect(FixtureFetcher([payload]))


def test_adapter_skips_prerelease() -> None:
    payload = fixture_payload()
    payload["prerelease"] = True

    assert CcSwitchReleaseAdapter().collect(FixtureFetcher([payload])) == []


@pytest.mark.parametrize("field", ["draft", "prerelease"])
def test_adapter_rejects_missing_stability_flag(field: str) -> None:
    payload = fixture_payload()
    del payload[field]

    with pytest.raises(CcSwitchPayloadError, match="稳定 Release"):
        CcSwitchReleaseAdapter().collect(FixtureFetcher([payload]))


def test_adapter_preserves_unknown_publication_date_as_none() -> None:
    payload = fixture_payload()
    payload["published_at"] = None

    candidates = CcSwitchReleaseAdapter().collect(FixtureFetcher([payload]))

    assert candidates[0].published_at is None


def test_cc_switch_source_plugin_uses_fixture_through_public_seam() -> None:
    fetcher = FixtureFetcher([fixture_payload()])
    plugin = CcSwitchSourcePlugin()
    request = CollectionRequest.model_validate(
        {
            "from": "2026-08-01T00:00:00+00:00",
            "to": "2026-08-03T00:00:00+00:00",
        }
    )

    batch = plugin.collect(
        SourceContext(request=request, http=fetcher)
    )
    health = plugin.probe(ProbeContext(http=FixtureFetcher([fixture_payload()])))

    assert batch.source_id == "cc-switch"
    assert batch.fetched_count == 4
    assert health.health == "healthy"
    assert health.accepted_count == 4


@pytest.mark.parametrize(
    "field, value",
    [("tag_name", "v3.19"), ("published_at", "not-a-date"), ("body", None)],
)
def test_adapter_rejects_malformed_release_fields(field: str, value: object) -> None:
    payload = fixture_payload()
    payload[field] = value

    with pytest.raises(CcSwitchPayloadError, match="官方 Release|无法识别"):
        CcSwitchReleaseAdapter().collect(FixtureFetcher([payload]))
