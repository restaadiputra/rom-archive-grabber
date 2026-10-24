import contextlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from rom_archive_grabber.adapters.atomic_write import write_atomic
from rom_archive_grabber.domain.models import CachedCatalog, DownloadJob, GameFile, JobStatus


class JsonCatalogStore:
    """One `<source_id>.json` file per source under `folder`."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def load(self, source_id: str) -> CachedCatalog | None:
        return _read_json(self._path(source_id), _catalog_from_dict)

    def save(self, source_id: str, catalog: CachedCatalog) -> None:
        document = {
            "fetched_at": catalog.fetched_at.isoformat(),
            "files": [_file_to_dict(item) for item in catalog.files],
        }
        write_atomic(self._path(source_id), json.dumps(document))

    def delete(self, source_id: str) -> None:
        self._path(source_id).unlink(missing_ok=True)

    def _path(self, source_id: str) -> Path:
        return self._folder / f"{source_id}.json"


class JsonJobStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.last_error: str | None = None

    def load(self) -> list[DownloadJob]:
        jobs = _read_json(self._path, _jobs_from_list)
        return jobs if jobs is not None else []

    def save(self, jobs: list[DownloadJob]) -> None:
        try:
            write_atomic(self._path, json.dumps([_job_to_dict(job) for job in jobs]))
        except OSError as exc:
            # The queue lives on in memory; a full disk must not stop the app.
            self.last_error = f"Couldn't save the download queue: {exc}"
        else:
            self.last_error = None


_T = TypeVar("_T")


def _read_json(path: Path, parse: Callable[[Any], _T]) -> _T | None:
    """Parse `path`; an unreadable file is moved aside and treated as missing."""
    if not path.exists():
        return None
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError, OSError):
        with contextlib.suppress(OSError):
            os.replace(path, path.with_name(path.name + ".corrupt"))
        return None


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _file_to_dict(item: GameFile) -> dict[str, Any]:
    return {
        "source_id": item.source_id,
        "title": item.title,
        "file_name": item.file_name,
        "platform": item.platform,
        "size": item.size,
        "url": item.url,
    }


def _file_from_dict(data: dict[str, Any]) -> GameFile:
    return GameFile(
        source_id=data["source_id"],
        title=data["title"],
        file_name=data["file_name"],
        platform=data["platform"],
        size=data["size"],
        url=data["url"],
    )


def _catalog_from_dict(data: dict[str, Any]) -> CachedCatalog:
    return CachedCatalog(
        files=[_file_from_dict(item) for item in data["files"]],
        fetched_at=_utc(data["fetched_at"]),
    )


def _job_to_dict(job: DownloadJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "file": _file_to_dict(job.file),
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "bytes_done": job.bytes_done,
        "bytes_total": job.bytes_total,
        "dest_path": job.dest_path,
        "error": job.error,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "resume_unsupported": job.resume_unsupported,
    }


def _job_from_dict(data: dict[str, Any]) -> DownloadJob:
    finished = data["finished_at"]
    return DownloadJob(
        id=data["id"],
        file=_file_from_dict(data["file"]),
        status=JobStatus(data["status"]),
        created_at=_utc(data["created_at"]),
        bytes_done=data["bytes_done"],
        bytes_total=data["bytes_total"],
        dest_path=data["dest_path"],
        error=data["error"],
        finished_at=_utc(finished) if finished else None,
        resume_unsupported=data["resume_unsupported"],
    )


def _jobs_from_list(data: list[dict[str, Any]]) -> list[DownloadJob]:
    return [_job_from_dict(item) for item in data]
