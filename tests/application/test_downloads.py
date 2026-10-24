from rom_archive_grabber.domain.models import JobStatus
from rom_archive_grabber.domain.ports import DownloadError, HttpError
from tests.application.download_fakes import (
    DOWNLOAD_DIR,
    FakeDownloader,
    MemoryJobStore,
    make_file,
    make_job,
    make_manager,
    settle,
)


async def test_runs_at_most_max_parallel() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=2)
    await manager.start()

    manager.enqueue([make_file("a"), make_file("b"), make_file("c")])
    await settle()
    assert downloader.running == {"a", "b"}

    downloader.release("a")
    await settle()
    assert downloader.running == {"b", "c"}
    assert manager.status_for(make_file("a").key) is JobStatus.DONE
    assert downloader.folders[0] == DOWNLOAD_DIR / "gameboy"


async def test_pause_then_resume_requeues() -> None:
    downloader = FakeDownloader()
    store = MemoryJobStore()
    manager = make_manager(store, downloader, max_parallel=1)
    await manager.start()
    first, second = manager.enqueue([make_file("a"), make_file("b")])
    await settle()

    manager.pause(first.id)
    await settle()
    assert first.status is JobStatus.PAUSED
    assert store.status_of(first.id) is JobStatus.PAUSED
    assert downloader.running == {"b"}

    manager.resume(first.id)
    assert manager.status_for(first.file.key) is JobStatus.QUEUED
    downloader.release("b")
    await settle()
    assert downloader.running == {"a"}
    assert second.status is JobStatus.DONE


async def test_start_now_runs_next_without_exceeding_limit() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=1)
    await manager.start()
    a, _b, c = manager.enqueue([make_file("a"), make_file("b"), make_file("c")])
    await settle()

    manager.start_now(c.id)
    await settle()
    assert downloader.running == {"a"}
    assert a.status is JobStatus.DOWNLOADING
    assert c.status is JobStatus.QUEUED

    downloader.release("a")
    await settle()
    assert downloader.running == {"c"}


async def test_failure_marks_failed_and_retry_requeues() -> None:
    downloader = FakeDownloader()
    store = MemoryJobStore()
    manager = make_manager(store, downloader, max_parallel=1)
    await manager.start()
    (job,) = manager.enqueue([make_file("a")])
    await settle()

    downloader.fail("a", HttpError("https://example.com/a.zip", 404))
    await settle()
    assert job.status is JobStatus.FAILED
    assert job.error == "HTTP 404: https://example.com/a.zip"
    assert store.status_of(job.id) is JobStatus.FAILED

    downloader.gates.clear()
    manager.retry(job.id)
    await settle()
    assert job.error is None
    assert job.status is JobStatus.DOWNLOADING
    assert downloader.started == ["a", "a"]


async def test_unexpected_errors_fail_the_job_and_scheduling_continues() -> None:
    downloader = FakeDownloader()
    manager = make_manager(MemoryJobStore(), downloader, max_parallel=1)
    await manager.start()
    first, second = manager.enqueue([make_file("a"), make_file("b")])
    await settle()

    downloader.fail("a", ValueError("bad url"))
    await settle()
    assert first.status is JobStatus.FAILED
    assert first.error == "bad url"
    assert second.status is JobStatus.DOWNLOADING

    downloader.fail("b", DownloadError("download ended early"))
    await settle()
    assert second.error == "download ended early"


async def test_cancel_removes_job_and_part_file() -> None:
    downloader = FakeDownloader()
    store = MemoryJobStore()
    manager = make_manager(store, downloader, max_parallel=1)
    await manager.start()
    running, queued = manager.enqueue([make_file("a"), make_file("b")])
    await settle()

    manager.cancel(running.id)
    manager.cancel(queued.id)
    await settle()

    assert manager.jobs() == []
    assert store.saved == []
    assert downloader.running == set()
    assert sorted(downloader.discarded) == ["a", "b"]


async def test_downloading_jobs_become_queued_on_load() -> None:
    store = MemoryJobStore(
        [
            make_job("a", JobStatus.DOWNLOADING, seconds=1),
            make_job("b", JobStatus.DOWNLOADING, seconds=2),
            make_job("c", JobStatus.PAUSED, seconds=0),
        ]
    )
    downloader = FakeDownloader()
    manager = make_manager(store, downloader, max_parallel=1)

    await manager.start()
    await manager.start()
    await settle()

    assert downloader.started == ["a"]
    assert [job.status for job in manager.jobs()] == [
        JobStatus.DOWNLOADING,
        JobStatus.QUEUED,
        JobStatus.PAUSED,
    ]


async def test_enqueue_skips_active_duplicates_but_allows_done() -> None:
    store = MemoryJobStore([make_job("done", JobStatus.DONE), make_job("paused", JobStatus.PAUSED)])
    manager = make_manager(store, FakeDownloader())
    await manager.start()

    added = manager.enqueue([make_file("done"), make_file("paused"), make_file("new")])
    again = manager.enqueue([make_file("new")])

    assert [job.file.title for job in added] == ["done", "new"]
    assert again == []
    assert len(manager.jobs()) == 4


async def test_delete_file_removes_file_and_history() -> None:
    store = MemoryJobStore([make_job("a", JobStatus.DONE), make_job("b", JobStatus.QUEUED)])
    downloader = FakeDownloader()
    manager = make_manager(store, downloader, max_parallel=1)
    await manager.start()

    await manager.delete_file("job-a")
    await manager.delete_file("job-b")

    assert downloader.deleted == ["a"]
    assert [job.id for job in store.saved] == ["job-b"]


async def test_status_for_reports_latest() -> None:
    store = MemoryJobStore([make_job("a", JobStatus.DONE)])
    manager = make_manager(store, FakeDownloader())
    await manager.start()
    key = make_file("a").key
    assert manager.status_for(key) is JobStatus.DONE
    assert manager.status_for("missing") is None

    manager.enqueue([make_file("a")])
    await settle()
    assert manager.status_for(key) is JobStatus.DOWNLOADING
