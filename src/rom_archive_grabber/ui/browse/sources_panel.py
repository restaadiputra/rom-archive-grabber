import re
from collections.abc import Sequence
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import DescendantFocus
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from rom_archive_grabber.ui.browse.choice_row import ChoiceRow
from rom_archive_grabber.ui.browse.source_row import SourceRow, SourceView

__all__ = ["ALL_PLATFORMS", "PlatformView", "SourceView", "SourcesPanel"]

SOURCE_GROUP = "source"
PLATFORM_GROUP = "platform"
ALL_PLATFORMS = ""
_ID_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
# Panel button id → the action it asks for on the highlighted source.
_BUTTON_ACTIONS = {
    "add-source": "add",
    "edit-source": "edit",
    "refresh-source": "refresh",
    "toggle-source": "toggle",
    "remove-source": "remove",
}


@dataclass(frozen=True, slots=True)
class PlatformView:
    key: str
    label: str
    selected: bool


def _widget_ids(prefix: str, values: list[str]) -> list[str]:
    """Valid, unique widget ids that stay readable (`source-my-list`)."""
    ids: list[str] = []
    for index, value in enumerate(values):
        candidate = f"{prefix}-{_ID_UNSAFE.sub('_', value)}"
        ids.append(candidate if candidate not in ids else f"{candidate}-{index}")
    return ids


class SourcesPanel(Vertical):
    """Left column: the sources to show and the platforms present in the results.

    The buttons under the sources act on the selected one: the source row that last
    had focus (a click on its name gives it focus), or the first source.
    """

    class ActionRequested(Message):
        """A source button was pressed; `source_id` is None for `add`."""

        def __init__(self, action: str, source_id: str | None) -> None:
            super().__init__()
            self.action = action
            self.source_id = source_id

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._views: dict[str, SourceView] = {}
        self._current: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("Sources", classes="heading")
        yield VerticalScroll(id="source-list")
        with Horizontal(classes="source-actions"):
            yield Button("Edit", id="edit-source", compact=True)
            yield Button("Refresh", id="refresh-source", compact=True)
        with Horizontal(classes="source-actions"):
            yield Button("Disable", id="toggle-source", compact=True)
            yield Button("Remove", id="remove-source", compact=True)
        yield Button("+ Add source", id="add-source", compact=True)
        yield Static("Platforms", classes="heading")
        yield VerticalScroll(id="platform-list")

    async def show(self, sources: list[SourceView], platforms: list[PlatformView]) -> None:
        await self._show_sources(sources)
        all_row = PlatformView(ALL_PLATFORMS, "All", not any(p.selected for p in platforms))
        await self._show_platforms([all_row, *platforms])

    async def _show_sources(self, sources: list[SourceView]) -> None:
        ids = _widget_ids(SOURCE_GROUP, [source.id for source in sources])
        container = self.query_one("#source-list", VerticalScroll)
        if self._ids(container) != ids:
            await self._replace(
                container, [SourceRow(s, i) for s, i in zip(sources, ids, strict=True)]
            )
        self._views = {source.id: source for source in sources}
        if self._current not in self._views:
            self._current = sources[0].id if sources else None
        self._show_current()

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        row = event.widget
        if isinstance(row, SourceRow):
            self._current = row.source_id
            self._show_current()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = _BUTTON_ACTIONS.get(event.button.id or "")
        if action is not None:
            event.stop()
            source_id = None if action == "add" else self._current
            self.post_message(self.ActionRequested(action, source_id))

    def _show_current(self) -> None:
        view = self._views.get(self._current or "")
        for row in self.query_one("#source-list").query(SourceRow):
            current = row.source_id == self._current
            row.show(self._views[row.source_id], current)
        user = view is not None and view.user
        self.query_one("#edit-source", Button).disabled = not user
        self.query_one("#remove-source", Button).disabled = not user
        self.query_one("#refresh-source", Button).disabled = view is None or not view.enabled
        toggle = self.query_one("#toggle-source", Button)
        toggle.disabled = view is None
        toggle.label = "Enable" if view is not None and not view.enabled else "Disable"

    async def _show_platforms(self, platforms: list[PlatformView]) -> None:
        names = ["all" if p.key == ALL_PLATFORMS else p.key for p in platforms]
        ids = _widget_ids(PLATFORM_GROUP, names)
        container = self.query_one("#platform-list", VerticalScroll)
        if self._ids(container) != ids:
            rows = [
                ChoiceRow(p.label, PLATFORM_GROUP, p.key, i)
                for p, i in zip(platforms, ids, strict=True)
            ]
            await self._replace(container, rows)
        for row, platform in zip(container.query(ChoiceRow), platforms, strict=True):
            row.set_class(platform.selected, "-selected")

    @staticmethod
    def _ids(container: VerticalScroll) -> list[str]:
        return [row.id or "" for row in container.children]

    @staticmethod
    async def _replace(container: VerticalScroll, rows: Sequence[Widget]) -> None:
        await container.remove_children()
        await container.mount_all(rows)
