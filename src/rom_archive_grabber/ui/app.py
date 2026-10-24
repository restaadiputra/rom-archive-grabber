import contextlib
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, TabbedContent, TabPane

from rom_archive_grabber.domain.models import SourceConfig
from rom_archive_grabber.ui.browse.browse_tab import REDRAW_SECONDS, BrowseTab
from rom_archive_grabber.ui.browse.formatting import downloads_tab_label
from rom_archive_grabber.ui.commands import AppCommands
from rom_archive_grabber.ui.downloads.downloads_tab import DownloadsTab
from rom_archive_grabber.ui.folder_opener import open_folder_or_notify
from rom_archive_grabber.ui.message_dialog import MessageDialog
from rom_archive_grabber.ui.services import AppServices, PluginWarning

__all__ = ["AppServices", "PluginWarning", "RomArchiveApp"]

_TABS = ("browse", "downloads")
_UNSAVED_NOTE = "Changes to settings won't be saved until the file is fixed."


class RomArchiveApp(App[None]):
    """Two tabs: Browse to find and queue files, Downloads to follow them."""

    TITLE = "rom-archive-grabber"
    CSS_PATH = "app.tcss"
    COMMANDS = App.COMMANDS | {AppCommands}
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("tab", "switch_tab", "Switch tab", priority=True),
        # `tab` switches tabs, so focus moves with shift+tab (and the mouse).
        Binding("shift+tab", "app.focus_previous", "Focus", priority=True),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, services: AppServices) -> None:
        super().__init__()
        self.services = services
        self._downloads_changed = False
        self._closed = False
        self._reported_save_error: str | None = None
        # The focused widget of each tab when it was left, restored on return.
        self._left_focus: dict[str, Widget | None] = {}

    def compose(self) -> ComposeResult:
        with TabbedContent(id="tabs"):
            with TabPane("Browse", id="browse"):
                yield BrowseTab(self.services)
            with TabPane("Downloads", id="downloads"):
                yield DownloadsTab(self.services)
        yield Footer()

    async def on_mount(self) -> None:
        downloads = self.services.downloads
        await downloads.start()
        downloads.on_change = self._on_downloads_changed
        self.set_interval(REDRAW_SECONDS, self._redraw_downloads)
        await self._redraw_downloads(force=True)
        self._show_startup_problems()
        self._browse().start_refresh(only_stale=True)

    async def on_unmount(self) -> None:
        await self._close_downloads()

    def all_sources(self) -> list[SourceConfig]:
        return self.services.all_sources()

    async def action_quit(self) -> None:
        await self._close_downloads()
        self.exit()

    def action_switch_tab(self) -> None:
        # The binding has priority, so it also fires behind dialogs and the palette.
        if isinstance(self.screen, ModalScreen):
            return
        tabs = self.query_one(TabbedContent)
        self._left_focus[tabs.active] = self.focused
        tabs.active = _TABS[(_TABS.index(tabs.active) + 1) % len(_TABS)]
        self._focus_tab(tabs.active)

    def action_refresh_all(self) -> None:
        self._browse().start_refresh(only_stale=False)

    def action_download_marked(self) -> None:
        self._browse().download_marked()

    def action_pause_all(self) -> None:
        self.services.downloads.pause_all()

    def action_resume_all(self) -> None:
        self.services.downloads.resume_all()

    def action_open_download_folder(self) -> None:
        open_folder_or_notify(self, self.services.open_folder, self.services.settings.download_dir)

    def action_add_source(self) -> None:
        self._browse().add_source()

    def _focus_tab(self, pane_id: str) -> None:
        """Focus where the tab was left, so its keys work and the hidden tab's do not."""
        pane = self.query_one(f"#{pane_id}", TabPane)
        previous = self._left_focus.get(pane_id)
        if previous is not None and previous.is_attached and pane in previous.ancestors:
            previous.focus()
        elif pane_id == "downloads":
            self.query_one(DownloadsTab).focus_list()
        else:
            self._browse().query_one(Input).focus()

    def _browse(self) -> BrowseTab:
        return self.query_one(BrowseTab)

    def _on_downloads_changed(self) -> None:
        # Progress fires many times a second; the timer picks the change up.
        self._downloads_changed = True
        # While the app shuts down its widgets are already gone; nothing to redraw.
        with contextlib.suppress(NoMatches):
            self._browse().mark_dirty()

    def _report_save_error(self) -> None:
        # Tell the user once per new problem, not on every tick.
        error = self.services.downloads.storage_error
        if error is not None and error != self._reported_save_error:
            self.notify(error, title="Download queue", severity="error", timeout=10)
        self._reported_save_error = error

    async def _redraw_downloads(self, force: bool = False) -> None:
        self._report_save_error()
        if not (force or self._downloads_changed):
            return
        self._downloads_changed = False
        label = downloads_tab_label(self.services.downloads.jobs())
        # The timer can fire once more while shutdown is removing the tabs.
        with contextlib.suppress(NoMatches):
            self.query_one(TabbedContent).get_tab("downloads").label = label
            await self.query_one(DownloadsTab).refresh_jobs()

    def _show_startup_problems(self) -> None:
        for warning in self.services.plugin_warnings:
            message = f"{warning.path.name}: {warning.message}"
            self.notify(message, title="Plugin skipped", severity="warning", timeout=10)
        if self.services.startup_error:
            message = f"{self.services.startup_error}\n\n{_UNSAVED_NOTE}"
            self.push_screen(MessageDialog("Settings not loaded", message))

    async def _close_downloads(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.services.downloads.on_change = None
        await self.services.downloads.shutdown()
