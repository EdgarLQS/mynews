from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import mynews.cli as cli
from mynews.application.collector import PipelineCollector
from mynews.domain.models import Candidate, CollectionRequest
from mynews.sources.external import ExternalPluginLoader
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceContext,
    SourceHealth,
    SourceMetadata,
)
from mynews.sources.registry import SourceRegistry
from mynews.storage.json_store import JsonNewsStore
from mynews.verification.fake import FakeVerifier

NOW = datetime(2026, 8, 9, 1, 0, tzinfo=UTC)
REQUEST = CollectionRequest.model_validate(
    {
        "from": "2026-08-08T00:00:00+00:00",
        "to": "2026-08-10T00:00:00+00:00",
    }
)


def metadata(
    source_id: str = "external-fixture",
    *,
    role: str = "primary",
    capabilities: tuple[str, ...] = ("fixture",),
) -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        name="External fixture",
        role=role,
        homepage="https://example.test/",
        official_domains=("example.test",),
        capabilities=capabilities,
    )


@dataclass
class FixturePlugin:
    metadata: SourceMetadata
    collect_error: Exception | None = None
    probe_error: Exception | None = None

    def collect(self, context: SourceContext) -> SourceBatch:
        if self.collect_error is not None:
            raise self.collect_error
        candidate = Candidate(
            source_id=self.metadata.source_id,
            title_original="External AI update",
            url="https://example.test/update",
            published_at=NOW,
        )
        return SourceBatch(self.metadata.source_id, (candidate,))

    def probe(self, context: ProbeContext) -> SourceHealth:
        if self.probe_error is not None:
            raise self.probe_error
        return SourceHealth(
            source_id=self.metadata.source_id,
            role=self.metadata.role,
            health="healthy",
            fetched_count=1,
            accepted_count=1,
            duration_ms=0,
            checked_at=NOW,
        )


@dataclass
class FakeEntryPoint:
    name: str
    value: str
    factory: object
    load_error: Exception | None = None

    def load(self) -> object:
        if self.load_error is not None:
            raise self.load_error
        return self.factory


def entry_point(
    name: str = "external-fixture",
    factory: object | None = None,
    *,
    load_error: Exception | None = None,
) -> FakeEntryPoint:
    return FakeEntryPoint(
        name,
        "fixture_module:factory",
        factory or (lambda: FixturePlugin(metadata())),
        load_error,
    )


def loader_for(*points: FakeEntryPoint) -> ExternalPluginLoader:
    return ExternalPluginLoader(points)  # type: ignore[arg-type]


def test_default_collect_and_probe_do_not_load_external_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingLoader:
        def __init__(self) -> None:
            raise AssertionError("默认路径不应创建外部 loader")

    monkeypatch.setattr(
        "mynews.application.runtime.ExternalPluginLoader", ExplodingLoader
    )
    registry = SourceRegistry([FixturePlugin(metadata())])

    assert cli.main(["probe"], registry=registry) == 0
    assert cli.main(["collect"], registry=registry) == 0


@pytest.mark.parametrize(
    "arguments",
    [
        ["plugin", "--help"],
        ["plugin", "list", "--help"],
        ["plugin", "probe", "--help"],
        ["probe", "--help"],
        ["collect", "--help"],
    ],
)
def test_external_plugin_help_is_chinese(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(arguments)

    assert raised.value.code == 0
    assert "用法：" in capsys.readouterr().out


def test_source_and_plugin_selection_are_mutually_exclusive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["collect", "--source", "hacker-news", "--plugin", "fixture"])

    assert raised.value.code == 2
    assert "不能与" in capsys.readouterr().err


def test_loader_lists_without_executing_factory() -> None:
    called = False

    def factory() -> FixturePlugin:
        nonlocal called
        called = True
        return FixturePlugin(metadata())

    report = loader_for(entry_point(factory=factory)).list_report()

    assert report["status"] == "complete"
    assert report["loaded"] is False
    assert called is False
    assert report["plugins"] == [
        {"id": "external-fixture", "value": "fixture_module:factory"}
    ]


def test_explicit_load_collect_probe_and_source_selection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loader = loader_for(entry_point())
    monkeypatch.setattr(
        "mynews.application.runtime.ExternalPluginLoader", lambda: loader
    )
    registry = SourceRegistry([FixturePlugin(metadata("built-in-fixture"))])

    probe_code = cli.main(["probe", "--plugin", "external-fixture"], registry=registry)
    probe = json.loads(capsys.readouterr().out)
    assert probe_code == 0
    assert probe["sources"][0]["source_id"] == "external-fixture"

    collect_code = cli.main(
        ["collect", "--plugin", "external-fixture"], registry=registry
    )
    collection = json.loads(capsys.readouterr().out)
    assert collect_code == 0
    assert collection["candidates"][0]["source_id"] == "external-fixture"
    assert collection["sources"][0]["source_id"] == "external-fixture"

    plugin_probe_code = cli.main(
        ["plugin", "probe", "--plugin", "external-fixture"], registry=registry
    )
    plugin_probe = json.loads(capsys.readouterr().out)
    assert plugin_probe_code == 0
    assert plugin_probe["plugins"][0]["id"] == "external-fixture"


def test_plugin_only_can_replace_a_configured_source_id(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    plugin = FixturePlugin(metadata("hacker-news"))
    loader = loader_for(entry_point(factory=lambda: plugin))
    monkeypatch.setattr(
        "mynews.application.runtime.ExternalPluginLoader", lambda: loader
    )
    registry = SourceRegistry([FixturePlugin(metadata("hacker-news"))])

    assert cli.main(["collect", "--plugin", "external-fixture"], registry=registry) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"][0]["source_id"] == "hacker-news"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_id", "bad id", "invalid_source_id"),
        ("plugin_api_version", "0.9", "protocol_incompatible"),
        ("role", "unknown", "invalid_role"),
        ("official_domains", ("https://example.test",), "invalid_official_domains"),
        ("capabilities", (), "empty_capabilities"),
    ],
)
def test_loader_rejects_invalid_metadata(field: str, value: object, code: str) -> None:
    changed = replace(metadata(), **{field: value})
    report = loader_for(entry_point(factory=lambda: FixturePlugin(changed))).load(
        ["external-fixture"]
    )

    assert report.status == "failed"
    assert report.issues[0].code == code


def test_loader_rejects_protocol_object_factory_and_duplicate_ids() -> None:
    bad_protocol = loader_for(entry_point(factory=lambda: object())).load(
        ["external-fixture"]
    )
    bad_factory = loader_for(
        entry_point(factory=lambda argument: FixturePlugin(metadata()))
    ).load(["external-fixture"])
    duplicate = loader_for(
        entry_point("one", factory=lambda: FixturePlugin(metadata("same"))),
        entry_point("two", factory=lambda: FixturePlugin(metadata("same"))),
    ).load(["one", "two"])
    conflict = loader_for(entry_point()).load(
        ["external-fixture"], occupied_source_ids=("external-fixture",)
    )

    assert bad_protocol.issues[0].code == "invalid_plugin_protocol"
    assert bad_factory.issues[0].code == "factory_must_be_no_argument"
    assert duplicate.issues[0].code == "duplicate_source_id"
    assert conflict.issues[0].code == "builtin_source_id_conflict"


def test_loader_reports_import_and_factory_runtime_failures() -> None:
    imported = loader_for(
        entry_point(load_error=ImportError("missing fixture module"))
    ).load(["external-fixture"])
    runtime = loader_for(
        entry_point(factory=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    ).load(["external-fixture"])

    assert imported.issues[0].code == "factory_import_failed"
    assert runtime.issues[0].code == "factory_runtime_error"


def test_source_runtime_failure_is_structured() -> None:
    plugin = FixturePlugin(metadata(), collect_error=RuntimeError("collect boom"))
    result = SourceRegistry([plugin]).collect_all(
        SourceContext(request=REQUEST, http=object())
    )

    assert result.health[0].health == "failed"
    assert result.health[0].error is not None
    assert result.health[0].error.code == "plugin_error"


class IncrementingClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 8, 9, tzinfo=UTC)

    def now(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


def test_failed_external_collect_does_not_change_store_state(tmp_path: Path) -> None:
    store = JsonNewsStore(tmp_path)
    success = PipelineCollector(
        SourceRegistry([FixturePlugin(metadata("good"))]),
        store,
        clock=IncrementingClock(),
        verifier=FakeVerifier(),
    ).collect(REQUEST)
    tracked = {
        path: path.read_bytes()
        for path in (
            tmp_path / "output/latest.json",
            tmp_path / "state/dedup.json",
            tmp_path / "state/pending_verifications.json",
        )
        if path.exists()
    }

    failed = PipelineCollector(
        SourceRegistry(
            [FixturePlugin(metadata("bad"), collect_error=RuntimeError("boom"))]
        ),
        store,
        clock=IncrementingClock(datetime(2026, 8, 9, 0, 1, tzinfo=UTC)),
        verifier=FakeVerifier(),
    ).collect(REQUEST)

    assert success.status == "complete"
    assert failed.status == "failed"
    assert failed.sources[0].error is not None
    assert {path: path.read_bytes() for path in tracked} == tracked
    assert len(list((tmp_path / "output/runs").glob("*.json"))) == 2


def test_real_entry_point_distribution_is_discovered_in_isolated_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = tmp_path / "temporary_external_plugin.py"
    module.write_text(
        """
from dataclasses import replace
from mynews.sources.builtins.hacker_news import HackerNewsPlugin
from mynews.sources.protocol import (
    ProbeContext,
    SourceBatch,
    SourceHealth,
    SourceMetadata,
)

class TemporaryPlugin:
    def __init__(self):
        self._delegate = HackerNewsPlugin()
        self.metadata = replace(
            self._delegate.metadata,
            source_id="temporary-hacker-news",
            name="Temporary Hacker News",
            capabilities=("fixture",),
        )

    def collect(self, context):
        batch = self._delegate.collect(context)
        candidates = tuple(
            item.model_copy(update={"source_id": self.metadata.source_id})
            for item in batch.candidates
        )
        return SourceBatch(self.metadata.source_id, candidates, batch.fetched_count)

    def probe(self, context):
        return self._delegate.probe(context).model_copy(
            update={"source_id": self.metadata.source_id}
        )

def factory():
    return TemporaryPlugin()
""",
        encoding="utf-8",
    )
    dist_info = tmp_path / "temporary_external_plugin-0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: temporary-external-plugin\nVersion: 0.1\n",
        encoding="utf-8",
    )
    (dist_info / "entry_points.txt").write_text(
        "[mynews.source_plugins]\ntemporary-hn = temporary_external_plugin:factory\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    loader = ExternalPluginLoader()
    discovered = loader.discover()
    report = loader.load(["temporary-hn"])

    assert any(point.name == "temporary-hn" for point in discovered)
    assert report.status == "complete"
    assert report.loaded[0].plugin.metadata.source_id == "temporary-hacker-news"
