import asyncio
import dataclasses
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rom_archive_grabber.application.downloads import (
    DownloadConfig,
    DownloadDeps,
    DownloadManager,
)
from rom_archive_grabber.application.platforms import PlatformCatalog
from rom_archive_grabber.domain.models import DownloadJob, GameFile, JobStatus, Platform
from rom_archive_grabber.domain.ports import DownloadError, ProgressFn

DOWNLOAD_DIR = Path("downloads")
_START = datetime(2026, 1, 1, tzinfo=UTC)


class FakeClock:
    """Each call is one second later, so jobs get distinct `created_at` values."""

    def __init__(self) -> None:
        self._ticks = 0

    def now(self) -> datetime:
        self._ticks += 1
        return _START + timedelta(seconds=self._ticks)


class MemoryJobStore:
    def __init__(self, jobs: list[DownloadJob] | None = None) -> None:
        self.saved: list[DownloadJob] = list(jobs or [])
        self.save_count = 0
        self.last_error: str | None = None

    def load(self) -> list[DownloadJob]:
        return [dataclasses.replace(job) for job in self.saved]

    def save(self, jobs: list[DownloadJob]) -> None:
        self.saved = [dataclasses.replace(job) for job in jobs]
        self.save_count += 1

    def status_of(self, job_id: str) -> JobStatus | None:
        return next((job.status for job in self.saved if job.id == job_id), None)


class FakeDownloader:
    """Each download waits on a per-title event; `fail` makes it raise instead.

    With `error_on_cancel`, cancellation surfaces as a DownloadError, the way a
    stream that fails to close while unwinding would.
    """

    def __init__(self) -> None:
        self.gates: dict[str, asyncio.Event] = {}
        self.failures: dict[str, Exception] = {}
        self.started: list[str] = []
        self.running: set[str] = set()
        self.folders: list[Path] = []
        self.discarded: list[str] = []
        self.deleted: list[str] = []
        self.error_on_cancel = False
        # `delete_file` runs in a worker thread; clearing this holds it there.
        self.delete_gate = threading.Event()
        self.delete_gate.set()
        self.active = 0
        self.discarded_while_running: list[str] = []

    def release(self, title: str) -> None:
        self._gate(title).set()

    def fail(self, title: str, error: Exception) -> None:
        self.failures[title] = error
        self.release(title)

    async def download(self, job: DownloadJob, folder: Path, on_progress: ProgressFn) -> None:
        title = job.file.title
        self.started.append(title)
        self.folders.append(folder)
        self.running.add(title)
        self.active += 1
        try:
            on_progress(1, 2)
            await self._wait(title)
            on_progress(2, 2)
        finally:
            self.running.discard(title)
            self.active -= 1

    async def _wait(self, title: str) -> None:
        try:
            await self._gate(title).wait()
        except asyncio.CancelledError:
            if self.error_on_cancel:
                raise DownloadError("stream closed while cancelling") from None
            raise
        if title in self.failures:
            raise self.failures.pop(title)

    def discard_partial(self, job: DownloadJob) -> None:
        self.discarded.append(job.file.title)
        if job.file.title in self.running:
            self.discarded_while_running.append(job.file.title)

    def delete_file(self, job: DownloadJob) -> None:
        self.delete_gate.wait(timeout=5)
        self.deleted.append(job.file.title)

    def _gate(self, title: str) -> asyncio.Event:
        return self.gates.setdefault(title, asyncio.Event())


def make_file(title: str, platform: str = "gb") -> GameFile:
    return GameFile(
        source_id="s1",
        title=title,
        file_name=f"{title}.zip",
        platform=platform,
        size=2,
        url=f"https://example.com/{title}.zip",
    )


def make_job(title: str, status: JobStatus, seconds: int = 0) -> DownloadJob:
    return DownloadJob(
        id=f"job-{title}",
        file=make_file(title),
        status=status,
        created_at=_START - timedelta(hours=1) + timedelta(seconds=seconds),
    )


def make_manager(
    store: MemoryJobStore, downloader: FakeDownloader, max_parallel: int = 2
) -> DownloadManager:
    platforms = PlatformCatalog(
        [Platform("gb", "Game Boy", "gameboy"), Platform("other", "Other", "other")]
    )
    deps = DownloadDeps(downloader, store, platforms, FakeClock())
    return DownloadManager(deps, DownloadConfig(DOWNLOAD_DIR, max_parallel))


async def settle() -> None:
    """Let started tasks run until they block on their gates."""
    for _ in range(20):
        await asyncio.sleep(0)
