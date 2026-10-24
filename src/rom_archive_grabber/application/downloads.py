import asyncio
import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from rom_archive_grabber.application import download_queue
from rom_archive_grabber.application.download_queue import is_active, latest_for, next_queued
from rom_archive_grabber.application.download_tasks import DownloadTasks
from rom_archive_grabber.application.platforms import PlatformCatalog
from rom_archive_grabber.domain.models import DownloadJob, GameFile, JobStatus
from rom_archive_grabber.domain.ports import Clock, Downloader, JobStore, ProgressFn


@dataclass(frozen=True, slots=True)
class DownloadConfig:
    download_dir: Path
    max_parallel: int


@dataclass(frozen=True, slots=True)
class DownloadDeps:
    downloader: Downloader
    store: JobStore
    platforms: PlatformCatalog
    clock: Clock


class DownloadManager:
    """Queue of download jobs, run as asyncio tasks up to `max_parallel` at once.

    Every status change is saved through the job store; progress only notifies.
    """

    def __init__(self, deps: DownloadDeps, config: DownloadConfig) -> None:
        self._deps = deps
        self._download_dir = config.download_dir
        self._max_parallel = max(1, config.max_parallel)
        self._jobs: list[DownloadJob] = []
        self._tasks = DownloadTasks()
        # Ids moved to the head of the queue by `start_now`, most recent first.
        self._front: list[str] = []
        self._started = False
        self._closed = False
        self.on_change: Callable[[], None] | None = None

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        loaded = self._deps.store.load()
        download_queue.requeue_interrupted(loaded)
        self._jobs[:0] = loaded
        self._commit()

    async def shutdown(self) -> None:
        """Stop running downloads, keeping their `.part` files, and save them as queued."""
        self._closed = True
        self._tasks.stop_all()
        download_queue.requeue_interrupted(self._jobs)
        await self._tasks.wait_stopped()
        self._deps.store.save(self._jobs)

    @property
    def storage_error(self) -> str | None:
        """Why the queue could not be saved, or None while saving works."""
        return self._deps.store.last_error

    def jobs(self) -> list[DownloadJob]:
        return list(self._jobs)

    def queue_order(self) -> list[str]:
        """Ids of unfinished jobs in the order the queue serves them."""
        return [job.id for job in download_queue.queue_order(self._jobs, self._front)]

    @property
    def max_parallel(self) -> int:
        return self._max_parallel

    def status_for(self, file_key: str) -> JobStatus | None:
        job = latest_for(self._jobs, file_key)
        return None if job is None else job.status

    def set_max_parallel(self, n: int) -> None:
        # Lowering the limit lets running jobs finish; it never pauses them.
        self._max_parallel = max(1, n)
        self._commit()

    def enqueue(self, files: Iterable[GameFile]) -> list[DownloadJob]:
        added: list[DownloadJob] = []
        for file in files:
            if is_active(self._jobs, file.key):
                continue
            job = DownloadJob(uuid4().hex, file, JobStatus.QUEUED, self._deps.clock.now())
            self._jobs.append(job)
            added.append(job)
        if added:
            self._commit()
        return added

    def pause(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is not None and self._pause_job(job):
            self._commit()

    def resume(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is not None and job.status is JobStatus.PAUSED:
            job.status = JobStatus.QUEUED
            self._commit()

    def start_now(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is None or job.status is not JobStatus.QUEUED:
            return
        self._drop_front(job_id)
        self._front.insert(0, job_id)
        self._commit()

    def retry(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is not None and job.status is JobStatus.FAILED:
            job.status = JobStatus.QUEUED
            job.error = None
            self._commit()

    def cancel(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is None or job.status is JobStatus.DONE:
            return
        self._forget(job)
        self._tasks.stop(job.id)
        self._discard_when_stopped(job)
        self._commit()

    def remove(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is not None and job.status in (JobStatus.QUEUED, JobStatus.FAILED):
            self._forget(job)
            # The downloader reserves the .part as soon as a job starts; left
            # behind, it would block the file name.
            self._discard_when_stopped(job)
            self._commit()

    def pause_all(self) -> None:
        changed = [self._pause_job(job) for job in list(self._jobs)]
        if any(changed):
            self._commit()

    def resume_all(self) -> None:
        paused = [job for job in self._jobs if job.status is JobStatus.PAUSED]
        for job in paused:
            job.status = JobStatus.QUEUED
        if paused:
            self._commit()

    async def delete_file(self, job_id: str) -> None:
        job = self._find(job_id)
        if job is None or job.status is not JobStatus.DONE:
            return
        # Deleting a large file can block, so it runs off the event loop.
        await asyncio.to_thread(self._deps.downloader.delete_file, job)
        # Another call may have removed the job while the file was deleted.
        if self._find(job_id) is job:
            self._forget(job)
            self._commit()

    def _find(self, job_id: str) -> DownloadJob | None:
        return next((job for job in self._jobs if job.id == job_id), None)

    def _forget(self, job: DownloadJob) -> None:
        self._jobs.remove(job)
        self._drop_front(job.id)

    def _drop_front(self, job_id: str) -> None:
        if job_id in self._front:
            self._front.remove(job_id)

    def _pause_job(self, job: DownloadJob) -> bool:
        if job.status not in (JobStatus.QUEUED, JobStatus.DOWNLOADING):
            return False
        self._tasks.stop(job.id)
        self._drop_front(job.id)
        job.status = JobStatus.PAUSED
        return True

    def _discard_when_stopped(self, job: DownloadJob) -> None:
        # A stopping task may still hold the .part open, and Windows cannot
        # delete an open file, so the discard waits for it to unwind.
        self._tasks.when_stopped(job.id, lambda: self._discard_partial(job))

    def _discard_partial(self, job: DownloadJob) -> None:
        # A failed discard must not undo the cancel or remove that asked for
        # it, and this can run as a task callback where an exception would
        # only reach the loop's log.
        with contextlib.suppress(OSError):
            self._deps.downloader.discard_partial(job)

    def _commit(self) -> None:
        """Start whatever now fits, then save and notify."""
        self._schedule()
        self._deps.store.save(self._jobs)
        self._notify()

    def _schedule(self) -> None:
        if not self._started or self._closed:
            return
        while len(self._tasks) < self._max_parallel:
            job = next_queued(self._jobs, self._front)
            if job is None:
                return
            self._drop_front(job.id)
            job.status = JobStatus.DOWNLOADING
            self._tasks.start(job.id, self._run(job))

    async def _run(self, job: DownloadJob) -> None:
        message: str | None = None
        try:
            folder = self._download_dir / self._deps.platforms.get(job.file.platform).folder
            await self._deps.downloader.download(job, folder, self._progress_for(job))
        except Exception as error:
            # DownloadError, HttpError and OSError are the expected failures, but
            # a plugin's odd URL can raise anything, and one bad job must never
            # stop the scheduler. Pause and cancel still work: CancelledError is
            # not an Exception, so it passes through untouched.
            outcome, message = JobStatus.FAILED, str(error) or type(error).__name__
        else:
            outcome = JobStatus.DONE
        # A stopped run can still end here when the downloader turns its
        # cancellation into an error; it must not overwrite the newer state.
        if not self._tasks.is_current(job.id):
            return
        self._tasks.finish(job.id)
        job.status, job.error = outcome, message
        if outcome is JobStatus.DONE:
            job.finished_at = self._deps.clock.now()
        self._commit()

    def _progress_for(self, job: DownloadJob) -> ProgressFn:
        def on_progress(done: int, total: int | None) -> None:
            job.bytes_done = done
            job.bytes_total = total
            self._notify()

        return on_progress

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()
