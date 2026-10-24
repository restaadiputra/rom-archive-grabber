from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class MessageDialog(ModalScreen[None]):
    """A message the user must acknowledge, such as a settings file that cannot be read."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, classes="heading", markup=False)
            yield Static(self._message, id="dialog-message", markup=False)
            yield Button("OK", id="dialog-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss()
