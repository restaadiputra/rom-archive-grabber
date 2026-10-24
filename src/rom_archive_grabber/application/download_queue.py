"""Pure ordering rules for the download queue."""

from rom_archive_grabber.domain.models import DownloadJob, JobStatus

# A file with a job in one of these states is not enqueued a second time.
ACTIVE_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.PAUSED})


def requeue_interrupted(jobs: list[DownloadJob]) -> None:
    """A job saved mid-download was interrupted; it goes back in line."""
    for job in jobs:
        if job.status is JobStatus.DOWNLOADING:
            job.status = JobStatus.QUEUED


def next_queued(jobs: list[DownloadJob], front: list[str]) -> DownloadJob | None:
    """The job to start next: `front` ids (from "start now") first, then oldest queued."""
    queued = [job for job in jobs if job.status is JobStatus.QUEUED]
    by_id = {job.id: job for job in queued}
    for job_id in front:
        if job_id in by_id:
            return by_id[job_id]
    return min(queued, key=lambda job: job.created_at, default=None)


def queue_order(jobs: list[DownloadJob], front: list[str]) -> list[DownloadJob]:
    """Unfinished jobs as the queue serves them: downloading, then queued in the
    order `next_queued` would pick them, then paused, then failed."""

    def oldest_first(status: JobStatus) -> list[DownloadJob]:
        return sorted((job for job in jobs if job.status is status), key=lambda job: job.created_at)

    queued = oldest_first(JobStatus.QUEUED)
    by_id = {job.id: job for job in queued}
    pushed = [by_id[job_id] for job_id in front if job_id in by_id]
    waiting = [job for job in queued if job not in pushed]
    paused, failed = oldest_first(JobStatus.PAUSED), oldest_first(JobStatus.FAILED)
    return [*oldest_first(JobStatus.DOWNLOADING), *pushed, *waiting, *paused, *failed]


def latest_by_file(jobs: list[DownloadJob]) -> dict[str, DownloadJob]:
    """The newest job per file key; on equal times the one added last wins."""
    latest: dict[str, DownloadJob] = {}
    for job in jobs:
        current = latest.get(job.file.key)
        if current is None or job.created_at >= current.created_at:
            latest[job.file.key] = job
    return latest


def latest_for(jobs: list[DownloadJob], file_key: str) -> DownloadJob | None:
    """The newest job for a file; on equal times the one added last wins."""
    return latest_by_file(jobs).get(file_key)


def is_active(jobs: list[DownloadJob], file_key: str) -> bool:
    return any(job.file.key == file_key and job.status in ACTIVE_STATUSES for job in jobs)
