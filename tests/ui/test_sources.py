from textual.pilot import Pilot
from textual.widgets import Button, Input, Select, Static

from rom_archive_grabber.domain.models import SourceConfig
from rom_archive_grabber.ui.app import RomArchiveApp
from rom_archive_grabber.ui.browse.results_table import ResultsTable
from rom_archive_grabber.ui.browse.source_row import SourceRow
from rom_archive_grabber.ui.dialogs.add_source import AddSourceDialog
from rom_archive_grabber.ui.dialogs.confirm import ConfirmDialog
from tests.ui.conftest import BUILTIN, HIDDEN, MY_LIST, OFF, SLOW_LINK, World

SIZE = (160, 40)
NEW_LINK = "https://example.org/picks.txt"
UNDETECTED = (
    "Couldn't recognise this link. Supported: Archive.org items or collections, "
    "folder pages, and plain link lists."
)


async def settle(pilot: Pilot[None]) -> None:
    # A dialog's result starts more work (saving, listing); let each round finish.
    for _ in range(3):
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def titles(pilot: Pilot[None]) -> list[str]:
    results = pilot.app.query_one(ResultsTable)
    return [str(results.get_cell(key, "title")) for key in results.rows]


def message(pilot: Pilot[None]) -> str:
    return str(pilot.app.screen.query_one("#source-message", Static).render())


def fill(pilot: Pilot[None], location: str | None, name: str, platform: str | None) -> None:
    screen = pilot.app.screen
    if location is not None:
        screen.query_one("#source-location", Input).value = location
    screen.query_one("#source-name", Input).value = name
    if platform is not None:
        screen.query_one("#source-platform", Select).value = platform


async def open_add_dialog(pilot: Pilot[None]) -> None:
    await settle(pilot)
    await pilot.click("#add-source")
    await pilot.pause()
    assert isinstance(pilot.app.screen, AddSourceDialog)


async def select(pilot: Pilot[None], source_id: str) -> None:
    await pilot.click(f"#source-{source_id} .source-name")
    await pilot.pause()


def row(pilot: Pilot[None], source_id: str) -> SourceRow:
    return pilot.app.query_one(f"#source-{source_id}", SourceRow)


def source_ids(world: World) -> list[str]:
    return [source.id for source in world.settings_store.settings.sources]


async def test_add_source_saves_and_refreshes(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await open_add_dialog(pilot)
        fill(pilot, NEW_LINK, "Homebrew Picks!", "nes")
        await pilot.click("#source-add")
        await settle(pilot)
        assert not isinstance(pilot.app.screen, AddSourceDialog)
        added = SourceConfig("homebrew-picks", "Homebrew Picks!", "fake", NEW_LINK, "nes")
        assert world.settings_store.settings.sources[-1] == added
        assert "Homebrew Picks! Game" in titles(pilot)
        assert pilot.app.query("#source-homebrew-picks")


async def test_added_source_id_is_unique(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await open_add_dialog(pilot)
        fill(pilot, NEW_LINK, MY_LIST.name, None)
        await pilot.click("#source-add")
        await settle(pilot)
        assert source_ids(world)[-1] == "my-list-2"


async def test_add_source_shows_error_when_undetected(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await open_add_dialog(pilot)
        fill(pilot, "https://example.com/unknown", "Unknown", None)
        await pilot.click("#source-add")
        await settle(pilot)
        assert isinstance(pilot.app.screen, AddSourceDialog)
        assert message(pilot) == UNDETECTED
        assert not pilot.app.screen.query_one("#source-add", Button).disabled
        assert source_ids(world) == [MY_LIST.id, OFF.id, HIDDEN.id]


async def test_empty_name_or_location_blocks_add(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await open_add_dialog(pilot)
        for location, name in ((NEW_LINK, "  "), ("", "Picks")):
            fill(pilot, location, name, None)
            await pilot.click("#source-add")
            await settle(pilot)
            assert isinstance(pilot.app.screen, AddSourceDialog)
            assert message(pilot) == "Enter a link or file path and a name."
        assert source_ids(world) == [MY_LIST.id, OFF.id, HIDDEN.id]


async def test_add_is_disabled_while_checking_and_cancel_closes(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await open_add_dialog(pilot)
        fill(pilot, SLOW_LINK, "Slow", None)
        await pilot.click("#source-add")
        await pilot.pause()
        assert pilot.app.screen.query_one("#source-add", Button).disabled
        assert message(pilot) == "Checking link…"
        await pilot.click("#source-cancel")
        await settle(pilot)
        assert not isinstance(pilot.app.screen, AddSourceDialog)
        assert source_ids(world) == [MY_LIST.id, OFF.id, HIDDEN.id]


async def test_palette_add_source_opens_dialog(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+p", *"add source")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, AddSourceDialog)


async def test_edit_changes_name_and_platform(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        await select(pilot, MY_LIST.id)
        await pilot.click("#edit-source")
        await pilot.pause()
        location = pilot.app.screen.query_one("#source-location", Input)
        assert location.value == MY_LIST.location
        assert location.disabled
        assert str(pilot.app.screen.query_one("#source-add", Button).label) == "Save"
        fill(pilot, None, "Renamed List", "gb")
        await pilot.click("#source-add")
        await settle(pilot)
        saved = world.settings_store.settings.sources[0]
        assert (saved.id, saved.name, saved.platform) == (MY_LIST.id, "Renamed List", "gb")
        assert (saved.kind, saved.location) == (MY_LIST.kind, MY_LIST.location)
        assert "Renamed List" in row(pilot, MY_LIST.id).text


async def test_builtin_source_cannot_be_edited_or_removed(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        await select(pilot, BUILTIN.id)
        assert pilot.app.query_one("#edit-source", Button).disabled
        assert pilot.app.query_one("#remove-source", Button).disabled
        assert not pilot.app.query_one("#toggle-source", Button).disabled


async def test_disable_builtin_hides_its_files_and_persists(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        await select(pilot, BUILTIN.id)
        await pilot.click("#toggle-source")
        await settle(pilot)
        assert titles(pilot) == ["Blade Buster"]
        assert BUILTIN.id in world.settings_store.settings.disabled_ids
        toggle = pilot.app.query_one("#toggle-source", Button)
        assert str(toggle.label) == "Enable"
        assert row(pilot, BUILTIN.id).text.endswith("(off)")
        await pilot.click("#toggle-source")
        await settle(pilot)
        assert "Tobu Tobu Girl" in titles(pilot)
        assert BUILTIN.id not in world.settings_store.settings.disabled_ids


async def test_enable_stale_user_source_lists_its_files(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        assert OFF.id not in world.catalog_store.catalogs
        await select(pilot, OFF.id)
        await pilot.click("#toggle-source")
        await settle(pilot)
        assert "Off Game" in titles(pilot)
        assert world.settings_store.settings.sources[1].enabled
        assert OFF.id in world.catalog_store.catalogs


async def test_enable_fresh_source_does_not_list_it_again(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        before = world.catalog_store.catalogs[MY_LIST.id].fetched_at
        await select(pilot, MY_LIST.id)
        await pilot.click("#toggle-source")
        await settle(pilot)
        await pilot.click("#toggle-source")
        await settle(pilot)
        assert "Blade Buster" in titles(pilot)
        assert world.catalog_store.catalogs[MY_LIST.id].fetched_at == before


async def test_refresh_lists_the_selected_source_and_keeps_it_shown(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        before = world.catalog_store.catalogs[MY_LIST.id].fetched_at
        builtin_before = world.catalog_store.catalogs[BUILTIN.id].fetched_at
        await select(pilot, MY_LIST.id)
        await pilot.click("#refresh-source")
        await settle(pilot)
        assert world.catalog_store.catalogs[MY_LIST.id].fetched_at > before
        assert world.catalog_store.catalogs[BUILTIN.id].fetched_at == builtin_before
        assert "Blade Buster" in titles(pilot)
        assert not row(pilot, MY_LIST.id).has_class("-hidden")


async def test_remove_asks_confirmation_and_forgets_cache(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await settle(pilot)
        await select(pilot, MY_LIST.id)
        await pilot.click("#remove-source")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ConfirmDialog)
        await pilot.click("#confirm-no")
        await settle(pilot)
        assert MY_LIST.id in source_ids(world)
        await select(pilot, MY_LIST.id)
        await pilot.click("#remove-source")
        await pilot.pause()
        await pilot.click("#confirm-yes")
        await settle(pilot)
        assert MY_LIST.id not in source_ids(world)
        assert MY_LIST.id not in world.catalog_store.catalogs
        assert "Blade Buster" not in titles(pilot)
        assert not pilot.app.query(f"#source-{MY_LIST.id}")
