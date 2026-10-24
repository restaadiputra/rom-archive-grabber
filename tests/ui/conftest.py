import asyncio
import copy
import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rom_archive_grabber.application.catalog import CatalogService
from rom_archive_grabber.application.downloads import DownloadConfig, DownloadDeps, DownloadManager
from rom_archive_grabber.application.platforms import PlatformCatalog
from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import (
    CachedCatalog,
    DownloadJob,
    GameFile,
    Platform,
    Settings,
    SourceConfig,
)
from rom_archive_grabber.domain.ports import ListProgress, ProgressFn, SettingsError
from rom_archive_grabber.ui.app import AppServices

DOWNLOAD_DIR = Path("downloads")
_START = datetime(2026, 1, 1, tzinfo=UTC)

BUILTIN = SourceConfig("homebrew", "Homebrew Shelf", "fake", "builtin", "gb")
MY_LIST = SourceConfig("my-list", "My List", "fake", "https://example.com/list.txt", "nes")
OFF = SourceConfig("off", "Switched Off", "fake", "https://example.com/off.txt", "nes", False)
HIDDEN = SourceConfig("hidden", "Hidden", "fake", "https://example.com/hidden.txt", "nes")


def game(source: SourceConfig, title: str, platform: str, size: int | None) -> GameFile:
    name = title.lower().replace(" ", "-") + ".zip"
    return GameFile(source.id, title, name, platform, size, f"https://example.com/{name}")


FILES: dict[str, list[GameFile]] = {
    BUILTIN.id: [
        game(BUILTIN, "Tobu Tobu Girl", "gb", 262_144),
        game(BUILTIN, "Anguna", "gba", 4_194_304),
    ],
    MY_LIST.id: [game(MY_LIST, "Blade Buster", "nes", 393_216)],
    OFF.id: [game(OFF, "Off Game", "nes", None)],
    HIDDEN.id: [game(HIDDEN, "Hidden Game", "nes", None)],
}


class FakeClock:
    def __init__(self) -> None:
        self._ticks = 0

    def now(self) -> datetime:
        self._ticks += 1
        return _START + timedelta(seconds=self._ticks)


# Links the fake adapter recognises, and one whose check never finishes.
DETECTED_PREFIX = "https://example.org/"
SLOW_LINK = "https://example.org/slow.txt"


class FakeAdapter:
    """Lists `FILES` for a source, reporting the first file as partial progress.

    A source added during a test lists one game named after the source.
    """

    kind = "fake"

    async def detect(self, location: str) -> bool:
        if location == SLOW_LINK:
            await asyncio.Event().wait()
        await asyncio.sleep(0)
        return location.startswith(DETECTED_PREFIX)

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        files = FILES.get(source.id) or [game(source, f"{source.name} Game", source.platform, 1)]
        if progress:
            progress(files[:1], 0, None)
        await asyncio.sleep(0)
        return list(files)


class MemoryCatalogStore:
    def __init__(self, fail_saves: bool) -> None:
        self.catalogs: dict[str, CachedCatalog] = {}
        self.fail_saves = fail_saves

    def load(self, source_id: str) -> CachedCatalog | None:
        return self.catalogs.get(source_id)

    def save(self, source_id: str, catalog: CachedCatalog) -> None:
        if self.fail_saves:
            raise OSError("cache folder is read-only")
        self.catalogs[source_id] = catalog

    def delete(self, source_id: str) -> None:
        self.catalogs.pop(source_id, None)


class MemoryJobStore:
    def __init__(self, jobs: list[DownloadJob]) -> None:
        self.saved = list(jobs)
        self.last_error: str | None = None

    def load(self) -> list[DownloadJob]:
        return [dataclasses.replace(job) for job in self.saved]

    def save(self, jobs: list[DownloadJob]) -> None:
        self.saved = [dataclasses.replace(job) for job in jobs]


class MemorySettingsStore:
    """Keeps a copy of what was saved, so tests see only changes that were saved."""

    def __init__(self, settings: Settings, fail_saves: bool) -> None:
        self.settings = copy.deepcopy(settings)
        self.fail_saves = fail_saves

    def load(self) -> Settings:
        return copy.deepcopy(self.settings)

    def save(self, settings: Settings) -> None:
        if self.fail_saves:
            raise SettingsError("settings folder is read-only")
        self.settings = copy.deepcopy(settings)


class FakeDownloader:
    """Downloads never finish on their own, so jobs stay visible as downloading."""

    async def download(self, job: DownloadJob, folder: Path, on_progress: ProgressFn) -> None:
        on_progress(1, 4)
        await asyncio.Event().wait()

    def discard_partial(self, job: DownloadJob) -> None:
        pass

    def delete_file(self, job: DownloadJob) -> None:
        pass


@dataclass
class World:
    """Everything a UI test may want to arrange before building the services."""

    jobs: list[DownloadJob] = field(default_factory=list)
    warnings: list["FakePluginWarning"] = field(default_factory=list)
    startup_error: str | None = None
    opened: list[Path] = field(default_factory=list)
    fail_catalog_saves: bool = False
    fail_settings_saves: bool = False
    job_store: MemoryJobStore = field(init=False)
    open_error: OSError | None = None
    catalog_store: MemoryCatalogStore = field(init=False)
    settings_store: MemorySettingsStore = field(init=False)

    def open_folder(self, path: Path) -> None:
        if self.open_error is not None:
            raise self.open_error
        self.opened.append(path)

    def services(self) -> AppServices:
        platforms = PlatformCatalog(
            [
                Platform("gb", "Game Boy", "game-boy"),
                Platform("gba", "Game Boy Advance", "game-boy-advance"),
                Platform("nes", "NES", "nes"),
                Platform("other", "Other", "other"),
            ]
        )
        registry = SourceRegistry()
        registry.register(FakeAdapter())
        registry.add_builtin_source(BUILTIN)
        settings = Settings(DOWNLOAD_DIR, 2, [MY_LIST, OFF, HIDDEN], {HIDDEN.id})
        self.job_store = MemoryJobStore(self.jobs)
        deps = DownloadDeps(FakeDownloader(), self.job_store, platforms, FakeClock())
        self.catalog_store = MemoryCatalogStore(self.fail_catalog_saves)
        self.settings_store = MemorySettingsStore(settings, self.fail_settings_saves)
        return AppServices(
            settings=settings,
            settings_store=self.settings_store,
            registry=registry,
            catalog=CatalogService(registry, self.catalog_store, FakeClock()),
            downloads=DownloadManager(deps, DownloadConfig(DOWNLOAD_DIR, 2)),
            platforms=platforms,
            open_folder=self.open_folder,
            plugin_warnings=self.warnings,
            startup_error=self.startup_error,
        )


@dataclass(frozen=True)
class FakePluginWarning:
    path: Path
    message: str


@pytest.fixture
def world() -> World:
    return World()
