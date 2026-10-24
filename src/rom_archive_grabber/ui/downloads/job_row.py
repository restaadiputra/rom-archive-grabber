import time
from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, ListItem, ProgressBar, Static

from rom_archive_grabber.domain.models import DownloadJob, JobStatus
from rom_archive_grabber.ui.downloads.job_text import (
    RESTARTED_NOTE,
    detail_text,
    speed_text,
    status_text,
)
from rom_archive_grabber.ui.downloads.speed_meter import SpeedMeter

# Every button a row can show, in display order; the status picks which.
_BUTTONS = (
    ("pause", "❚❚ Pause"),
    ("resume", "▶ Resume"),
    ("start_now", "▶ Start now"),
    ("retry", "↻ Retry"),
    ("cancel", "✕ Cancel"),
    ("remove", "✕ Remove"),
    ("open_folder", "Open folder"),
    ("delete_file", "Delete file"),
)
_SHOWN = {
    JobStatus.DOWNLOADING: {"pause", "cancel"},
    JobStatus.PAUSED: {"resume", "cancel"},
    JobStatus.QUEUED: {"start_now", "remove"},
    JobStatus.FAILED: {"retry", "remove"},
    JobStatus.DONE: {"open_folder", "delete_file"},
}
# Failed and finished jobs show a line of text where the progress would be.
_WITH_DETAIL = (JobStatus.FAILED, JobStatus.DONE)


class JobRow(ListItem):
    """One download: title, state, progress, speed and the actions its state allows.

    The row is updated in place as the job changes, so it keeps its highlight
    and its speed history across redraws.
    """

    class ActionPressed(Message):
        """A row button was pressed; `action` names it, such as `pause`."""

        def __init__(self, job: DownloadJob, action: str) -> None:
            super().__init__()
            self.job = job
            self.action = action

    def __init__(self, job: DownloadJob, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(id=f"job-{job.id}")
        self.job = job
        self._clock = clock
        self._meter = SpeedMeter()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(self.job.file.title, classes="job-title", markup=False)
            yield Static(RESTARTED_NOTE, classes="job-note", markup=False)
            yield Static("", classes="job-status", markup=False)
            yield ProgressBar(classes="job-progress", show_eta=False)
            yield Static("", classes="job-detail", markup=False)
            yield Static("", classes="job-speed", markup=False)
            with Horizontal(classes="job-actions"):
                for action, label in _BUTTONS:
                    # Keys act on the highlighted row, so focus stays on the list.
                    classes = action.replace("_", "-")
                    button = Button(label, name=action, classes=classes, compact=True)
                    button.can_focus = False
                    yield button

    def on_mount(self) -> None:
        self.show(self.job)

    def show(self, job: DownloadJob) -> None:
        self.job = job
        status = job.status
        self._static(".job-note").display = job.resume_unsupported and status is not JobStatus.DONE
        self._static(".job-status").update(status_text(job))
        has_detail = status in _WITH_DETAIL
        self._static(".job-detail").display = has_detail
        self._static(".job-detail").update(detail_text(job))
        self.query_one(ProgressBar).display = not has_detail
        self._static(".job-speed").display = not has_detail
        self._show_progress(job)
        shown = _SHOWN[status]
        for button in self.query(Button):
            button.display = button.name in shown

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.name:
            self.post_message(self.ActionPressed(self.job, event.button.name))

    def _show_progress(self, job: DownloadJob) -> None:
        total, progress = job.bytes_total or job.file.size, job.bytes_done
        if job.status is JobStatus.DOWNLOADING:
            self._meter.add(self._clock(), job.bytes_done)
            rate = self._meter.rate()
        else:
            self._meter.reset()
            rate = None
        # An unknown size animates while downloading and shows empty otherwise.
        if total is None and job.status is not JobStatus.DOWNLOADING:
            total, progress = 1, 0
        self.query_one(ProgressBar).update(total=total, progress=progress)
        self._static(".job-speed").update(speed_text(rate))

    def _static(self, selector: str) -> Static:
        return self.query_one(selector, Static)
