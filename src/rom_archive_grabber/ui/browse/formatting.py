"""Text shown in the Browse tab for sizes, download states and labels."""

from collections.abc import Iterable

from rom_archive_grabber.domain.models import DownloadJob, JobStatus

_UNITS = ("KB", "MB", "GB", "TB")
_STEP = 1024
NO_VALUE = "—"


def format_size(size: int | None) -> str:
    """`256 KB`, `4.0 MB`: whole kilobytes, one decimal from megabytes up."""
    if size is None:
        return NO_VALUE
    if size < _STEP:
        return f"{size} B"
    value = size / _STEP
    unit = 0
    while value >= _STEP and unit < len(_UNITS) - 1:
        value /= _STEP
        unit += 1
    return f"{value:.0f} KB" if unit == 0 else f"{value:.1f} {_UNITS[unit]}"


def status_label(job: DownloadJob | None) -> str:
    if job is None:
        return ""
    match job.status:
        case JobStatus.DONE:
            return "✔ have"
        case JobStatus.DOWNLOADING:
            return _downloading(job)
        case JobStatus.PAUSED:
            return "❚❚"
        case JobStatus.QUEUED:
            return "…"
        case JobStatus.FAILED:
            return "✖ failed"


def _downloading(job: DownloadJob) -> str:
    if not job.bytes_total:
        return "↓"
    return f"↓ {job.bytes_done * 100 // job.bytes_total}%"


def downloads_tab_label(jobs: Iterable[DownloadJob]) -> str:
    running = sum(1 for job in jobs if job.status is JobStatus.DOWNLOADING)
    return f"Downloads ({running} ↓)" if running else "Downloads"
