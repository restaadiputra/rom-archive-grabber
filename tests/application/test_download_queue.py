from rom_archive_grabber.application.download_queue import (
    latest_by_file,
    latest_for,
    next_queued,
    queue_order,
)
from rom_archive_grabber.domain.models import JobStatus
from tests.application.download_fakes import make_file, make_job


def test_latest_by_file_keeps_newest_job_per_file() -> None:
    old = make_job("tobu", JobStatus.DONE, seconds=1)
    new = make_job("tobu", JobStatus.QUEUED, seconds=2)
    other = make_job("ucity", JobStatus.FAILED)
    assert latest_by_file([new, other, old]) == {old.file.key: new, other.file.key: other}


def test_latest_by_file_prefers_the_job_added_last_on_equal_times() -> None:
    first = make_job("tobu", JobStatus.DONE)
    second = make_job("tobu", JobStatus.QUEUED)
    assert latest_by_file([first, second])[first.file.key] is second
    assert latest_for([first, second], make_file("tobu").key) is second


def test_queue_order_lists_unfinished_jobs_in_the_order_they_are_served() -> None:
    failed = make_job("failed", JobStatus.FAILED, seconds=1)
    paused = make_job("paused", JobStatus.PAUSED, seconds=2)
    late = make_job("late", JobStatus.QUEUED, seconds=9)
    old = make_job("old", JobStatus.QUEUED, seconds=3)
    pushed = make_job("pushed", JobStatus.QUEUED, seconds=8)
    running = make_job("running", JobStatus.DOWNLOADING, seconds=7)
    done = make_job("done", JobStatus.DONE, seconds=0)
    jobs = [failed, paused, late, old, pushed, running, done]

    order = queue_order(jobs, [pushed.id])

    assert order == [running, pushed, old, late, paused, failed]
    assert order[1] is next_queued(jobs, [pushed.id])
