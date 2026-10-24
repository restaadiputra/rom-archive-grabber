import json
from collections.abc import AsyncIterator
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any

import pytest
import respx

from rom_archive_grabber.adapters import http_client
from rom_archive_grabber.adapters.http_client import HttpxClient
from rom_archive_grabber.adapters.sources.archive_org import ArchiveOrgAdapter
from rom_archive_grabber.adapters.sources.curated import (
    CURATED_SOURCE,
    CuratedArchiveAdapter,
    CuratedCollection,
    load_curated,
)
from rom_archive_grabber.application.platforms import load_platforms
from rom_archive_grabber.domain.ports import HttpError

FIXTURES = Path(__file__).parents[2] / "fixtures"
METADATA = "https://archive.org/metadata/"
DATA = package_files("rom_archive_grabber.data")

CURATED_TOML = """
[[collection]]
identifier = "example-homebrew-jam"
platform = "gb"
note = "Example jam upload."
[collection.overrides]
"example-homebrew-jam-b" = "gbc"

[[collection]]
identifier = "example-homebrew-solo"
platform = "nes"
note = "Example single item."
"""


def _search(ids: list[str]) -> dict[str, object]:
    docs = [{"identifier": item, "title": item} for item in ids]
    return {"response": {"numFound": len(ids), "docs": docs}}


@respx.mock
async def test_curated_applies_overrides() -> None:
    item = json.loads((FIXTURES / "archive-metadata-item.json").read_text(encoding="utf-8"))
    collection = json.loads(
        (FIXTURES / "archive-metadata-collection.json").read_text(encoding="utf-8")
    )
    respx.get(METADATA + "example-homebrew-jam").respond(json=collection)
    respx.get("https://archive.org/advancedsearch.php").respond(
        json=_search(["example-homebrew-jam-a", "example-homebrew-jam-b"])
    )
    for item_id in ("example-homebrew-jam-a", "example-homebrew-jam-b", "example-homebrew-solo"):
        respx.get(METADATA + item_id).respond(json=item)
    client = HttpxClient("rom-archive-grabber/test")
    adapter = CuratedArchiveAdapter(
        ArchiveOrgAdapter(client, pause_seconds=0), load_curated(CURATED_TOML)
    )
    try:
        files = await adapter.list_files(CURATED_SOURCE)
    finally:
        await client.aclose()
    assert [(f.url.split("/")[4], f.platform, f.source_id) for f in files] == [
        ("example-homebrew-jam-a", "gb", "curated"),
        ("example-homebrew-jam-b", "gbc", "curated"),
        ("example-homebrew-solo", "nes", "curated"),
    ]
    assert await adapter.detect("https://archive.org/details/example-homebrew-jam") is False


def test_shipped_curated_file_parses_and_every_entry_has_note_and_known_platform() -> None:
    known = {
        p.key
        for p in load_platforms(DATA.joinpath("platforms.toml").read_text(encoding="utf-8")).all()
    }
    collections = load_curated(
        DATA.joinpath("curated-collections.toml").read_text(encoding="utf-8")
    )
    assert collections
    for collection in collections:
        assert collection.identifier.strip()
        assert collection.note.strip()
        assert collection.platform in known
        assert set(collection.overrides.values()) <= known
        assert all(isinstance(name, str) and name for name in collection.exclude)


def _item() -> Any:  # noqa: ANN401 - JSON fixtures have no fixed shape
    return json.loads((FIXTURES / "archive-metadata-item.json").read_text(encoding="utf-8"))


def _entry(identifier: str, exclude: frozenset[str] = frozenset()) -> CuratedCollection:
    return CuratedCollection(identifier, "gb", "Example.", {}, exclude)


@pytest.fixture
async def archive(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[ArchiveOrgAdapter]:
    async def no_backoff(seconds: float) -> None:
        return None

    monkeypatch.setattr(http_client, "_sleep", no_backoff)
    client = HttpxClient("rom-archive-grabber/test")
    yield ArchiveOrgAdapter(client, pause_seconds=0)
    await client.aclose()


@respx.mock
async def test_curated_skips_failing_entry(archive: ArchiveOrgAdapter) -> None:
    broken = respx.get(METADATA + "example-homebrew-gone").respond(503)
    respx.get(METADATA + "example-homebrew-solo").respond(json=_item())
    entries = [_entry("example-homebrew-gone"), _entry("example-homebrew-solo")]
    files = await CuratedArchiveAdapter(archive, entries).list_files(CURATED_SOURCE)
    assert broken.call_count > 1
    assert [f.url.split("/")[4] for f in files] == ["example-homebrew-solo"]


@respx.mock
async def test_curated_raises_when_all_entries_fail(archive: ArchiveOrgAdapter) -> None:
    respx.get(METADATA + "example-homebrew-gone").respond(503)
    respx.get(METADATA + "example-homebrew-down").respond(500)
    entries = [_entry("example-homebrew-gone"), _entry("example-homebrew-down")]
    with pytest.raises(HttpError) as raised:
        await CuratedArchiveAdapter(archive, entries).list_files(CURATED_SOURCE)
    assert raised.value.status == 500


@respx.mock
async def test_curated_excludes_listed_files(archive: ArchiveOrgAdapter) -> None:
    metadata = _item()
    metadata["files"].append({"name": "source.zip", "source": "original", "size": "9"})
    respx.get(METADATA + "example-homebrew-solo").respond(json=metadata)
    entries = [_entry("example-homebrew-solo", frozenset({"source.zip"}))]
    files = await CuratedArchiveAdapter(archive, entries).list_files(CURATED_SOURCE)
    assert [(f.file_name, f.title) for f in files] == [("My Game.gb", "Jam Entry Deluxe")]
