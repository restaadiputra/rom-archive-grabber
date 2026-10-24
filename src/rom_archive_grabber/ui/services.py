from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rom_archive_grabber.application.catalog import CatalogService
from rom_archive_grabber.application.downloads import DownloadManager
from rom_archive_grabber.application.platforms import PlatformCatalog
from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.application.source_settings import SourceSettings
from rom_archive_grabber.domain.models import Settings, SourceConfig
from rom_archive_grabber.domain.ports import SettingsStore


class PluginWarning(Protocol):
    """A plugin that could not be loaded; the plugin loader's warnings fit this shape."""

    @property
    def path(self) -> Path: ...

    @property
    def message(self) -> str: ...


@dataclass
class AppServices:
    """Everything the UI needs, built by the composition root."""

    settings: Settings
    settings_store: SettingsStore
    registry: SourceRegistry
    catalog: CatalogService
    downloads: DownloadManager
    platforms: PlatformCatalog
    open_folder: Callable[[Path], None]
    plugin_warnings: Sequence[PluginWarning]
    startup_error: str | None = None

    def all_sources(self) -> list[SourceConfig]:
        """Built-in sources plus the user's, minus any switched off."""
        sources = self.source_settings()
        return [source for source in sources.listed() if sources.is_enabled(source)]

    def source_settings(self) -> SourceSettings:
        return SourceSettings(self.settings, self.settings_store, self.registry)
