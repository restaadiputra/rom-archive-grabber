import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from rom_archive_grabber.domain.models import DownloadJob, JobStatus
from rom_archive_grabber.ui.dialogs.confirm import ConfirmDialog
from rom_archive_grabber.ui.downloads.job_list import JobList
from rom_archive_grabber.ui.downloads.job_row import JobRow
from rom_archive_grabber.ui.downloads.job_text import footer_text
from rom_archive_grabber.ui.folder_opener import open_folder_or_notify
from rom_archive_grabber.ui.services import AppServices


class DownloadsTab(Vertical):
    """Follow and control downloads: what runs and waits, and what is finished."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("p", "row('pause')", "Pause"),
        Binding("r", "row('resume')", "Resume"),
        Binding("x", "row('cancel')", "Cancel"),
        Binding("o", "row('open_folder')", "Open folder"),
    ]

    def __init__(self, services: AppServices) -> None:
        super().__init__(id="downloads-tab")
        self._services = services
        # The redraw timer and button handlers can both redraw; one at a time.
        self._lock = asyncio.Lock()
        self._current: JobList | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="downloads-header"):
            yield Static("Active", classes="heading")
            yield Button("Pause all", id="pause-all", compact=True)
            yield Button("Resume all", id="resume-all", compact=True)
        yield JobList(id="active-jobs")
        yield Static("Downloaded", classes="heading")
        yield JobList(id="done-jobs")
        yield Static("", id="downloads-footer", markup=False)

    async def on_mount(self) -> None:
        await self.refresh_jobs()

    def focus_list(self) -> None:
        self._current_list().focus()

    async def refresh_jobs(self) -> None:
        """Show the manager's jobs: unfinished ones in queue order, finished newest first."""
        async with self._lock:
            manager = self._services.downloads
            jobs = manager.jobs()
            by_id = {job.id: job for job in jobs}
            await self._list("#active-jobs").sync([by_id[i] for i in manager.queue_order()])
            done = [job for job in jobs if job.status is JobStatus.DONE]
            done.sort(key=lambda job: job.finished_at or job.created_at, reverse=True)
            await self._list("#done-jobs").sync(done)
            footer = footer_text(jobs, manager.max_parallel)
            self.query_one("#downloads-footer", Static).update(footer)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        if isinstance(event.widget, JobList):
            self._current = event.widget

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        manager = self._services.downloads
        if event.button.id == "pause-all":
            manager.pause_all()
        elif event.button.id == "resume-all":
            manager.resume_all()
        await self.refresh_jobs()

    async def on_job_row_action_pressed(self, event: JobRow.ActionPressed) -> None:
        await self._act(event.action, event.job)

    async def action_row(self, action: str) -> None:
        row = self._current_list().highlighted_row()
        if row is not None:
            await self._act(action, row.job)

    async def _act(self, action: str, job: DownloadJob) -> None:
        simple = self._job_actions().get(action)
        if simple is not None:
            simple(job.id)
        elif action == "open_folder":
            self._open_folder(job)
        elif action == "delete_file":
            self._confirm_delete(job)
        await self.refresh_jobs()

    def _job_actions(self) -> dict[str, Callable[[str], None]]:
        manager = self._services.downloads
        return {
            "pause": manager.pause,
            "resume": manager.resume,
            "start_now": manager.start_now,
            "retry": manager.retry,
            "cancel": manager.cancel,
            "remove": manager.remove,
        }

    def _open_folder(self, job: DownloadJob) -> None:
        if job.dest_path:
            folder = Path(job.dest_path).parent
            open_folder_or_notify(self.app, self._services.open_folder, folder)

    def _confirm_delete(self, job: DownloadJob) -> None:
        name = Path(job.dest_path).name if job.dest_path else job.file.file_name

        async def answered(yes: bool | None) -> None:
            if yes:
                await self._delete(job)

        self.app.push_screen(ConfirmDialog(f"Delete {name} from disk?"), answered)

    async def _delete(self, job: DownloadJob) -> None:
        try:
            await self._services.downloads.delete_file(job.id)
        except OSError as error:
            self.notify(f"Could not delete {job.file.file_name}: {error}", severity="error")
        await self.refresh_jobs()

    def _current_list(self) -> JobList:
        return self._current or self._list("#active-jobs")

    def _list(self, selector: str) -> JobList:
        return self.query_one(selector, JobList)
