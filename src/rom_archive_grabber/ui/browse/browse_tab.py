import asyncio
from collections.abc import Awaitable, Callable
from typing import ClassVar, TypeVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input
from textual.worker import Worker, WorkerState

from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.ui.browse.browse_state import BrowseState
from rom_archive_grabber.ui.browse.browse_views import BrowseViews
from rom_archive_grabber.ui.browse.choice_row import ChoiceRow
from rom_archive_grabber.ui.browse.details_panel import DetailsPanel
from rom_archive_grabber.ui.browse.loaded_files import LoadedFiles
from rom_archive_grabber.ui.browse.results_table import ResultsTable, SortView
from rom_archive_grabber.ui.browse.row_context import RowContext
from rom_archive_grabber.ui.browse.source_actions import SourceActions
from rom_archive_grabber.ui.browse.source_row import SourceRow
from rom_archive_grabber.ui.browse.sources_panel import ALL_PLATFORMS, SourcesPanel
from rom_archive_grabber.ui.folder_opener import open_folder_or_notify
from rom_archive_grabber.ui.services import AppServices

# Progress can arrive many times a second; the view redraws at most this often.
REDRAW_SECONDS = 0.25
T = TypeVar("T")


class BrowseTab(Vertical):
    """Search, filter, sort and mark files, and send them to the download queue."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_mark", "Mark"),
        Binding("d", "download", "Download"),
    ]

    def __init__(self, services: AppServices) -> None:
        super().__init__(id="browse-tab")
        self._services = services
        self._state = BrowseState()
        self._views = BrowseViews(services, self._state)
        self._files = LoadedFiles(services)
        self._dirty = False
        # Listing runs for all sources and for single sources can overlap.
        self._refreshes = 0
        self._source_actions = SourceActions(services, self)
        # The refresh worker and event handlers can both redraw; one at a time.
        self._view_lock = asyncio.Lock()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield SourcesPanel(id="sources")
            with Vertical(id="centre"):
                yield Input(placeholder="search", id="search")
                yield ResultsTable()
            yield DetailsPanel(id="details")

    async def on_mount(self) -> None:
        self.set_interval(REDRAW_SECONDS, self._redraw_if_dirty)
        self._files.reload()
        await self.refresh_view()

    def mark_dirty(self) -> None:
        self._dirty = True

    def start_refresh(self, only_stale: bool) -> None:
        """List the sources again in the background, showing files as they arrive."""
        self._start_refresh(self._services.all_sources(), only_stale, "refresh")

    def refresh_sources(self, sources: list[SourceConfig]) -> None:
        """List these sources again without stopping a refresh of the others."""
        for source in sources:
            self._start_refresh([source], False, f"refresh:{source.id}")

    def add_source(self) -> None:
        self._source_actions.add()

    def ask(self, screen: ModalScreen[T], then: Callable[[T | None], Awaitable[None]]) -> None:
        self.app.push_screen(screen, then)

    def notify_error(self, message: str) -> None:
        self.notify(message, title="Settings", severity="error", timeout=10)

    async def sources_changed(self) -> None:
        self._files.reload()
        await self.refresh_view()

    async def on_sources_panel_action_requested(self, event: SourcesPanel.ActionRequested) -> None:
        await self._source_actions.run(event.action, event.source_id)

    def _start_refresh(self, sources: list[SourceConfig], only_stale: bool, group: str) -> None:
        # A failed refresh is reported, never allowed to close the app.
        work = self._refresh(sources, only_stale)
        self.run_worker(work, group=group, exclusive=True, exit_on_error=False)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state is WorkerState.ERROR:
            message = f"Listing sources stopped: {event.worker.error}"
            self.notify(message, title="Refresh failed", severity="error")

    async def refresh_view(self) -> None:
        async with self._view_lock:
            await self._draw()

    async def _draw(self) -> None:
        self._dirty = False
        sources = self._services.all_sources()
        context = self._views.row_context(sources)
        visible = self._state.visible(self._files.files, [source.id for source in sources])
        sort = SortView(self._state.sort_column, self._state.descending)
        self.query_one(ResultsTable).show([context.row(file) for file in visible], sort)
        panel = self.query_one(SourcesPanel)
        await panel.show(self._views.sources(), self._views.platforms(self._files.files))
        self._show_details(context)

    def download_marked(self) -> None:
        """Queue the marked files, or the file under the cursor when none are marked."""
        marked = [self._files.get(key) for key in self._visible_keys() if key in self._state.marked]
        files = [file for file in marked if file is not None]
        if not files:
            cursor = self._cursor_file()
            files = [] if cursor is None else [cursor]
        self._services.downloads.enqueue(files)
        self._state.marked.clear()
        self.mark_dirty()

    async def action_toggle_mark(self) -> None:
        cursor = self._cursor_file()
        if cursor is not None:
            self._state.toggle_mark(cursor.key)
            await self.refresh_view()

    async def action_download(self) -> None:
        self.download_marked()
        await self.refresh_view()

    async def on_input_changed(self, event: Input.Changed) -> None:
        self._state.query = event.value
        await self.refresh_view()

    async def on_results_table_sort_requested(self, event: ResultsTable.SortRequested) -> None:
        self._state.sort_by(event.column)
        await self.refresh_view()

    async def on_choice_row_chosen(self, event: ChoiceRow.Chosen) -> None:
        # Only platforms use choice rows: one platform filter at a time.
        self._state.platform = None if event.value == ALL_PLATFORMS else event.value
        await self.refresh_view()

    async def on_source_row_visibility_toggled(self, event: SourceRow.VisibilityToggled) -> None:
        self._state.toggle_source(event.source_id)
        await self.refresh_view()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_details(self._views.row_context(self._services.all_sources()))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        cursor = self._cursor_file()
        if cursor is None:
            return
        elif event.button.id in ("download", "download-again"):
            self._services.downloads.enqueue([cursor])
            await self.refresh_view()
        elif event.button.id == "open-folder":
            open_folder_or_notify(
                self.app, self._services.open_folder, self._views.folder_for(cursor)
            )

    async def _refresh(self, sources: list[SourceConfig], only_stale: bool) -> None:
        self._refreshes += 1
        catalog = self._services.catalog
        try:
            for source in sources:
                if only_stale and not catalog.is_stale(source.id):
                    continue
                await catalog.refresh(source, self._show_partial)
                # The finished listing replaces the partial one straight away.
                self._files.reload()
                self.mark_dirty()
        finally:
            self._refreshes -= 1
            self._files.reload()
            await self.refresh_view()

    def _show_partial(self, files: list[GameFile], done: int, total: int | None) -> None:
        self._files.merge(files)
        self.mark_dirty()

    async def _redraw_if_dirty(self) -> None:
        # Source markers change while listing runs, so redraw throughout a refresh.
        if self._dirty or self._refreshes:
            await self.refresh_view()

    def _show_details(self, context: RowContext) -> None:
        cursor = self._cursor_file()
        view = None if cursor is None else context.details(cursor)
        self.query_one(DetailsPanel).show(view)

    def _cursor_file(self) -> GameFile | None:
        key = self.query_one(ResultsTable).cursor_key()
        return None if key is None else self._files.get(key)

    def _visible_keys(self) -> list[str]:
        return [str(key.value) for key in self.query_one(ResultsTable).rows]
