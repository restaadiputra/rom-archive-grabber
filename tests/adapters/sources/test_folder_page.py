from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from rom_archive_grabber.adapters.sources.folder_page import FolderPageAdapter, parse_folder_page
from rom_archive_grabber.domain.models import SourceConfig
from rom_archive_grabber.domain.ports import HttpStream

BASE = "https://example.com/homebrew/gb/"
FIXTURE = Path(__file__).parents[2] / "fixtures" / "folder-page.html"


class FakeHttp:
    def __init__(self, pages: dict[str, tuple[str, str]]) -> None:
        self.pages = pages

    async def get_text(self, url: str) -> tuple[str, str]:
        return self.pages[url]

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:  # noqa: ANN401
        raise NotImplementedError

    def stream(self, url: str, start: int = 0) -> AbstractAsyncContextManager[HttpStream]:
        raise NotImplementedError


def _fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_fixture_keeps_only_game_files() -> None:
    assert parse_folder_page(_fixture(), BASE) == [
        "https://example.com/homebrew/gb/Tobu%20Girl.gb",
        "https://example.com/homebrew/gb/Another_Game.gb",
    ]


def test_parse_skips_non_http_fragment_and_unsafe_links() -> None:
    html = (
        '<a href="mailto:a@example.com">m</a><a href="javascript:void(0)">j</a>'
        '<a href="#top">t</a><a href="%2E%2E">dots</a><a href="x.gb#frag">f</a>'
        '<a href="https://example.org/mirror/m.gb">mirror</a>'
        '<a href="x.gb?dl=1">query</a>'
    )
    assert parse_folder_page(html, BASE) == [
        "https://example.com/homebrew/gb/x.gb",
        "https://example.org/mirror/m.gb",
    ]


async def test_detect_true_for_index_page() -> None:
    adapter = FolderPageAdapter(FakeHttp({BASE: (_fixture(), "text/html; charset=utf-8")}))
    assert await adapter.detect(BASE) is True


async def test_detect_true_for_index_title_without_game_links() -> None:
    html = "<title>index of /empty</title><a href='notes.txt'>n</a>"
    adapter = FolderPageAdapter(FakeHttp({BASE: (html, "text/html")}))
    assert await adapter.detect(BASE) is True


async def test_detect_false_for_plain_html_without_game_links() -> None:
    html = "<title>Welcome</title><a href='about.html'>About</a>"
    adapter = FolderPageAdapter(FakeHttp({BASE: (html, "text/html")}))
    assert await adapter.detect(BASE) is False


async def test_detect_false_for_non_html_content() -> None:
    adapter = FolderPageAdapter(FakeHttp({BASE: (_fixture(), "text/plain")}))
    assert await adapter.detect(BASE) is False


async def test_relative_links_resolve_when_location_lacks_trailing_slash() -> None:
    location = "https://example.com/homebrew/gb"
    adapter = FolderPageAdapter(FakeHttp({location: (_fixture(), "text/html")}))
    source = SourceConfig("f2", "Folder", "folder-page", location, "gb")
    files = await adapter.list_files(source)
    assert files[0].url == "https://example.com/homebrew/gb/Tobu%20Girl.gb"
    assert await adapter.detect(location) is True


async def test_list_files_titles_are_decoded() -> None:
    adapter = FolderPageAdapter(FakeHttp({BASE: (_fixture(), "text/html")}))
    source = SourceConfig("f1", "Folder", "folder-page", BASE, "gb")
    files = await adapter.list_files(source)
    assert [(f.title, f.file_name, f.platform, f.size) for f in files] == [
        ("Tobu Girl", "Tobu Girl.gb", "gb", None),
        ("Another Game", "Another_Game.gb", "gb", None),
    ]
    assert files[0].url == "https://example.com/homebrew/gb/Tobu%20Girl.gb"
