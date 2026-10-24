from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from textual.pilot import Pilot
from textual.widgets import Button, Input, ProgressBar, Static, TabbedContent

from rom_archive_grabber.application.downloads import DownloadManager
from rom_archive_grabber.domain.models import DownloadJob, JobStatus
from rom_archive_grabber.ui.app import RomArchiveApp
from rom_archive_grabber.ui.dialogs.confirm import ConfirmDialog
from rom_archive_grabber.ui.downloads.job_list import JobList
from rom_archive_grabber.ui.downloads.job_row import JobRow
from tests.ui.conftest import BUILTIN, DOWNLOAD_DIR, World, game

SIZE = (160, 40)
# Noon, so the local date is the same in every time zone.
_AT = datetime(2025, 12, 1, 12, tzinfo=UTC)
DONE_PATH = DOWNLOAD_DIR / "game-boy" / "anguna.zip"
Call = tuple[object, ...]


def job(job_id: str, minute: int, status: JobStatus) -> DownloadJob:
    file = game(BUILTIN, f"Game {job_id}", "gb", 262_144)
    return DownloadJob(job_id, file, status, _AT + timedelta(minutes=minute))


def seeded(world: World) -> World:
    """Two jobs start downloading (max 2), one waits, plus one of each other state."""
    paused = job("paused", 4, JobStatus.PAUSED)
    paused.resume_unsupported = True
    failed = job("failed", 5, JobStatus.FAILED)
    failed.error = "link not found"
    done = job("done", 0, JobStatus.DONE)
    done.dest_path, done.bytes_total = str(DONE_PATH), 262_144
    done.finished_at = _AT
    queued = [job(job_id, minute, JobStatus.QUEUED) for minute, job_id in enumerate("abc", 1)]
    world.jobs = [failed, done, paused, *queued]
    return world


def record_calls(manager: DownloadManager, *names: str) -> list[Call]:
    """Wrap manager methods so each call is recorded, then passed on."""
    calls: list[Call] = []

    def wrap(name: str, method: Callable[..., object]) -> Callable[..., object]:
        def recorded(*args: object) -> object:
            calls.append((name, *args))
            return method(*args)

        return recorded

    for name in names:
        setattr(manager, name, wrap(name, getattr(manager, name)))
    return calls


async def open_downloads(pilot: Pilot[None]) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.press("tab")
    await pilot.pause()


def row(pilot: Pilot[None], job_id: str) -> JobRow:
    return pilot.app.query_one(f"#job-{job_id}", JobRow)


def buttons(pilot: Pilot[None], job_id: str) -> list[str]:
    return [str(button.label) for button in row(pilot, job_id).query(Button) if button.display]


def text(pilot: Pilot[None], selector: str) -> str:
    return str(pilot.app.screen.query_one(selector, Static).render())


def ids(pilot: Pilot[None], list_id: str) -> list[str]:
    return [item.job.id for item in pilot.app.query_one(list_id, JobList).query(JobRow)]


async def test_rows_show_buttons_for_each_status(world: World) -> None:
    async with RomArchiveApp(seeded(world).services()).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        assert ids(pilot, "#active-jobs") == ["a", "b", "c", "paused", "failed"]
        assert ids(pilot, "#done-jobs") == ["done"]
        assert buttons(pilot, "a") == ["❚❚ Pause", "✕ Cancel"]
        assert buttons(pilot, "paused") == ["▶ Resume", "✕ Cancel"]
        assert buttons(pilot, "c") == ["▶ Start now", "✕ Remove"]
        assert buttons(pilot, "failed") == ["↻ Retry", "✕ Remove"]
        assert buttons(pilot, "done") == ["Open folder", "Delete file"]
        assert text(pilot, "#job-a .job-status") == "↓ downloading"
        assert text(pilot, "#job-failed .job-detail") == "link not found"
        assert text(pilot, "#job-done .job-detail") == "256 KB · GB · 2025-12-01"
        assert text(pilot, "#job-paused .job-note") == "restarted (server can't resume)"
        assert not pilot.app.query_one("#job-a .job-note").display


async def test_clicking_pause_calls_manager(world: World) -> None:
    services = seeded(world).services()
    calls = record_calls(services.downloads, "pause", "start_now")
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        await pilot.click("#job-c .start-now")
        await pilot.click("#job-a .pause")
        await pilot.pause()
        assert calls == [("start_now", "c"), ("pause", "a")]
        assert buttons(pilot, "a") == ["▶ Resume", "✕ Cancel"]
        # The paused job leaves a slot, so the waiting one starts.
        assert buttons(pilot, "c") == ["❚❚ Pause", "✕ Cancel"]
        assert ids(pilot, "#active-jobs") == ["b", "c", "a", "paused", "failed"]


async def test_pause_all_and_resume_all(world: World) -> None:
    services = seeded(world).services()
    calls = record_calls(services.downloads, "pause_all", "resume_all")
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        await pilot.click("#pause-all")
        await pilot.pause()
        assert all(buttons(pilot, job_id)[0] == "▶ Resume" for job_id in "abc")
        await pilot.click("#resume-all")
        await pilot.pause()
        assert calls == [("pause_all",), ("resume_all",)]
        assert buttons(pilot, "paused") == ["▶ Start now", "✕ Remove"]


async def test_delete_file_requires_confirmation(world: World) -> None:
    services = seeded(world).services()
    calls = record_calls(services.downloads, "delete_file")
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        await pilot.click("#job-done .delete-file")
        await pilot.pause()
        assert isinstance(pilot.app.screen, ConfirmDialog)
        assert text(pilot, "#dialog-message") == "Delete anguna.zip from disk?"
        await pilot.click("#confirm-no")
        await pilot.pause()
        assert calls == []
        assert ids(pilot, "#done-jobs") == ["done"]

        await pilot.click("#job-done .delete-file")
        await pilot.pause()
        await pilot.click("#confirm-yes")
        await pilot.pause(0.2)
        assert calls == [("delete_file", "done")]
        assert ids(pilot, "#done-jobs") == []


async def test_open_folder_calls_opener_with_parent_folder(world: World) -> None:
    async with RomArchiveApp(seeded(world).services()).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        await pilot.click("#job-done .open-folder")
        await pilot.pause()
        assert world.opened == [DONE_PATH.parent]


async def test_open_folder_failure_is_reported(world: World) -> None:
    world.open_error = OSError("no file manager")
    async with RomArchiveApp(seeded(world).services()).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        await pilot.click("#job-done .open-folder")
        await pilot.pause()
        assert any("no file manager" in note.message for note in pilot.app._notifications)


async def test_tab_label_counts_active_downloads(world: World) -> None:
    async with RomArchiveApp(seeded(world).services()).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        tabs = pilot.app.query_one(TabbedContent)
        assert str(tabs.get_tab("downloads").label) == "Downloads (2 ↓)"
        await pilot.click("#pause-all")
        await pilot.pause(0.4)
        assert str(tabs.get_tab("downloads").label) == "Downloads"


async def test_footer_counts(world: World) -> None:
    async with RomArchiveApp(seeded(world).services()).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        footer = "#downloads-footer"
        assert text(pilot, footer) == "4 active · 1 queued · 1 downloaded · max 2 at once"
        await pilot.click("#job-failed .remove")
        await pilot.pause()
        assert text(pilot, footer) == "3 active · 1 queued · 1 downloaded · max 2 at once"


async def test_keys_act_on_the_highlighted_row_of_the_downloads_tab(world: World) -> None:
    services = seeded(world).services()
    calls = record_calls(services.downloads, "pause", "resume", "cancel")
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.click(Input)
        await pilot.press("p", "r", "x", "o")
        await pilot.pause()
        assert calls == []

        await open_downloads(pilot)
        # The highlight follows job "a" as pausing and resuming move it in the list.
        await pilot.press("p", "r", "down", "x")
        await pilot.pause()
        assert calls == [("pause", "a"), ("resume", "a"), ("cancel", "paused")]
        assert ids(pilot, "#active-jobs") == ["b", "c", "a", "failed"]

        await pilot.click("#job-done .job-title")
        await pilot.press("o")
        await pilot.pause()
        assert world.opened == [DONE_PATH.parent]


async def test_progress_updates_rows_in_place(world: World) -> None:
    services = seeded(world).services()
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await open_downloads(pilot)
        first = row(pilot, "a")
        running = next(job for job in services.downloads.jobs() if job.id == "a")
        running.bytes_done = 3
        notify = services.downloads.on_change
        assert notify is not None
        notify()
        await pilot.pause(0.4)
        assert row(pilot, "a") is first
        assert first.query_one(".job-progress", ProgressBar).percentage == 0.75


async def test_browse_keys_do_not_fire_on_the_downloads_tab(world: World) -> None:
    services = world.services()
    async with RomArchiveApp(services).run_test(size=SIZE) as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.click("#results")
        await open_downloads(pilot)
        await pilot.press("space", "d")
        await pilot.pause()
        assert services.downloads.jobs() == []
        await pilot.press("tab")
        await pilot.pause()
        assert pilot.app.focused is pilot.app.query_one("#results")
