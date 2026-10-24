from dataclasses import dataclass

from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets.data_table import ColumnKey

from rom_archive_grabber.application.search import SortColumn

# Column key and header text, in display order.
COLUMNS = (
    ("mark", "Mark"),
    ("title", "Title"),
    ("platform", "Platform"),
    ("size", "Size"),
    ("source", "Source"),
    ("status", "Status"),
)
_SORTABLE = {column.value: column for column in SortColumn}
# Long titles and source names are cut so Status stays on screen.
_MAX_WIDTHS = {"title": 36, "source": 18}


@dataclass(frozen=True, slots=True)
class RowView:
    key: str
    cells: tuple[str, str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class SortView:
    column: SortColumn | None
    descending: bool


def _headers(sort: SortView) -> list[str]:
    arrow = "▼" if sort.descending else "▲"
    return [
        f"{label} {arrow}" if sort.column is not None and key == sort.column.value else label
        for key, label in COLUMNS
    ]


def _capped_width(key: str, index: int, rows: list[RowView]) -> int | None:
    """A fixed width for a capped column whose text is too long, else None (automatic)."""
    cap = _MAX_WIDTHS.get(key)
    longest = max((len(row.cells[index]) for row in rows), default=0)
    return cap if cap is not None and longest > cap else None


class ResultsTable(DataTable[str]):
    """The file list. Rows are keyed by `GameFile.key`."""

    title_key = ColumnKey("title")

    class SortRequested(Message):
        def __init__(self, column: SortColumn) -> None:
            super().__init__()
            self.column = column

    def __init__(self) -> None:
        super().__init__(id="results", cursor_type="row", zebra_stripes=True)
        self._keys: list[str] = []
        self._headers: list[str] = []

    def show(self, rows: list[RowView], sort: SortView) -> None:
        """Show `rows`, updating cells in place when only their text changed."""
        headers = _headers(sort)
        keys = [row.key for row in rows]
        if keys == self._keys and headers == self._headers:
            self._update_cells(rows)
            return
        self._rebuild(rows, headers)
        self._keys, self._headers = keys, headers

    def cursor_key(self) -> str | None:
        if self.row_count == 0:
            return None
        cell = self.coordinate_to_cell_key(Coordinate(self.cursor_row, 0))
        return cell.row_key.value

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        event.stop()
        column = _SORTABLE.get(event.column_key.value or "")
        if column is not None:
            self.post_message(self.SortRequested(column))

    def _update_cells(self, rows: list[RowView]) -> None:
        for row in rows:
            for (column, _), text in zip(COLUMNS, row.cells, strict=True):
                if self.get_cell(row.key, column) != text:
                    self.update_cell(row.key, column, text)

    def _rebuild(self, rows: list[RowView], headers: list[str]) -> None:
        # Keep the cursor on the same file and the view where the user left it.
        cursor, scroll_y = self.cursor_key(), self.scroll_y
        self.clear(columns=True)
        for index, ((key, _), header) in enumerate(zip(COLUMNS, headers, strict=True)):
            self.add_column(header, key=key, width=_capped_width(key, index, rows))
        for row in rows:
            self.add_row(*row.cells, key=row.key)
        if cursor is not None and cursor in self.rows:
            self.move_cursor(row=self.get_row_index(cursor), scroll=False)
        # The new rows are measured on the next refresh; scrolling earlier would clamp to 0.
        self.call_after_refresh(self.scroll_to, y=scroll_y, animate=False)
