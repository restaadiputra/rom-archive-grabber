from datetime import UTC, datetime
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import Button, Input, TabbedContent

from rom_archive_grabber.domain.models import DownloadJob, JobStatus
from rom_archive_grabber.ui.app import RomArchiveApp
from rom_archive_grabber.ui.browse.results_table import ResultsTable
from rom_archive_grabber.ui.browse.source_row import SourceRow
from rom_archive_grabber.ui.message_dialog import MessageDialog
from tests.ui.conftest import BUILTIN, FILES, MY_LIST, FakePluginWarning, World

# Wide enough that every column fits and header clicks land where expected.
SIZE = (160, 40)
ALL_TITLES = ["Tobu Tobu Girl", "Anguna", "Blade Buster"]


async def loaded(pilot: Pilot[None]) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def table(pilot: Pilot[None]) -> ResultsTable:
    return pilot.app.query_one(ResultsTable)


def titles(pilot: Pilot[None]) -> list[str]:
    results = table(pilot)
    return [str(results.get_cell(key, "title")) for key in results.rows]


def header_offset(results: ResultsTable, column: str) -> tuple[int, int]:
    x = 0
    for key, col in results.columns.items():
        if key.value == column:
            return x + 1, 0
        x += col.get_render_width(results)
    raise AssertionError(f"no column {column}")


async def test_shows_files_from_all_enabled_sources(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        assert titles(pilot) == ALL_TITLES


async def test_typing_in_search_filters_rows(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.click(Input)
        await pilot.press(*"tobu")
        await pilot.pause()
        assert titles(pilot) == ["Tobu Tobu Girl"]


async def test_space_and_d_in_search_are_typed_not_bound(world: World) -> None:
    services = world.services()
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.click(Input)
        await pilot.press(*"blade d")
        await pilot.pause()
        assert pilot.app.query_one(Input).value == "blade d"
        assert services.downloads.jobs() == []


async def test_clicking_title_header_sorts_then_reverses(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        offset = header_offset(table(pilot), "title")
        await pilot.click(ResultsTable, offset=offset)
        await pilot.pause()
        assert titles(pilot) == ["Anguna", "Blade Buster", "Tobu Tobu Girl"]
        assert str(table(pilot).columns[table(pilot).title_key].label) == "Title ▲"
        await pilot.click(ResultsTable, offset=offset)
        await pilot.pause()
        assert titles(pilot) == ["Tobu Tobu Girl", "Blade Buster", "Anguna"]
        assert str(table(pilot).columns[table(pilot).title_key].label) == "Title ▼"


async def test_platform_filter_limits_rows(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.click("#platform-gba")
        await pilot.pause()
        assert titles(pilot) == ["Anguna"]
        await pilot.click("#platform-all")
        await pilot.pause()
        assert titles(pilot) == ALL_TITLES


async def test_clicking_source_toggle_hides_then_shows_its_files(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        toggle = f"#source-{BUILTIN.id} .source-toggle"
        await pilot.click(toggle)
        await pilot.pause()
        assert titles(pilot) == ["Blade Buster"]
        assert pilot.app.query_one(f"#source-{BUILTIN.id}", SourceRow).text.startswith("○")
        await pilot.click(toggle)
        await pilot.pause()
        assert titles(pilot) == ALL_TITLES


async def test_clicking_source_name_selects_without_hiding(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.click(f"#source-{MY_LIST.id} .source-name")
        await pilot.pause()
        assert titles(pilot) == ALL_TITLES
        row = pilot.app.query_one(f"#source-{MY_LIST.id}", SourceRow)
        assert row.text == "● ▶ My List"
        assert row.has_class("-current")
        assert not row.has_class("-hidden")


async def test_space_and_enter_on_source_row_toggle_visibility(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        pilot.app.query_one(f"#source-{BUILTIN.id}", SourceRow).focus()
        await pilot.press("space")
        await pilot.pause()
        assert titles(pilot) == ["Blade Buster"]
        await pilot.press("enter")
        await pilot.pause()
        assert titles(pilot) == ALL_TITLES


async def test_space_marks_and_d_enqueues_marked(world: World) -> None:
    services = world.services()
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        table(pilot).focus()
        await pilot.press("space", "down", "down", "space", "d")
        await pilot.pause()
        queued = [job.file.title for job in services.downloads.jobs()]
        assert queued == ["Tobu Tobu Girl", "Blade Buster"]
        assert [str(table(pilot).get_cell(key, "mark")) for key in table(pilot).rows] == [""] * 3


async def test_d_without_marks_enqueues_cursor_row(world: World) -> None:
    services = world.services()
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        table(pilot).focus()
        await pilot.press("down", "d")
        await pilot.pause()
        assert [job.file.title for job in services.downloads.jobs()] == ["Anguna"]


async def test_details_panel_shows_open_folder_for_done_file(world: World) -> None:
    anguna = FILES[BUILTIN.id][1]
    dest = str(Path("downloads", "game-boy-advance", anguna.file_name))
    created = datetime(2025, 12, 1, tzinfo=UTC)
    world.jobs.append(DownloadJob("done-1", anguna, JobStatus.DONE, created, dest_path=dest))
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        table(pilot).focus()
        await pilot.press("down")
        await pilot.pause()
        assert str(table(pilot).get_cell(anguna.key, "status")) == "✔ have"
        assert not pilot.app.query_one("#download", Button).display
        assert pilot.app.query_one("#download-again", Button).display
        await pilot.click("#open-folder")
        assert world.opened == [Path("downloads", "game-boy-advance")]


async def test_failing_open_folder_button_shows_error(world: World) -> None:
    anguna = FILES[BUILTIN.id][1]
    created = datetime(2025, 12, 1, tzinfo=UTC)
    world.jobs.append(DownloadJob("done-1", anguna, JobStatus.DONE, created, dest_path="x/a.zip"))
    world.open_error = PermissionError("access denied")
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        table(pilot).focus()
        await pilot.press("down")
        await pilot.click("#open-folder")
        await pilot.pause()
        assert pilot.app.is_running
        assert any("access denied" in note.message for note in pilot.app._notifications)


async def test_tab_switches_to_downloads(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.press("tab")
        assert pilot.app.query_one(TabbedContent).active == "downloads"
        await pilot.press("tab")
        assert pilot.app.query_one(TabbedContent).active == "browse"


async def test_downloads_tab_label_counts_active_jobs(world: World) -> None:
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        tabs = pilot.app.query_one(TabbedContent)
        assert tabs.get_tab("downloads").label_text == "Downloads"
        table(pilot).focus()
        await pilot.press("d")
        await pilot.pause(0.4)
        assert tabs.get_tab("downloads").label_text == "Downloads (1 ↓)"
        assert str(table(pilot).get_cell(FILES[BUILTIN.id][0].key, "status")) == "↓ 25%"


async def test_plugin_warning_is_shown(world: World) -> None:
    world.warnings.append(FakePluginWarning(Path("plugins", "broken.py"), "boom"))
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        messages = [note.message for note in pilot.app._notifications]
        assert any("broken.py" in message and "boom" in message for message in messages)


async def test_startup_error_opens_dialog(world: World) -> None:
    world.startup_error = "settings.toml: bad value"
    async with RomArchiveApp(world.services()).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        assert isinstance(pilot.app.screen, MessageDialog)
        await pilot.click("#dialog-ok")
        assert not isinstance(pilot.app.screen, MessageDialog)


async def test_command_palette_downloads_cursor_row(world: World) -> None:
    services = world.services()
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await loaded(pilot)
        await pilot.press("ctrl+p")
        await pilot.press(*"download marked")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause()
        assert [job.file.title for job in services.downloads.jobs()] == ["Tobu Tobu Girl"]
