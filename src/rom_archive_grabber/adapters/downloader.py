import os
import re
from http import HTTPStatus
from pathlib import Path

from rom_archive_grabber.domain.models import DownloadJob
from rom_archive_grabber.domain.names import safe_file_name
from rom_archive_grabber.domain.ports import (
    DownloadError,
    HttpClient,
    HttpError,
    HttpStream,
    ProgressFn,
)

_HTML_PREFIXES = (b"<!doctype html", b"<html")
_HEAD_BYTES = 512
_CONTENT_RANGE_TOTAL = re.compile(r"/(\d+)\s*$")
_PART_SUFFIX = ".part"


def looks_like_html(head: bytes) -> bool:
    return head[:_HEAD_BYTES].lstrip().lower().startswith(_HTML_PREFIXES)


def _is_taken(path: Path) -> bool:
    return path.exists() or path.with_name(path.name + _PART_SUFFIX).exists()


def unique_path(folder: Path, name: str) -> Path:
    """First free path for `name`, adding " (2)", " (3)"... before the extension."""
    candidate = folder / name
    stem, ext = candidate.stem, candidate.suffix
    counter = 2
    while _is_taken(candidate):
        candidate = folder / f"{stem} ({counter}){ext}"
        counter += 1
    return candidate


def _part_path(job: DownloadJob) -> Path | None:
    if job.dest_path is None:
        return None
    return Path(job.dest_path + _PART_SUFFIX)


def _lower_headers(stream: HttpStream) -> dict[str, str]:
    return {key.lower(): value for key, value in stream.headers.items()}


def _total_bytes(headers: dict[str, str], start: int, partial: bool) -> int | None:
    if partial:
        match = _CONTENT_RANGE_TOTAL.search(headers.get("content-range", ""))
        if match:
            return int(match.group(1))
    length = headers.get("content-length", "")
    if length.isdigit():
        return start + int(length)
    return None


class FileDownloader:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def download(self, job: DownloadJob, folder: Path, on_progress: ProgressFn) -> None:
        dest = self._resolve_dest(job, folder)
        part = Path(str(dest) + _PART_SUFFIX)
        start = part.stat().st_size if part.exists() else 0
        # Leaving the context (error or cancellation) closes the connection;
        # the .part file stays so the download can resume later.
        async with self._http.stream(job.file.url, start) as stream:
            self._check_range_rejected(stream, part, start)
            partial = self._check_status(job, stream, start)
            if not partial:
                start = 0
            self._check_content_type(stream, part)
            await self._write(job, (stream, part, partial), start, on_progress)
        os.replace(part, dest)

    def discard_partial(self, job: DownloadJob) -> None:
        part = _part_path(job)
        if part is not None:
            part.unlink(missing_ok=True)

    def delete_file(self, job: DownloadJob) -> None:
        if job.dest_path is not None:
            Path(job.dest_path).unlink(missing_ok=True)

    def _resolve_dest(self, job: DownloadJob, folder: Path) -> Path:
        if job.dest_path is None:
            folder.mkdir(parents=True, exist_ok=True)
            name = safe_file_name(job.file.file_name)
            reserved = unique_path(folder, name)
            # Claim the name on disk now so a parallel job with the same file
            # name cannot resolve to the same destination.
            reserved.with_name(reserved.name + _PART_SUFFIX).touch()
            job.dest_path = str(reserved)
        dest = Path(job.dest_path).resolve()
        if not dest.is_relative_to(folder.resolve()):
            raise DownloadError("destination is outside the download folder")
        return Path(job.dest_path)

    def _check_range_rejected(self, stream: HttpStream, part: Path, start: int) -> None:
        if stream.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE and start > 0:
            part.unlink(missing_ok=True)
            raise DownloadError("server rejected resume; retry to start over")

    def _check_status(self, job: DownloadJob, stream: HttpStream, start: int) -> bool:
        """Return True when the server resumed (206); False when it sent it all (200)."""
        if stream.status == HTTPStatus.PARTIAL_CONTENT:
            job.resume_unsupported = False
            return True
        if stream.status != HTTPStatus.OK:
            raise HttpError(job.file.url, stream.status)
        if start > 0:
            job.resume_unsupported = True
        return False

    def _check_content_type(self, stream: HttpStream, part: Path) -> None:
        content_type = _lower_headers(stream).get("content-type", "")
        if content_type.lower().startswith("text/html"):
            part.unlink(missing_ok=True)
            raise DownloadError("server returned a web page, not a file")

    async def _write(
        self,
        job: DownloadJob,
        response: tuple[HttpStream, Path, bool],
        start: int,
        on_progress: ProgressFn,
    ) -> None:
        stream, part, partial = response
        headers = _lower_headers(stream)
        job.bytes_done = start
        job.bytes_total = _total_bytes(headers, start, partial)
        first = True
        with part.open("ab" if partial else "wb") as handle:
            async for chunk in stream.chunks():
                if first and looks_like_html(chunk):
                    handle.close()
                    part.unlink(missing_ok=True)
                    raise DownloadError("server returned a web page, not a file")
                first = False
                handle.write(chunk)
                job.bytes_done += len(chunk)
                on_progress(job.bytes_done, job.bytes_total)
        if job.bytes_total is not None and job.bytes_done < job.bytes_total:
            raise DownloadError("download ended early")
