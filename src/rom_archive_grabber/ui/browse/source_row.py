from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.events import Click
from textual.message import Message
from textual.widgets import Static

from rom_archive_grabber.application.catalog import SourceState

_STATE_SUFFIX = {SourceState.LOADING: " …", SourceState.ERROR: " !"}
CURRENT_MARK = "▶"


@dataclass(frozen=True, slots=True)
class SourceView:
    id: str
    name: str
    state: SourceState
    error: str | None
    shown: bool
    enabled: bool
    # Added by the user, so it can be edited and removed.
    user: bool

    @property
    def dot(self) -> str:
        """Whether the source's files are shown in the results."""
        return "●" if self.shown else "○"

    @property
    def label(self) -> str:
        off = "" if self.enabled else " (off)"
        return f"{self.name}{_STATE_SUFFIX.get(self.state, '')}{off}"


class SourceRow(Horizontal, can_focus=True):
    """One source: a ● / ○ toggle that shows or hides its files, then its name.

    Clicking the name only selects the row (it gets focus); the Sources panel buttons act
    on the selected row. Clicking the toggle, `space` or `enter` shows or hides the files.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_visibility", "Show/hide", show=False),
        Binding("enter", "toggle_visibility", "Show/hide", show=False),
    ]

    class VisibilityToggled(Message):
        def __init__(self, source_id: str) -> None:
            super().__init__()
            self.source_id = source_id

    def __init__(self, view: SourceView, widget_id: str) -> None:
        super().__init__(id=widget_id)
        self.source_id = view.id
        self._view = view
        self._current = False

    @property
    def text(self) -> str:
        """The row as shown, such as `● ▶ My List !`."""
        return f"{self._view.dot} {self._name_text()}"

    def compose(self) -> ComposeResult:
        yield Static(classes="source-toggle", markup=False)
        yield Static(classes="source-name", markup=False)

    def on_mount(self) -> None:
        self._paint()

    def show(self, view: SourceView, current: bool) -> None:
        self._view, self._current = view, current
        self._paint()

    def on_click(self, event: Click) -> None:
        if event.widget is self.query_one(".source-toggle"):
            event.stop()
            self.action_toggle_visibility()

    def action_toggle_visibility(self) -> None:
        self.post_message(self.VisibilityToggled(self.source_id))

    def _paint(self) -> None:
        self.query_one(".source-toggle", Static).update(self._view.dot)
        self.query_one(".source-name", Static).update(self._name_text())
        failed = self._view.state is SourceState.ERROR
        self.tooltip = self._view.error if failed else None
        self.set_class(not self._view.shown, "-hidden")
        self.set_class(self._current, "-current")

    def _name_text(self) -> str:
        mark = CURRENT_MARK if self._current else " "
        return f"{mark} {self._view.label}"
