from dataclasses import dataclass

from rom_archive_grabber.application.platforms import PlatformCatalog
from rom_archive_grabber.domain.models import DownloadJob, GameFile, JobStatus
from rom_archive_grabber.ui.browse.details_panel import DetailsView
from rom_archive_grabber.ui.browse.formatting import format_size, status_label
from rom_archive_grabber.ui.browse.results_table import RowView

MARK = "●"


@dataclass(frozen=True, slots=True)
class RowContext:
    """What a row needs besides its file: marks, latest jobs, source names, platforms."""

    marked: set[str]
    jobs: dict[str, DownloadJob]
    source_names: dict[str, str]
    platforms: PlatformCatalog

    def row(self, file: GameFile) -> RowView:
        cells = (
            MARK if file.key in self.marked else "",
            file.title,
            self.platforms.get(file.platform).label,
            format_size(file.size),
            self._source_name(file),
            status_label(self.jobs.get(file.key)),
        )
        return RowView(file.key, cells)

    def details(self, file: GameFile) -> DetailsView:
        job = self.jobs.get(file.key)
        status = None if job is None else job.status
        return DetailsView(
            title=file.title,
            file_name=file.file_name,
            size=format_size(file.size),
            source_name=self._source_name(file),
            status=status,
            status_text=_status_detail(job),
        )

    def _source_name(self, file: GameFile) -> str:
        return self.source_names.get(file.source_id, file.source_id)


def _status_detail(job: DownloadJob | None) -> str:
    if job is None:
        return ""
    if job.status is JobStatus.FAILED:
        return job.error or ""
    if job.status is JobStatus.DOWNLOADING and job.bytes_total:
        return f"{job.bytes_done * 100 // job.bytes_total}%"
    return ""
