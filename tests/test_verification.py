from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from mynews.domain.models import Candidate, Evidence, EvidenceValidation
from mynews.domain.normalization import Normalizer
from mynews.infrastructure.http import HttpResponse
from mynews.verification.codex import (
    CodexVerifier,
    SubprocessCodexRunner,
    _content_hash,
    _prompt,
)
from mynews.verification.fake import FakeVerifier
from mynews.verification.protocol import (
    EvidenceVerifier,
    VerificationConfig,
    VerificationDecision,
    VerificationTarget,
)

NOW = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
BODY = (
    '<html><head><meta property="article:published_time" '
    'content="2026-08-02T01:00:00Z"></head>'
    '<body>Official launch of Model 5.</body></html>'
)


class FakeHttp:
    def __init__(self, responses: Mapping[str, HttpResponse | BaseException]) -> None:
        self.responses = dict(responses)
        self.calls: list[tuple[str, float | None]] = []

    def get(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        del headers
        self.calls.append((url, timeout))
        result = self.responses[url]
        if isinstance(result, BaseException):
            raise result
        return result


class StaticCodex:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.prompts: list[str] = []
        self.calls: list[tuple[str, float, str]] = []

    def run(
        self,
        prompt: str,
        *,
        model: str,
        timeout: float,
        reasoning_effort: str,
    ) -> str:
        self.prompts.append(prompt)
        self.calls.append((model, timeout, reasoning_effort))
        return self.outputs.pop(0)


def response(body: str, *, final_url: str | None = None) -> HttpResponse:
    return HttpResponse(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        body=body.encode(),
        final_url=final_url,
    )


def target(
    *,
    url: str,
    source_role: str = "discovery",
    official_domains: tuple[str, ...] = ("official.example",),
    excerpt: str = "Official launch of Model 5.",
    relevance_score: int | None = None,
) -> VerificationTarget:
    candidate = Candidate(
        source_id="fixture",
        title_original="Model 5 launches",
        url=url,
        published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
        excerpt=excerpt,
        relevance_score=relevance_score,
    )
    item = Normalizer(source_roles={"fixture": source_role}).normalize(
        [candidate], observed_at=NOW
    )[0]
    return VerificationTarget(
        item=item,
        source_id="fixture",
        publisher="Official Publisher",
        excerpt=excerpt,
        official_domains=official_domains,
        source_role=source_role,
    )


def body_hash(body: str) -> str:
    return _content_hash(body)


def test_codex_revalidation_ignores_dynamic_html_shell() -> None:
    body = (
        '<html><head><meta property="article:published_time" '
        'content="2026-08-02T01:00:00Z"><script>'
        'window.requestId = "two";</script></head>'
        "<body><h1>Official launch of Model 5.</h1></body></html>"
    )
    stable_body = (
        '<html><head><meta property="article:published_time" '
        'content="2026-08-02T01:00:00Z"></head>'
        "<body><h1>Official launch of Model 5.</h1></body></html>"
    )
    candidate = target(url="https://news.example/story")
    payload = json.loads(suggestion(candidate.item.event_key))
    payload["suggestions"][0]["content_hash"] = body_hash(stable_body)
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(body)}),
        runner=StaticCodex([json.dumps(payload)]),
    )

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "verified"


def test_codex_verification_matches_timezone_aware_page_date() -> None:
    body = (
        '<meta property="article:published_time" '
        'content="2026-08-02T00:30:00+08:00">'
        "Official launch of Model 5."
    )
    candidate = target(url="https://news.example/story")
    payload = json.loads(suggestion(candidate.item.event_key))
    payload["suggestions"][0]["published_at"] = "2026-08-02T00:30:00+08:00"
    payload["suggestions"][0]["content_hash"] = body_hash(body)
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(body)}),
        runner=StaticCodex([json.dumps(payload)]),
    )

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "verified"


def test_codex_suggestion_can_fall_back_to_candidate_date() -> None:
    candidate = target(url="https://news.example/story")
    payload = json.loads(suggestion(candidate.item.event_key))
    payload["suggestions"][0]["published_at"] = None
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(BODY)}),
        runner=StaticCodex([json.dumps(payload)]),
    )

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "verified"


def suggestion(item_id: str, *, url: str = "https://official.example/news") -> str:
    return json.dumps(
        {
            "suggestions": [
                {
                    "item_id": item_id,
                    "url": url,
                    "publisher": "Official Publisher",
                    "title": "Model 5 launches",
                    "published_at": "2026-08-02T01:00:00Z",
                    "excerpt": "Official launch of Model 5.",
                    "content_hash": body_hash(BODY),
                }
            ]
        }
    )


def test_fake_verifier_is_a_public_evidence_verifier_seam() -> None:
    evidence = Evidence(
        url="https://official.example/news",
        publisher="Official Publisher",
        title="Model 5 launches",
        published_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
        retrieved_at=NOW,
        excerpt="Official launch of Model 5.",
        content_hash=body_hash(BODY),
        validation=EvidenceValidation(
            reachable=True, official_domain=True, excerpt_matched=True
        ),
    )
    item_target = target(url="https://news.example/story")
    verifier = FakeVerifier(
        {
            item_target.item.event_key: VerificationDecision.verified(
                item_target.item.event_key, evidence
            )
        }
    )

    result = verifier.verify([item_target], config=VerificationConfig())

    assert isinstance(verifier, EvidenceVerifier)
    assert result[0].status == "verified"


def test_codex_verifier_directly_verifies_an_official_source() -> None:
    official = target(
        url="https://official.example/news",
        source_role="primary",
    )
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(BODY)})
    )

    result = verifier.verify([official], config=VerificationConfig())

    assert result[0].status == "verified"
    assert result[0].reason == "official_source"
    assert result[0].evidence is not None
    assert result[0].evidence.validation.reachable is True


def test_codex_suggestion_is_rechecked_before_it_can_verify() -> None:
    candidate = target(url="https://news.example/story")
    runner = StaticCodex([suggestion(candidate.item.event_key)])
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(BODY)}), runner=runner
    )

    result = verifier.verify(
        [candidate],
        config=VerificationConfig(model="test-model", budget=1, batch_size=1),
    )

    assert result[0].status == "verified"
    assert runner.calls == [("test-model", 30.0, "medium")]


def test_verification_config_defaults_to_medium_and_rejects_unknown_effort() -> None:
    assert VerificationConfig().reasoning_effort == "medium"

    with pytest.raises(ValueError, match="推理强度无效"):
        VerificationConfig(reasoning_effort="turbo")  # type: ignore[arg-type]


def test_codex_excerpt_matches_visible_text_across_html_elements() -> None:
    body = (
        '<meta property="article:published_time" content="2026-08-02T01:00:00Z">'
        "<article><h1>Official\u200b launch</h1><p>of Model 5.</p></article>"
    )
    candidate = target(url="https://news.example/story")
    payload = json.loads(suggestion(candidate.item.event_key))
    payload["suggestions"][0]["content_hash"] = body_hash(body)
    runner = StaticCodex([json.dumps(payload)])
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(body)}), runner=runner
    )

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "verified"


def test_codex_prompt_requires_verbatim_evidence_excerpt() -> None:
    candidate = target(url="https://news.example/story")

    prompt = _prompt(
        [
            VerificationTarget(
                item=candidate.item,
                source_id="fixture",
                publisher="Official Publisher",
                excerpt=candidate.excerpt,
                official_domains=("official.example",),
                source_role="discovery",
            )
        ]
    )

    assert "逐字连续的原文片段" in prompt
    assert "不能改写" in prompt
    assert "allowed_official_domains" in prompt
    assert "不能自行扩大白名单" in prompt


@pytest.mark.parametrize(
    "suggested_url, final_url, expected_reason",
    [
        (
            "https://media.example/story",
            None,
            "evidence_not_official",
        ),
        (
            "https://official.example/search?q=model",
            None,
            "search_summary_not_evidence",
        ),
        (
            "https://official.example/news",
            "https://official.example.evil/news",
            "redirect_not_official",
        ),
    ],
)
def test_untrusted_urls_never_become_verified(
    suggested_url: str,
    final_url: str | None,
    expected_reason: str,
) -> None:
    candidate = target(url="https://news.example/story")
    runner = StaticCodex([suggestion(candidate.item.event_key, url=suggested_url)])
    responses: dict[str, HttpResponse] = {}
    if suggested_url == "https://official.example/news":
        responses[suggested_url] = response(BODY, final_url=final_url)
    verifier = CodexVerifier(FakeHttp(responses), runner=runner)

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "unverified"
    assert result[0].reason == expected_reason


def test_github_evidence_requires_the_declared_organization() -> None:
    candidate = target(
        url="https://news.example/story",
        official_domains=("github.com",),
    )
    candidate = replace(
        candidate, official_github_organizations=("trusted-org",)
    )
    runner = StaticCodex(
        [suggestion(candidate.item.event_key, url="https://github.com/evil/repo")]
    )
    verifier = CodexVerifier(FakeHttp({}), runner=runner)

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "unverified"
    assert result[0].reason == "evidence_not_official"


@pytest.mark.parametrize(
    "body, expected_reason",
    [
        ("<html>no matching excerpt</html>", "evidence_excerpt_mismatch"),
        (BODY, "evidence_content_hash_mismatch"),
        (
            '<meta property="article:published_time" content="2026-08-03T01:00:00Z">'
            "Official launch of Model 5.",
            "evidence_date_mismatch",
        ),
        (
            "<p>2026-08-02 is an unrelated date.</p>Official launch of Model 5.",
            "evidence_date_mismatch",
        ),
    ],
)
def test_revalidation_failures_remain_unverified(
    body: str, expected_reason: str
) -> None:
    candidate = target(url="https://news.example/story")
    payload = json.loads(suggestion(candidate.item.event_key))
    if expected_reason == "evidence_content_hash_mismatch":
        payload["suggestions"][0]["content_hash"] = "sha256:wrong"
    runner = StaticCodex([json.dumps(payload)])
    verifier = CodexVerifier(
        FakeHttp({"https://official.example/news": response(body)}), runner=runner
    )

    result = verifier.verify(
        [candidate], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].status == "unverified"
    assert result[0].reason == expected_reason


def test_bad_codex_json_and_budget_are_recorded_without_upgrade() -> None:
    candidates = [
        target(url=f"https://news.example/story-{index}") for index in range(3)
    ]
    runner = StaticCodex(["not json"])
    verifier = CodexVerifier(FakeHttp({}), runner=runner)

    result = verifier.verify(
        candidates,
        config=VerificationConfig(budget=2, batch_size=2),
    )

    assert [item.status for item in result] == ["unverified"] * 3
    assert result[0].reason == "invalid_codex_json"
    assert result[1].reason == "invalid_codex_json"
    assert result[2].reason == "verification_budget_exhausted"


def test_budget_selects_highest_ranked_candidates_first() -> None:
    low = target(url="https://news.example/low", relevance_score=10)
    high = target(url="https://news.example/high", relevance_score=90)
    runner = StaticCodex(['{"suggestions": []}'])
    verifier = CodexVerifier(FakeHttp({}), runner=runner)

    result = verifier.verify(
        [low, high], config=VerificationConfig(budget=1, batch_size=1)
    )

    assert result[0].reason == "verification_budget_exhausted"
    assert result[1].reason == "codex_no_suggestion"


def test_codex_runner_is_read_only_ephemeral_and_never_uses_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: float,
        check: bool,
        shell: bool,
        cwd: str,
        reasoning_effort: str = "medium",
    ) -> SimpleNamespace:
        del reasoning_effort
        captured.update(
            {
                "command": command,
                "input": input,
                "text": text,
                "capture_output": capture_output,
                "timeout": timeout,
                "check": check,
                "shell": shell,
                "cwd": cwd,
            }
        )
        output_path = Path(
            command[command.index("--output-last-message") + 1]
        )
        output_path.write_text('{"suggestions":[]}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("mynews.verification.codex.subprocess.run", run)

    output = SubprocessCodexRunner("codex-test").run(
        "structured prompt", model="test-model", timeout=2.5
    )

    command = captured["command"]
    assert output == '{"suggestions":[]}'
    assert command[:2] == ["codex-test", "exec"]
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("-c") + 1] == (
        'model_reasoning_effort="medium"'
    )
    assert captured["shell"] is False
    assert captured["timeout"] == 2.5


def test_codex_runner_emits_strict_output_schema_for_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: float,
        check: bool,
        shell: bool,
        cwd: str,
        reasoning_effort: str = "medium",
    ) -> SimpleNamespace:
        del input, text, capture_output, timeout, check, shell, cwd, reasoning_effort
        schema_path = Path(command[command.index("--output-schema") + 1])
        captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        output_path = Path(
            command[command.index("--output-last-message") + 1]
        )
        output_path.write_text('{"suggestions":[]}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("mynews.verification.codex.subprocess.run", run)

    SubprocessCodexRunner("codex-test").run(
        "structured prompt", model="test-model", timeout=2.5
    )

    schema = captured["schema"]
    assert isinstance(schema, dict)
    suggestion_schema = schema["$defs"]["CodexSuggestion"]
    assert set(suggestion_schema["required"]) == set(
        suggestion_schema["properties"]
    )
    assert {"published_at", "content_hash"} <= set(
        suggestion_schema["required"]
    )
