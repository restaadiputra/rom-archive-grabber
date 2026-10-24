from textual.app import App
from textual.widgets import Button

from rom_archive_grabber.domain.models import Platform
from rom_archive_grabber.ui.dialogs.add_source import AddSourceDialog
from tests.ui.test_sources import NEW_LINK, SIZE, fill, message, settle


class DialogApp(App[None]):
    """The add dialog on its own, with a link check that fails."""

    async def broken_detect(self, location: str) -> str | None:
        raise RuntimeError("network down")

    def on_mount(self) -> None:
        platforms = [Platform("nes", "NES", "nes")]
        self.push_screen(AddSourceDialog(platforms, detect=self.broken_detect))


async def test_failing_link_check_shows_error_and_allows_retry() -> None:
    async with DialogApp().run_test(size=SIZE) as pilot:
        await pilot.pause()
        fill(pilot, NEW_LINK, "Picks", None)
        await pilot.click("#source-add")
        await settle(pilot)
        assert isinstance(pilot.app.screen, AddSourceDialog)
        assert message(pilot) == "Checking the link failed: network down"
        assert not pilot.app.screen.query_one("#source-add", Button).disabled
