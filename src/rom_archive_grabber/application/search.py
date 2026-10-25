import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from rom_archive_grabber.domain.models import GameFile


def normalize(text: str) -> str:
    """Casefold and strip accents so "Pokémon" and "pokemon" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@lru_cache(maxsize=100_000)
def _normalized_title(title: str) -> str:
    return normalize(title)


def matches(query: str, title: str) -> bool:
    words = normalize(query).split()
    return all(word in _normalized_title(title) for word in words)


class SortColumn(StrEnum):
    TITLE = "title"
    PLATFORM = "platform"
    SIZE = "size"
    SOURCE = "source"


@dataclass(frozen=True)
class FileFilter:
    query: str = ""
    # None means "all sources"; an empty set means "no sources".
    source_ids: frozenset[str] | None = None
    platform: str | None = None


def filter_files(files: Sequence[GameFile], flt: FileFilter) -> list[GameFile]:
    words = normalize(flt.query).split()
    return [f for f in files if _accepts(f, flt, words)]


def _accepts(file: GameFile, flt: FileFilter, words: list[str]) -> bool:
    if flt.source_ids is not None and file.source_id not in flt.source_ids:
        return False
    if flt.platform is not None and file.platform != flt.platform:
        return False
    return not words or all(word in _normalized_title(file.title) for word in words)


def sort_files(
    files: Sequence[GameFile], column: SortColumn, descending: bool = False
) -> list[GameFile]:
    if column is SortColumn.SIZE:
        return _sort_by_size(files, descending)
    ordered = sorted(files, key=lambda f: _sort_key(f, column))
    return ordered[::-1] if descending else ordered


def _sort_key(file: GameFile, column: SortColumn) -> tuple[str, str]:
    primary = {
        SortColumn.TITLE: file.title,
        SortColumn.PLATFORM: file.platform,
        SortColumn.SOURCE: file.source_id,
    }[column]
    return normalize(primary), normalize(file.title)


def _sort_by_size(files: Sequence[GameFile], descending: bool) -> list[GameFile]:
    # Unknown sizes stay at the end whichever way the list is ordered.
    known = sorted(
        (f for f in files if f.size is not None),
        key=lambda f: (f.size or 0, normalize(f.title)),
        reverse=descending,
    )
    return known + [f for f in files if f.size is None]
