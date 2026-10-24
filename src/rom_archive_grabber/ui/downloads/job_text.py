"""Text shown in the Downloads tab for job states, details and counts."""

from collections.abc import Iterable

from rom_archive_grabber.domain.models import DownloadJob, JobStatus
from rom_archive_grabber.ui.browse.formatting import NO_VALUE, format_size

RESTARTED_NOTE = "restarted (server can't resume)"

_STATUS = {
    JobStatus.DOWNLOADING: "↓ downloading",
    JobStatus.PAUSED: "❚❚ paused",
    JobStatus.QUEUED: "… queued",
    JobStatus.FAILED: "✖ failed",
    JobStatus.DONE: "✔ done",
}
_ACTIVE = (JobStatus.DOWNLOADING, JobStatus.PAUSED, JobStatus.FAILED)


def status_text(job: DownloadJob) -> str:
    return _STATUS[job.status]


def detail_text(job: DownloadJob) -> str:
    """The error of a failed job; size, platform and date of a finished one."""
    if job.status is JobStatus.FAILED:
        return job.error or "download failed"
    if job.status is not JobStatus.DONE:
        return ""
    size = format_size(job.bytes_total or job.file.size)
    when = job.finished_at.astimezone().date().isoformat() if job.finished_at else NO_VALUE
    return f"{size} · {job.file.platform.upper()} · {when}"


def speed_text(rate: float | None) -> str:
    return NO_VALUE if rate is None else f"{format_size(int(rate))}/s"


def footer_text(jobs: Iterable[DownloadJob], max_parallel: int) -> str:
    """`N active · N queued · N downloaded · max N at once`.

    Active jobs are the ones started and not finished: downloading, paused or failed.
    """
    statuses = [job.status for job in jobs]
    active = sum(1 for status in statuses if status in _ACTIVE)
    queued = statuses.count(JobStatus.QUEUED)
    done = statuses.count(JobStatus.DONE)
    return f"{active} active · {queued} queued · {done} downloaded · max {max_parallel} at once"
