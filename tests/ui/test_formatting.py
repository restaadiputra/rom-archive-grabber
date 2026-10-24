from datetime import UTC, datetime

import pytest

from rom_archive_grabber.domain.models import DownloadJob, GameFile, JobStatus
from rom_archive_grabber.ui.browse.formatting import (
    downloads_tab_label,
    format_size,
    status_label,
)

FILE = GameFile("s", "Tobu Tobu Girl", "tobu.gb", "gb", 1, "https://example.com/tobu.gb")


def job(status: JobStatus, second: int = 0, done: int = 0, total: int | None = None) -> DownloadJob:
    created = datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC)
    return DownloadJob(f"j{second}", FILE, status, created, done, total)


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (None, "—"),
        (512, "512 B"),
        (262_144, "256 KB"),
        (393_216, "384 KB"),
        (4_194_304, "4.0 MB"),
        (1_610_612_736, "1.5 GB"),
    ],
)
def test_format_size(size: int | None, text: str) -> None:
    assert format_size(size) == text


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        (job(JobStatus.DONE), "✔ have"),
        (job(JobStatus.DOWNLOADING, done=42, total=100), "↓ 42%"),
        (job(JobStatus.DOWNLOADING), "↓"),
        (job(JobStatus.PAUSED), "❚❚"),
        (job(JobStatus.QUEUED), "…"),
        (job(JobStatus.FAILED), "✖ failed"),
    ],
)
def test_status_label(value: DownloadJob | None, text: str) -> None:
    assert status_label(value) == text


def test_downloads_tab_label_counts_running_jobs_only() -> None:
    assert downloads_tab_label([job(JobStatus.DONE), job(JobStatus.QUEUED, 1)]) == "Downloads"
    jobs = [job(JobStatus.DOWNLOADING), job(JobStatus.PAUSED, 1), job(JobStatus.DOWNLOADING, 2)]
    assert downloads_tab_label(jobs) == "Downloads (2 ↓)"
