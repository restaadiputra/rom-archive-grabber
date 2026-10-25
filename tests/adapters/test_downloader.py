import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rom_archive_grabber.adapters.downloader import (
    FileDownloader,
    looks_like_html,
    unique_path,
)
from rom_archive_grabber.domain.models import DownloadJob, GameFile, JobStatus
from rom_archive_grabber.domain.ports import DownloadError, HttpError, HttpStream


class FakeStream:
    def __init__(
        self, status: int, headers: Mapping[str, str], chunks: list[bytes], hang: bool = False
    ) -> None:
        self.status = status
        self.headers = headers
        self._chunks = chunks
        self._hang = hang

    async def chunks(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        if self._hang:
            await asyncio.Event().wait()


class FakeHttp:
    def __init__(self, stream: FakeStream) -> None:
        self._stream = stream
        self.starts: list[int] = []
        self.urls: list[str] = []

    async def get_text(self, url: str) -> tuple[str, str]:
        raise NotImplementedError

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> object:
        raise NotImplementedError

    def stream(self, url: str, start: int = 0) -> AbstractAsyncContextManager[HttpStream]:
        self.urls.append(url)
        self.starts.append(start)
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[HttpStream]:
        yield self._stream


def make_job(file_name: str = "game.gb") -> DownloadJob:
    file = GameFile("s", "Game", file_name, "gb", None, "https://example.com/game.gb")
    return DownloadJob("j1", file, JobStatus.QUEUED, datetime(2026, 1, 1, tzinfo=UTC))


def ok(chunks: list[bytes], **headers: str) -> FakeStream:
    return FakeStream(200, headers, chunks)


async def run(
    stream: FakeStream, job: DownloadJob, folder: Path
) -> tuple[FakeHttp, list[tuple[int, int | None]]]:
    http = FakeHttp(stream)
    seen: list[tuple[int, int | None]] = []
    await FileDownloader(http).download(job, folder, lambda done, total: seen.append((done, total)))
    return http, seen


async def test_downloads_to_platform_folder(tmp_path: Path) -> None:
    job = make_job()
    folder = tmp_path / "Game Boy"
    _, seen = await run(ok([b"abc", b"def"], **{"Content-Length": "6"}), job, folder)
    assert job.dest_path == str(folder / "game.gb")
    assert (folder / "game.gb").read_bytes() == b"abcdef"
    assert not (folder / "game.gb.part").exists()
    assert (job.bytes_done, job.bytes_total) == (6, 6)
    assert seen[-1] == (6, 6)


async def test_resolver_supplies_current_url_and_file_name(tmp_path: Path) -> None:
    class Resolver:
        async def resolve(self, file: GameFile) -> tuple[str, str | None]:
            return "https://cdn.example/current.gb", "server-name.gb"

    job = make_job()
    http = FakeHttp(ok([b"game"]))
    await FileDownloader(http, Resolver()).download(job, tmp_path, lambda _done, _total: None)
    assert http.urls == ["https://cdn.example/current.gb"]
    assert (tmp_path / "server-name.gb").read_bytes() == b"game"


def test_unique_path_adds_suffix(tmp_path: Path) -> None:
    (tmp_path / "a.gb").write_bytes(b"x")
    assert unique_path(tmp_path, "a.gb") == tmp_path / "a (2).gb"
    (tmp_path / "a (2).gb").write_bytes(b"x")
    assert unique_path(tmp_path, "a.gb") == tmp_path / "a (3).gb"
    (tmp_path / "b.gb.part").write_bytes(b"x")
    assert unique_path(tmp_path, "b.gb") == tmp_path / "b (2).gb"


async def test_dest_stays_inside_folder(tmp_path: Path) -> None:
    job = make_job("../../x.gb")
    folder = tmp_path / "Game Boy"
    await run(ok([b"abc"]), job, folder)
    assert job.dest_path is not None
    assert Path(job.dest_path).parent == folder


async def test_resume_appends_on_206(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    (tmp_path / "game.gb.part").write_bytes(b"old!")
    stream = FakeStream(206, {"Content-Range": "bytes 4-6/7"}, [b"new"])
    http, _ = await run(stream, job, tmp_path)
    assert http.starts == [4]
    assert (tmp_path / "game.gb").read_bytes() == b"old!new"
    assert job.bytes_total == 7
    assert not job.resume_unsupported


async def test_resume_total_from_content_length(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    (tmp_path / "game.gb.part").write_bytes(b"old!")
    await run(FakeStream(206, {"Content-Length": "3"}, [b"new"]), job, tmp_path)
    assert job.bytes_total == 7


async def test_unknown_total_is_none(tmp_path: Path) -> None:
    job = make_job()
    await run(ok([b"abc"]), job, tmp_path)
    assert job.bytes_total is None


async def test_restart_when_range_ignored(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    (tmp_path / "game.gb.part").write_bytes(b"old!")
    await run(ok([b"new"]), job, tmp_path)
    assert (tmp_path / "game.gb").read_bytes() == b"new"
    assert job.resume_unsupported


async def test_html_response_fails_and_removes_part(tmp_path: Path) -> None:
    job = make_job()
    with pytest.raises(DownloadError, match="web page"):
        await run(ok([b"  <!DOCTYPE html><html>"]), job, tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_html_content_type_fails(tmp_path: Path) -> None:
    job = make_job()
    with pytest.raises(DownloadError):
        await run(ok([b"hello"], **{"Content-Type": "text/html; charset=utf-8"}), job, tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_bad_status_raises_and_keeps_part(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    (tmp_path / "game.gb.part").write_bytes(b"old!")
    with pytest.raises(HttpError):
        await run(FakeStream(404, {}, []), job, tmp_path)
    assert (tmp_path / "game.gb.part").read_bytes() == b"old!"


async def test_short_body_fails_and_keeps_part(tmp_path: Path) -> None:
    job = make_job()
    with pytest.raises(DownloadError, match="ended early"):
        await run(ok([b"abc"], **{"Content-Length": "6"}), job, tmp_path)
    assert (tmp_path / "game.gb.part").read_bytes() == b"abc"
    assert not (tmp_path / "game.gb").exists()


async def test_416_on_resume_discards_part(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    (tmp_path / "game.gb.part").write_bytes(b"old!")
    with pytest.raises(DownloadError, match="retry"):
        await run(FakeStream(416, {}, []), job, tmp_path)
    assert not (tmp_path / "game.gb.part").exists()
    assert job.dest_path == str(tmp_path / "game.gb")


async def test_concurrent_same_name_jobs_get_distinct_paths(tmp_path: Path) -> None:
    class SlowStream(FakeStream):
        async def chunks(self) -> AsyncIterator[bytes]:
            await asyncio.sleep(0.01)
            async for chunk in super().chunks():
                yield chunk
                await asyncio.sleep(0.01)

    first, second = make_job(), make_job()
    downloads = [
        FileDownloader(FakeHttp(SlowStream(200, {}, [data[:3], data[3:]]))).download(
            job, tmp_path, lambda _d, _t: None
        )
        for job, data in ((first, b"AAAAAA"), (second, b"BBBBBB"))
    ]
    await asyncio.gather(*downloads)
    assert first.dest_path != second.dest_path
    assert first.dest_path is not None
    assert second.dest_path is not None
    assert Path(first.dest_path).read_bytes() == b"AAAAAA"
    assert Path(second.dest_path).read_bytes() == b"BBBBBB"


async def test_cancel_keeps_part_file(tmp_path: Path) -> None:
    job = make_job()
    http = FakeHttp(FakeStream(200, {}, [b"abc"], hang=True))
    task = asyncio.create_task(FileDownloader(http).download(job, tmp_path, lambda _d, _t: None))
    for _ in range(50):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (tmp_path / "game.gb.part").read_bytes() == b"abc"


def test_discard_partial_removes_part(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    (tmp_path / "game.gb.part").write_bytes(b"x")
    downloader = FileDownloader(FakeHttp(ok([])))
    downloader.discard_partial(downloader_job := job)
    assert not (tmp_path / "game.gb.part").exists()
    downloader.discard_partial(downloader_job)
    downloader.discard_partial(make_job())


def test_delete_file_tolerates_missing(tmp_path: Path) -> None:
    job = make_job()
    job.dest_path = str(tmp_path / "game.gb")
    downloader = FileDownloader(FakeHttp(ok([])))
    downloader.delete_file(job)
    (tmp_path / "game.gb").write_bytes(b"x")
    downloader.delete_file(job)
    assert not (tmp_path / "game.gb").exists()
    downloader.delete_file(make_job())


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"<!doctype HTML>", True),
        (b"\n <html lang=en>", True),
        (b"PK\x03\x04", False),
        (b"", False),
    ],
)
def test_looks_like_html(head: bytes, expected: bool) -> None:
    assert looks_like_html(head) is expected
