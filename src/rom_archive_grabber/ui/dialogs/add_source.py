import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static
from textual.worker import Worker, WorkerState

from rom_archive_grabber.domain.models import Platform, SourceConfig

# Finds the source kind that can read a link or file path; None when none can.
DetectKind = Callable[[str], Awaitable[str | None]]

UNDETECTED = (
    "Couldn't recognise this link. Supported: Archive.org items or collections, "
    "folder pages, plain link lists, and installed plugins."
)
_MISSING = "Enter a link or file path and a name."
_CHECKING = "Checking link…"


@dataclass(frozen=True, slots=True)
class SourceDraft:
    location: str
    name: str
    platform: str
    # The detected kind, or the existing source's kind when editing.
    kind: str = ""


class AddSourceDialog(ModalScreen[SourceDraft | None]):
    """Asks for a link or file path, a name and a platform; checks the link before adding.

    With `existing`, edits that source's name and platform; its link cannot change.
    """

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(
        self, platforms: list[Platform], existing: SourceConfig | None = None, *, detect: DetectKind
    ) -> None:
        super().__init__()
        self._platforms = platforms
        self._existing = existing
        self._detect = detect

    def compose(self) -> ComposeResult:
        existing = self._existing
        options = [(platform.label, platform.key) for platform in self._platforms]
        platform = existing.platform if existing else options[0][1]
        with Vertical(id="dialog", classes="-form"):
            yield Static("Edit source" if existing else "Add source", classes="heading")
            yield Input(
                existing.location if existing else "",
                placeholder="URL or file path",
                id="source-location",
                disabled=existing is not None,
            )
            yield Input(existing.name if existing else "", placeholder="Name", id="source-name")
            yield Select(options, value=platform, allow_blank=False, id="source-platform")
            yield Static("", id="source-message", markup=False)
            with Horizontal(id="dialog-buttons"):
                yield Button("Save" if existing else "Add", id="source-add", variant="primary")
                yield Button("Cancel", id="source-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "source-cancel":
            self.dismiss(None)
        else:
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if not self.query_one("#source-add", Button).disabled:
            self._submit()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state is WorkerState.ERROR:
            self._say(f"Checking the link failed: {event.worker.error}")

    def _submit(self) -> None:
        draft = self._draft()
        if not (draft.location and draft.name):
            self._say(_MISSING)
        elif self._existing is not None:
            self.dismiss(dataclasses.replace(draft, kind=self._existing.kind))
        else:
            # A failed check is shown in the dialog, never allowed to close the app.
            self.run_worker(self._check(draft), exclusive=True, exit_on_error=False)

    async def _check(self, draft: SourceDraft) -> None:
        add = self.query_one("#source-add", Button)
        add.disabled = True
        self._say(_CHECKING)
        try:
            kind = await self._detect(draft.location)
        finally:
            add.disabled = False
        if not self.is_attached:
            return  # Cancel closed the dialog while the link was checked.
        if kind is None:
            self._say(UNDETECTED)
        else:
            self.dismiss(dataclasses.replace(draft, kind=kind))

    def _draft(self) -> SourceDraft:
        location = self.query_one("#source-location", Input).value.strip()
        name = self.query_one("#source-name", Input).value.strip()
        platform = self.query_one("#source-platform", Select).value
        return SourceDraft(location, name, str(platform))

    def _say(self, text: str) -> None:
        self.query_one("#source-message", Static).update(text)
