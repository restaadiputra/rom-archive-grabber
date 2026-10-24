import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rom_archive_grabber.adapters.json_stores import JsonCatalogStore, JsonJobStore
from rom_archive_grabber.domain.models import CachedCatalog, DownloadJob, GameFile, JobStatus

FETCHED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_file() -> GameFile:
    return GameFile("a", "One", "one.zip", "nes", None, "https://example.com/one.zip")


def test_catalog_round_trip(tmp_path: Path) -> None:
    store = JsonCatalogStore(tmp_path / "catalogs")
    catalog = CachedCatalog([make_file()], FETCHED)
    store.save("a", catalog)
    loaded = store.load("a")
    assert loaded == catalog
    assert loaded is not None
    assert loaded.fetched_at.tzinfo is not None


def test_catalog_missing_is_none(tmp_path: Path) -> None:
    assert JsonCatalogStore(tmp_path).load("nope") is None


def test_corrupt_catalog_file_is_ignored_and_renamed(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{not json", encoding="utf-8")
    store = JsonCatalogStore(tmp_path)
    assert store.load("a") is None
    assert not (tmp_path / "a.json").exists()
    assert (tmp_path / "a.json.corrupt").exists()


def test_catalog_delete(tmp_path: Path) -> None:
    store = JsonCatalogStore(tmp_path)
    store.save("a", CachedCatalog([], FETCHED))
    store.delete("a")
    store.delete("a")
    assert store.load("a") is None


def test_job_store_round_trip(tmp_path: Path) -> None:
    store = JsonJobStore(tmp_path / "jobs.json")
    full = DownloadJob(
        "1",
        make_file(),
        JobStatus.FAILED,
        FETCHED,
        bytes_done=5,
        bytes_total=10,
        dest_path="/x/one.zip",
        error="bad",
        finished_at=FETCHED,
        resume_unsupported=True,
    )
    minimal = DownloadJob("2", make_file(), JobStatus.QUEUED, FETCHED)
    store.save([full, minimal])
    assert store.load() == [full, minimal]


def test_job_store_missing_and_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    store = JsonJobStore(path)
    assert store.load() == []
    path.write_text("[[", encoding="utf-8")
    assert store.load() == []
    assert path.with_name("jobs.json.corrupt").exists()


def test_job_save_failure_is_recorded_not_raised(tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    store = JsonJobStore(blocker / "jobs.json")
    store.save([])
    assert store.last_error is not None
    assert "Couldn't save the download queue" in store.last_error


def test_job_save_clears_the_error_once_it_works(tmp_path: Path) -> None:
    store = JsonJobStore(tmp_path / "jobs.json")
    store.last_error = "earlier failure"
    store.save([])
    assert store.last_error is None


def test_corrupt_file_that_cannot_be_renamed_is_still_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.json").write_text("{not json", encoding="utf-8")

    def refuse(src: object, dst: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", refuse)
    assert JsonCatalogStore(tmp_path).load("a") is None
