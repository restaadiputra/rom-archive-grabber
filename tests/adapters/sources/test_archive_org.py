import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from rom_archive_grabber.adapters.http_client import HttpxClient
from rom_archive_grabber.adapters.sources.archive_org import ArchiveOrgAdapter
from rom_archive_grabber.domain.models import GameFile, SourceConfig

FIXTURES = Path(__file__).parents[2] / "fixtures"
METADATA = "https://archive.org/metadata/"
SEARCH = "https://archive.org/advancedsearch.php"
ITEM_ID = "example-homebrew-jam-entry"
JAM_ID = "example-homebrew-jam"


def _fixture(name: str) -> Any:  # noqa: ANN401 - JSON fixtures have no fixed shape
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _source(identifier: str) -> SourceConfig:
    return SourceConfig(
        "ia", "Archive", "archive-org", f"https://archive.org/details/{identifier}", "gb"
    )


@pytest.fixture
async def adapter() -> AsyncIterator[ArchiveOrgAdapter]:
    client = HttpxClient("rom-archive-grabber/test")
    yield ArchiveOrgAdapter(client, pause_seconds=0)
    await client.aclose()


async def test_detect_details_urls(adapter: ArchiveOrgAdapter) -> None:
    assert await adapter.detect("https://archive.org/details/abc") is True
    assert await adapter.detect("https://www.archive.org/details/abc") is True
    assert await adapter.detect("https://example.com/details/abc") is False
    assert await adapter.detect("https://archive.org/download/abc/x.gb") is False


@respx.mock
async def test_item_keeps_original_game_files_only(adapter: ArchiveOrgAdapter) -> None:
    respx.get(METADATA + ITEM_ID).respond(json=_fixture("archive-metadata-item.json"))
    files = await adapter.list_files(_source(ITEM_ID))
    assert [(f.file_name, f.size, f.platform, f.source_id) for f in files] == [
        ("My Game.gb", 32768, "gb", "ia")
    ]


@respx.mock
async def test_single_file_item_uses_item_title(adapter: ArchiveOrgAdapter) -> None:
    respx.get(METADATA + ITEM_ID).respond(json=_fixture("archive-metadata-item.json"))
    files = await adapter.list_files(_source(ITEM_ID))
    assert [f.title for f in files] == ["Jam Entry Deluxe"]


@respx.mock
async def test_multi_file_item_uses_clean_file_names(adapter: ArchiveOrgAdapter) -> None:
    metadata = _fixture("archive-metadata-item.json")
    metadata["files"].append({"name": "Second_Game.gbc", "source": "original"})
    respx.get(METADATA + ITEM_ID).respond(json=metadata)
    files = await adapter.list_item(ITEM_ID, "gbc", "ia")
    assert [(f.title, f.size, f.platform) for f in files] == [
        ("My Game", 32768, "gbc"),
        ("Second Game", None, "gbc"),
    ]


@respx.mock
async def test_download_url_is_quoted(adapter: ArchiveOrgAdapter) -> None:
    respx.get(METADATA + ITEM_ID).respond(json=_fixture("archive-metadata-item.json"))
    files = await adapter.list_files(_source(ITEM_ID))
    assert files[0].url == f"https://archive.org/download/{ITEM_ID}/My%20Game.gb"


def _search_page(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    assert params["q"] == f"collection:{JAM_ID}"
    assert params.get_list("fl[]") == ["identifier", "title"]
    assert (params["rows"], params["output"]) == ("500", "json")
    pages = _fixture("archive-search.json")
    return httpx.Response(200, json=pages[int(params["page"]) - 1])


@respx.mock
async def test_collection_pages_search_and_reports_progress(adapter: ArchiveOrgAdapter) -> None:
    respx.get(METADATA + JAM_ID).respond(json=_fixture("archive-metadata-collection.json"))
    search = respx.get(SEARCH).mock(side_effect=_search_page)
    for suffix in ("a", "b", "c"):
        respx.get(f"{METADATA}{JAM_ID}-{suffix}").respond(
            json=_fixture("archive-metadata-item.json")
        )
    calls: list[tuple[int, int, int | None]] = []

    def progress(files: list[GameFile], done: int, total: int | None) -> None:
        calls.append((len(files), done, total))

    files = await adapter.list_files(_source(JAM_ID), progress)
    assert search.call_count == 2
    assert calls == [(1, 1, 3), (2, 2, 3), (3, 3, 3)]
    assert [f.url.split("/")[4] for f in files] == [f"{JAM_ID}-a", f"{JAM_ID}-b", f"{JAM_ID}-c"]
