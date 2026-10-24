from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from rom_archive_grabber.adapters.sources.link_list import LinkListAdapter, parse_link_list
from rom_archive_grabber.domain.models import SourceConfig
from rom_archive_grabber.domain.ports import HttpStream


class FakeHttp:
    def __init__(self, pages: dict[str, tuple[str, str]]) -> None:
        self.pages = pages

    async def get_text(self, url: str) -> tuple[str, str]:
        return self.pages[url]

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:  # noqa: ANN401
        raise NotImplementedError

    def stream(self, url: str, start: int = 0) -> AbstractAsyncContextManager[HttpStream]:
        raise NotImplementedError


def test_parse_link_list_titles_comments_blank_lines() -> None:
    text = (
        "# my list\n\nChrono Homebrew | https://example.com/a/chrono.zip\n"
        "https://example.com/b/Tobu_Girl.gb\n"
    )
    assert parse_link_list(text, None) == [
        ("Chrono Homebrew", "https://example.com/a/chrono.zip"),
        ("Tobu Girl", "https://example.com/b/Tobu_Girl.gb"),
    ]


def test_relative_links_resolve_against_base() -> None:
    text = "Rel | sub/game.gb\n/root/other.gb\n"
    assert parse_link_list(text, "https://example.com/lists/games.txt") == [
        ("Rel", "https://example.com/lists/sub/game.gb"),
        ("other", "https://example.com/root/other.gb"),
    ]


def test_relative_links_without_base_are_skipped() -> None:
    assert parse_link_list("sub/game.gb\n", None) == []


async def test_link_list_detects_local_file(tmp_path: Path) -> None:
    path = tmp_path / "list.txt"
    path.write_text("Game | https://example.com/g.gb\n", encoding="utf-8")
    adapter = LinkListAdapter(FakeHttp({}))
    assert await adapter.detect(str(path)) is True
    assert await adapter.detect(str(tmp_path / "missing.txt")) is False
    empty = tmp_path / "empty.txt"
    empty.write_text("# nothing\n", encoding="utf-8")
    assert await adapter.detect(str(empty)) is False


async def test_link_list_detects_urls_by_type_or_extension() -> None:
    body = "https://example.com/g.gb\n"
    adapter = LinkListAdapter(
        FakeHttp(
            {
                "https://example.com/plain": (body, "text/plain; charset=utf-8"),
                "https://example.com/list.txt": (body, "application/octet-stream"),
                "https://example.com/page": (body, "text/html"),
            }
        )
    )
    assert await adapter.detect("https://example.com/plain") is True
    assert await adapter.detect("https://example.com/list.txt") is True
    assert await adapter.detect("https://example.com/page") is False


async def test_link_list_list_files_sets_platform_and_names() -> None:
    body = (
        "Chrono Homebrew | https://example.com/a/chrono%20demo.zip\n"
        "https://example.com/b/Tobu_Girl.gb\n"
    )
    adapter = LinkListAdapter(FakeHttp({"https://example.com/list.txt": (body, "text/plain")}))
    source = SourceConfig("s1", "Mine", "link-list", "https://example.com/list.txt", "gb")
    files = await adapter.list_files(source)
    assert [(f.title, f.file_name, f.platform, f.size, f.source_id) for f in files] == [
        ("Chrono Homebrew", "chrono demo.zip", "gb", None, "s1"),
        ("Tobu Girl", "Tobu_Girl.gb", "gb", None, "s1"),
    ]
    assert files[0].url == "https://example.com/a/chrono%20demo.zip"


async def test_link_list_list_files_reads_local_file(tmp_path: Path) -> None:
    path = tmp_path / "list.txt"
    path.write_text("Game ä | https://example.org/g.gb\n", encoding="utf-8")
    source = SourceConfig("s2", "Local", "link-list", str(path), "gb")
    files = await LinkListAdapter(FakeHttp({})).list_files(source)
    assert [f.title for f in files] == ["Game ä"]


async def test_link_list_skips_unsafe_or_empty_names() -> None:
    body = (
        "https://example.com/dir/\n"
        "https://example.com/a/%2E%2E\n"
        "https://example.com/a/..%2F..%2Fevil.zip\n"
        "https://example.com/a/x%5C..%5Cwin.zip\n"
        "https://example.com/a/%2F\n"
    )
    adapter = LinkListAdapter(FakeHttp({"https://example.com/l.txt": (body, "text/plain")}))
    source = SourceConfig("s3", "Odd", "link-list", "https://example.com/l.txt", "gb")
    files = await adapter.list_files(source)
    assert [f.file_name for f in files] == ["evil.zip", "win.zip"]
