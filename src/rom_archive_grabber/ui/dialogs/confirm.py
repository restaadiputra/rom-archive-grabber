from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmDialog(ModalScreen[bool]):
    """A yes-or-no question before something that cannot be undone, such as removing a source."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", "No")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._message, id="dialog-message", markup=False)
            with Horizontal(id="dialog-buttons"):
                yield Button("Yes", id="confirm-yes", variant="error")
                yield Button("No", id="confirm-no")

    def on_mount(self) -> None:
        # The safe answer has focus, so a stray enter does not confirm.
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "confirm-yes")
