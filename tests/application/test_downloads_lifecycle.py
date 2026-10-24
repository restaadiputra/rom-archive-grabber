import asyncio

from rom_archive_grabber.domain.models import JobStatus
from tests.application.download_fakes import (
    FakeDownloader,
    MemoryJobStore,
    make_file,
    make_job,
    make_manager,
    settle,
)


async def test_stopped_run_that_errors_on_cancel_stays_paused() -> None:
    downloader = FakeDownloader()
    downloader.error_on_cancel = True
    store = MemoryJobStore()
    manager = make_manager(store, downloader)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()

    manager.pause(job.id)
    await settle()

    assert job.status is JobStatus.PAUSED
    assert job.error is None
    assert store.status_of(job.id) is JobStatus.PAUSED


async def test_resume_before_old_run_unwinds_keeps_new_run_and_limit() -> None:
    downloader = FakeDownloader()
    downloader.error_on_cancel = True
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=1)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()

    manager.pause(job.id)
    manager.resume(job.id)
    await settle()
    (other,) = manager.enqueue([make_file("b")])
    await settle()

    assert job.status is JobStatus.DOWNLOADING
    assert other.status is JobStatus.QUEUED
    assert downloader.active == 1

    downloader.release("a")
    await settle()
    assert manager.status_for(job.file.key) is JobStatus.DONE
    assert manager.status_for(other.file.key) is JobStatus.DOWNLOADING


async def test_shutdown_keeps_queued_when_cancel_errors() -> None:
    downloader = FakeDownloader()
    downloader.error_on_cancel = True
    store = MemoryJobStore()
    manager = make_manager(store, downloader)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()

    await manager.shutdown()
    await settle()

    assert store.status_of(job.id) is JobStatus.QUEUED
    assert job.error is None


async def test_shutdown_waits_for_tasks_already_stopping() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()

    manager.pause(job.id)
    await manager.shutdown()

    assert downloader.active == 0


async def test_cancel_right_after_pause_discards_once_unwound() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()

    manager.pause(job.id)
    manager.cancel(job.id)
    assert downloader.discarded == []
    await settle()

    assert downloader.discarded == ["a"]
    assert downloader.discarded_while_running == []


async def test_concurrent_delete_file_calls_remove_the_job_once() -> None:
    store = MemoryJobStore([make_job("a", JobStatus.DONE)])
    downloader = FakeDownloader()
    manager = make_manager(store, downloader)
    await manager.start()
    downloader.delete_gate.clear()

    deletes = [asyncio.create_task(manager.delete_file("job-a")) for _ in range(2)]
    await settle()
    downloader.delete_gate.set()
    await asyncio.gather(*deletes)

    assert downloader.deleted == ["a", "a"]
    assert manager.jobs() == []


async def test_paused_and_resumed_jobs_keep_created_at_order() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=1)
    await manager.start()
    _a, b, _c, d = manager.enqueue([make_file(name) for name in "abcd"])
    await settle()

    manager.start_now(d.id)
    for job_id in (b.id, d.id):
        manager.pause(job_id)
    for job_id in (d.id, b.id):
        manager.resume(job_id)

    for finished, expected in (("a", "b"), ("b", "c"), ("c", "d")):
        downloader.release(finished)
        await settle()
        assert downloader.running == {expected}


async def test_start_now_puts_the_most_recent_first() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=1)
    await manager.start()
    _a, b, c = manager.enqueue([make_file(name) for name in "abc"])
    await settle()

    manager.start_now(b.id)
    manager.start_now(c.id)

    for finished, expected in (("a", "c"), ("c", "b")):
        downloader.release(finished)
        await settle()
        assert downloader.running == {expected}
