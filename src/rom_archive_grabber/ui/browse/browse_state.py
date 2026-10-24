from collections.abc import Sequence
from dataclasses import dataclass, field

from rom_archive_grabber.application.search import (
    FileFilter,
    SortColumn,
    filter_files,
    sort_files,
)
from rom_archive_grabber.domain.models import GameFile


@dataclass
class BrowseState:
    """What the user has chosen to see: search, platform, hidden sources, sort, marks."""

    query: str = ""
    platform: str | None = None
    hidden_sources: set[str] = field(default_factory=set)
    sort_column: SortColumn | None = None
    descending: bool = False
    marked: set[str] = field(default_factory=set)

    def visible(self, files: Sequence[GameFile], source_ids: Sequence[str]) -> list[GameFile]:
        shown = filter_files(files, self._filter(source_ids))
        if self.sort_column is None:
            return shown
        return sort_files(shown, self.sort_column, self.descending)

    def sort_by(self, column: SortColumn) -> None:
        """A new column sorts ascending; the current column flips direction."""
        if self.sort_column is column:
            self.descending = not self.descending
        else:
            self.sort_column, self.descending = column, False

    def toggle_source(self, source_id: str) -> None:
        self.hidden_sources ^= {source_id}

    def toggle_mark(self, file_key: str) -> None:
        self.marked ^= {file_key}

    def _filter(self, source_ids: Sequence[str]) -> FileFilter:
        allowed = None
        if self.hidden_sources:
            allowed = frozenset(s for s in source_ids if s not in self.hidden_sources)
        return FileFilter(self.query, allowed, self.platform)
