from rom_archive_grabber.application.search import (
    FileFilter,
    SortColumn,
    filter_files,
    matches,
    sort_files,
)
from rom_archive_grabber.domain.models import GameFile


def make_file(
    title: str,
    *,
    source_id: str = "s1",
    platform: str = "gb",
    size: int | None = 1,
) -> GameFile:
    return GameFile(
        source_id=source_id,
        title=title,
        file_name=f"{title}.zip",
        platform=platform,
        size=size,
        url=f"https://example.com/{title}.zip",
    )


def test_matches_ignores_case_and_accents() -> None:
    assert matches("pokemon", "Pokémon Homebrew")


def test_matches_requires_all_words() -> None:
    assert not matches("tobu deluxe", "Tobu Tobu Girl")


def test_matches_empty_query_matches_all() -> None:
    assert matches("   ", "Anything")


def test_filter_by_platform_and_source() -> None:
    a = make_file("A", source_id="s1", platform="gb")
    b = make_file("B", source_id="s2", platform="gb")
    c = make_file("C", source_id="s1", platform="nes")
    files = [a, b, c]

    assert filter_files(files, FileFilter(platform="gb", source_ids=frozenset({"s1"}))) == [a]
    assert filter_files(files, FileFilter()) == files
    assert filter_files(files, FileFilter(source_ids=frozenset())) == []
    assert filter_files(files, FileFilter(query="b")) == [b]


def test_sort_size_none_last_both_directions() -> None:
    small = make_file("small", size=1)
    big = make_file("big", size=9)
    unknown = make_file("unknown", size=None)
    files = [unknown, big, small]

    assert sort_files(files, SortColumn.SIZE) == [small, big, unknown]
    assert sort_files(files, SortColumn.SIZE, descending=True) == [big, small, unknown]


def test_sort_title_descending() -> None:
    a, b, c = make_file("alpha"), make_file("Beta"), make_file("gamma")

    assert sort_files([b, a, c], SortColumn.TITLE, descending=True) == [c, b, a]


def test_sort_source_ties_broken_by_title() -> None:
    x = make_file("x", source_id="s1")
    y = make_file("y", source_id="s1")
    z = make_file("a", source_id="s2")

    assert sort_files([z, y, x], SortColumn.SOURCE) == [x, y, z]
