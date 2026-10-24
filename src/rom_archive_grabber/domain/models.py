from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Platform:
    key: str
    label: str
    folder: str


@dataclass(frozen=True, slots=True)
class SourceConfig:
    id: str
    name: str
    # A plain string so plugins can add kinds. Built in: "archive-org",
    # "folder-page", "link-list", "curated".
    kind: str
    location: str
    platform: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class GameFile:
    source_id: str
    title: str
    file_name: str
    platform: str
    size: int | None
    url: str

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.url}"


@dataclass(frozen=True, slots=True)
class CachedCatalog:
    files: list[GameFile]
    fetched_at: datetime


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    FAILED = "failed"
    DONE = "done"


@dataclass(slots=True)
class DownloadJob:
    id: str
    file: GameFile
    status: JobStatus
    created_at: datetime
    bytes_done: int = 0
    bytes_total: int | None = None
    dest_path: str | None = None
    error: str | None = None
    finished_at: datetime | None = None
    resume_unsupported: bool = False


@dataclass(slots=True)
class Settings:
    download_dir: Path
    max_parallel: int = 2
    sources: list[SourceConfig] = field(default_factory=list)
    disabled_ids: set[str] = field(default_factory=set)
