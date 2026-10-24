from textual.pilot import Pilot
from textual.widgets import Static, TabbedContent

from rom_archive_grabber.ui.app import RomArchiveApp
from rom_archive_grabber.ui.browse.source_row import SourceRow
from rom_archive_grabber.ui.message_dialog import MessageDialog
from tests.ui.conftest import BUILTIN, World

SIZE = (160, 40)


async def loaded(pilot: Pilot[None]) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def error_messages(pilot: Pilot[None]) -> list[str]:
    return [note.message for note in pilot.app._notifications if note.severity == "error"]


async def test_failed_catalog_save_keeps_app_running_and_marks_source(world: World) -> None:
    world.fail_catalog_saves = True
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        assert pilot.app.is_running
        row = pilot.app.query_one(f"#source-{BUILTIN.id}", SourceRow)
        assert row.text.endswith(" !")
        assert row.tooltip == "cache folder is read-only"


async def test_failing_open_folder_shows_error_instead_of_crashing(world: World) -> None:
    world.open_error = FileNotFoundError("no file manager")
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.app.run_action("open_download_folder")
        await pilot.pause()
        assert pilot.app.is_running
        assert any("no file manager" in message for message in error_messages(pilot))


async def test_tab_does_nothing_while_a_dialog_is_open(world: World) -> None:
    world.startup_error = "settings.toml: bad value"
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.press("tab")
        assert isinstance(pilot.app.screen, MessageDialog)
        assert pilot.app.query_one(TabbedContent).active == "browse"


async def test_startup_dialog_says_settings_will_not_be_saved(world: World) -> None:
    world.startup_error = "settings.toml: bad value"
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        message = str(pilot.app.screen.query_one("#dialog-message", Static).render())
        assert "settings.toml: bad value" in message
        assert "won't be saved until the file is fixed" in message


async def test_palette_switch_tab_still_works(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.press("ctrl+p", *"switch tab")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause()
        assert pilot.app.query_one(TabbedContent).active == "downloads"


async def test_failed_settings_save_keeps_app_running_and_notifies(world: World) -> None:
    world.fail_settings_saves = True
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.click(f"#source-{BUILTIN.id} .source-name")
        await pilot.click("#toggle-source")
        await pilot.pause()
        await loaded(pilot)
        assert pilot.app.is_running
        assert any("Couldn't save settings" in message for message in error_messages(pilot))


async def test_failed_queue_save_is_reported_once(world: World) -> None:
    app = RomArchiveApp(world.services())
    async with app.run_test(size=SIZE) as pilot:
        await loaded(pilot)
        world.job_store.last_error = "Couldn't save the download queue: disk full"
        await app._redraw_downloads()
        await app._redraw_downloads()
        await pilot.pause()
        reports = [m for m in error_messages(pilot) if "disk full" in m]
        assert len(reports) == 1
        assert pilot.app.is_running
