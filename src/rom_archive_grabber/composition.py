"""Builds the concrete adapters and starts the app; the only module that knows them all."""

import asyncio
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path

from rom_archive_grabber import __version__
from rom_archive_grabber.adapters.clock import SystemClock
from rom_archive_grabber.adapters.downloader import FileDownloader
from rom_archive_grabber.adapters.http_client import HttpxClient, user_agent
from rom_archive_grabber.adapters.json_stores import JsonCatalogStore, JsonJobStore
from rom_archive_grabber.adapters.open_folder import open_folder
from rom_archive_grabber.adapters.paths import AppPaths
from rom_archive_grabber.adapters.plugin_loader import load_plugins
from rom_archive_grabber.adapters.settings_store import TomlSettingsStore, UnsavedSettingsStore
from rom_archive_grabber.adapters.sources.archive_org import ArchiveOrgAdapter
from rom_archive_grabber.adapters.sources.curated import (
    CURATED_SOURCE,
    CuratedArchiveAdapter,
    load_curated,
)
from rom_archive_grabber.adapters.sources.folder_page import FolderPageAdapter
from rom_archive_grabber.adapters.sources.link_list import LinkListAdapter
from rom_archive_grabber.application.catalog import CatalogService
from rom_archive_grabber.application.downloads import DownloadConfig, DownloadDeps, DownloadManager
from rom_archive_grabber.application.platforms import load_platforms
from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import Settings
from rom_archive_grabber.domain.ports import HttpClient, SettingsError, SettingsStore
from rom_archive_grabber.ui.app import AppServices, RomArchiveApp

_LOCAL_PLUGINS = "local-plugins"


def _data_text(name: str) -> str:
    return files("rom_archive_grabber.data").joinpath(name).read_text(encoding="utf-8")


def find_repo_root(start: Path) -> Path | None:
    """The nearest folder above `start` holding a `pyproject.toml` (a source checkout)."""
    for folder in start.resolve().parents:
        if (folder / "pyproject.toml").is_file():
            return folder
    return None


def load_settings(store: TomlSettingsStore, paths: AppPaths) -> tuple[Settings, str | None]:
    """The saved settings, or defaults plus the reason when the file cannot be read."""
    try:
        return store.load(), None
    except SettingsError as error:
        return Settings(download_dir=paths.default_download_dir), str(error)


def build_http() -> HttpxClient:
    return HttpxClient(user_agent(__version__))


def _build_registry(http: HttpClient) -> SourceRegistry:
    registry = SourceRegistry()
    archive = ArchiveOrgAdapter(http)
    registry.register(archive)
    registry.register(LinkListAdapter(http))
    registry.register(FolderPageAdapter(http))
    collections = load_curated(_data_text("curated-collections.toml"))
    registry.register(CuratedArchiveAdapter(archive, collections))
    registry.add_builtin_source(CURATED_SOURCE)
    return registry


def build_services(
    paths: AppPaths, http: HttpClient, plugin_folders: Sequence[Path]
) -> AppServices:
    toml_store = TomlSettingsStore(paths.settings_file, paths.default_download_dir)
    settings, startup_error = load_settings(toml_store, paths)
    # While the file cannot be read, nothing this session may overwrite it.
    store: SettingsStore = toml_store if startup_error is None else UnsavedSettingsStore(settings)
    registry = _build_registry(http)
    warnings = load_plugins(plugin_folders, registry, http)
    platforms = load_platforms(_data_text("platforms.toml"))
    jobs = JsonJobStore(paths.jobs_file)
    deps = DownloadDeps(FileDownloader(http), jobs, platforms, SystemClock())
    config = DownloadConfig(settings.download_dir, settings.max_parallel)
    return AppServices(
        settings=settings,
        settings_store=store,
        registry=registry,
        catalog=CatalogService(registry, JsonCatalogStore(paths.catalog_dir), SystemClock()),
        downloads=DownloadManager(deps, config),
        platforms=platforms,
        open_folder=open_folder,
        plugin_warnings=warnings,
        startup_error=startup_error,
    )


def _plugin_folders(paths: AppPaths) -> list[Path]:
    repo_root = find_repo_root(Path(__file__))
    local = [] if repo_root is None else [repo_root / _LOCAL_PLUGINS]
    return [*local, paths.plugins_dir]


async def _run() -> None:
    paths = AppPaths.from_platform()
    http = build_http()
    try:
        await RomArchiveApp(build_services(paths, http, _plugin_folders(paths))).run_async()
    finally:
        await http.aclose()


def main() -> None:
    asyncio.run(_run())
