from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.events import Click
from textual.message import Message
from textual.widgets import Static


class ChoiceRow(Static, can_focus=True):
    """One clickable line in a side list, such as a source or a platform."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("enter", "choose", "Choose", show=False)]

    class Chosen(Message):
        def __init__(self, group: str, value: str) -> None:
            super().__init__()
            self.group = group
            self.value = value

    def __init__(self, text: str, group: str, value: str, widget_id: str) -> None:
        super().__init__(text, id=widget_id, markup=False)
        self.group = group
        self.value = value

    def on_click(self, event: Click) -> None:
        event.stop()
        self.action_choose()

    def action_choose(self) -> None:
        self.post_message(self.Chosen(self.group, self.value))
