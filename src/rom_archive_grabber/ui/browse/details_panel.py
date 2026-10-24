from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from rom_archive_grabber.application.download_queue import ACTIVE_STATUSES
from rom_archive_grabber.domain.models import JobStatus


@dataclass(frozen=True, slots=True)
class DetailsView:
    title: str
    file_name: str
    size: str
    source_name: str
    status: JobStatus | None
    status_text: str


_STATUS_TEXT = {
    JobStatus.DONE: "Downloaded",
    JobStatus.DOWNLOADING: "Downloading",
    JobStatus.PAUSED: "Paused",
    JobStatus.QUEUED: "Queued",
    JobStatus.FAILED: "Download failed",
}


class DetailsPanel(Vertical):
    """Right column: the file under the cursor and what can be done with it."""

    def compose(self) -> ComposeResult:
        yield Static("Nothing selected", id="detail-title", classes="heading", markup=False)
        yield Static("", id="detail-file", markup=False)
        yield Static("", id="detail-source", markup=False)
        yield Static("", id="detail-status", markup=False)
        with Horizontal(id="detail-actions"):
            yield Button("Download", id="download", compact=True)
            yield Button("Open folder", id="open-folder", compact=True)
            yield Button("Download again", id="download-again", compact=True)

    def show(self, view: DetailsView | None) -> None:
        self.query_one("#detail-actions").display = view is not None
        if view is None:
            self._set("#detail-title", "Nothing selected")
            for selector in ("#detail-file", "#detail-source", "#detail-status"):
                self._set(selector, "")
            return
        self._set("#detail-title", view.title)
        self._set("#detail-file", f"{view.file_name} · {view.size}")
        self._set("#detail-source", f"from: {view.source_name}")
        status = _STATUS_TEXT.get(view.status, "") if view.status else ""
        self._set("#detail-status", f"{status} {view.status_text}".strip() if status else "")
        self.query_one("#detail-status").set_class(view.status is JobStatus.DONE, "-done")
        self._show_buttons(view.status)

    def _show_buttons(self, status: JobStatus | None) -> None:
        done = status is JobStatus.DONE
        download = self.query_one("#download", Button)
        download.display = not done
        # A file already waiting or downloading cannot be added again.
        download.disabled = status in ACTIVE_STATUSES
        self.query_one("#open-folder").display = done
        self.query_one("#download-again").display = done

    def _set(self, selector: str, text: str) -> None:
        self.query_one(selector, Static).update(text)
