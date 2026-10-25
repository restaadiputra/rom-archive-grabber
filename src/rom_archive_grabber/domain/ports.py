from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from rom_archive_grabber.domain.models import (
    CachedCatalog,
    DownloadJob,
    GameFile,
    Settings,
    SourceConfig,
)

# Files listed so far, items done, items total (None when unknown).
ListProgress = Callable[[list[GameFile], int, int | None], None]
# Bytes done, bytes total (None when unknown).
ProgressFn = Callable[[int, int | None], None]


class HttpStream(Protocol):
    status: int
    headers: Mapping[str, str]

    def chunks(self) -> AsyncIterator[bytes]: ...


class HttpClient(Protocol):
    async def get_text(self, url: str) -> tuple[str, str]:
        """Return the body text and its content type."""
        ...

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:  # noqa: ANN401  JSON bodies have no fixed shape
        ...

    def stream(self, url: str, start: int = 0) -> AbstractAsyncContextManager[HttpStream]: ...


class SourceAdapter(Protocol):
    kind: str

    async def detect(self, location: str) -> bool: ...

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]: ...


class CatalogStore(Protocol):
    def load(self, source_id: str) -> CachedCatalog | None: ...

    def save(self, source_id: str, catalog: CachedCatalog) -> None: ...

    def delete(self, source_id: str) -> None: ...


class JobStore(Protocol):
    # Why the last save failed, or None once a save worked; saving never raises.
    last_error: str | None

    def load(self) -> list[DownloadJob]: ...

    def save(self, jobs: list[DownloadJob]) -> None: ...


class SettingsError(Exception):
    """The settings file cannot be read or written."""


class SettingsStore(Protocol):
    def load(self) -> Settings: ...

    def save(self, settings: Settings) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current time, timezone-aware UTC."""
        ...


class HttpError(Exception):
    """A request failed; `status` is None for connection-level failures."""

    def __init__(self, url: str, status: int | None) -> None:
        detail = "connection failed" if status is None else f"HTTP {status}"
        super().__init__(f"{detail}: {url}")
        self.url = url
        self.status = status


class DownloadError(Exception):
    """A download could not produce a usable file."""


class Downloader(Protocol):
    async def download(self, job: DownloadJob, folder: Path, on_progress: ProgressFn) -> None: ...

    def discard_partial(self, job: DownloadJob) -> None:
        """Delete the job's unfinished `.part` file, if any."""
        ...

    def delete_file(self, job: DownloadJob) -> None:
        """Delete the job's finished file; a missing file is fine."""
        ...


class FileResolver(Protocol):
    async def resolve(self, file: GameFile) -> tuple[str, str | None]:
        """Return a current download URL and an optional server-provided name."""
        ...


class MatchingFileResolver(FileResolver, Protocol):
    def handles(self, file: GameFile) -> bool:
        """Whether this resolver owns the file's download link."""
        ...
