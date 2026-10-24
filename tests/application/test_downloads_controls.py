from rom_archive_grabber.domain.models import JobStatus
from tests.application.download_fakes import (
    FakeDownloader,
    MemoryJobStore,
    make_file,
    make_job,
    make_manager,
    settle,
)


async def test_remove_only_drops_queued_or_failed_jobs() -> None:
    store = MemoryJobStore([make_job("failed", JobStatus.FAILED), make_job("done", JobStatus.DONE)])
    downloader = FakeDownloader()
    manager = make_manager(store, downloader, max_parallel=1)
    await manager.start()
    running, queued = manager.enqueue([make_file("a"), make_file("b")])
    await settle()

    for job_id in (running.id, queued.id, "job-failed", "job-done"):
        manager.remove(job_id)
    assert downloader.discarded == ["b", "failed"]

    assert [job.id for job in manager.jobs()] == ["job-done", running.id]
    assert [job.id for job in store.saved] == ["job-done", running.id]


async def test_pause_all_and_resume_all() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=1)
    await manager.start()
    jobs = manager.enqueue([make_file("a"), make_file("b")])
    await settle()

    manager.pause_all()
    await settle()
    assert [job.status for job in jobs] == [JobStatus.PAUSED, JobStatus.PAUSED]
    assert downloader.running == set()

    manager.resume_all()
    await settle()
    assert [job.status for job in jobs] == [JobStatus.DOWNLOADING, JobStatus.QUEUED]


async def test_set_max_parallel_clamps_and_starts_more() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=0)
    await manager.start()
    manager.enqueue([make_file("a"), make_file("b"), make_file("c")])
    await settle()
    assert downloader.running == {"a"}

    manager.set_max_parallel(3)
    await settle()
    assert downloader.running == {"a", "b", "c"}

    manager.set_max_parallel(1)
    await settle()
    assert downloader.running == {"a", "b", "c"}


async def test_on_change_fires_for_progress_and_status() -> None:
    downloader = FakeDownloader()
    store = MemoryJobStore()
    manager = make_manager(store, downloader, max_parallel=1)
    changes: list[int] = []
    manager.on_change = lambda: changes.append(store.save_count)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()
    saves_before_progress = store.save_count
    count_before = len(changes)

    downloader.release("a")
    await settle()

    assert job.bytes_done == 2
    assert job.bytes_total == 2
    assert len(changes) >= count_before + 2
    assert store.save_count == saves_before_progress + 1


async def test_shutdown_stops_tasks_and_saves_them_queued() -> None:
    downloader = FakeDownloader()
    store = MemoryJobStore()
    manager = make_manager(store, downloader, max_parallel=2)
    await manager.start()
    first, second, paused = manager.enqueue([make_file("a"), make_file("b"), make_file("c")])
    await settle()
    manager.pause(paused.id)
    await settle()

    await manager.shutdown()
    await settle()

    assert downloader.running == set()
    assert downloader.discarded == []
    assert store.status_of(first.id) is JobStatus.QUEUED
    assert store.status_of(second.id) is JobStatus.QUEUED
    assert store.status_of(paused.id) is JobStatus.PAUSED


async def test_queue_order_follows_start_now_and_max_parallel_is_clamped() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=0)
    await manager.start()
    a, b, c = manager.enqueue([make_file("a"), make_file("b"), make_file("c")])
    await settle()

    manager.start_now(c.id)
    manager.pause(b.id)

    assert manager.queue_order() == [a.id, c.id, b.id]
    assert manager.max_parallel == 1
