import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from rom_archive_grabber.adapters.atomic_write import write_atomic
from rom_archive_grabber.domain.models import Settings, SourceConfig
from rom_archive_grabber.domain.ports import SettingsError

DEFAULT_MAX_PARALLEL = 2


class UnsavedSettingsStore:
    """Hands out fixed settings and never writes, so a broken settings file stays as it is."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def load(self) -> Settings:
        return self._settings

    def save(self, settings: Settings) -> None:
        # The user's file could not be read; overwriting it would lose their sources.
        pass


class TomlSettingsStore:
    def __init__(self, path: Path, default_download_dir: Path) -> None:
        self._path = path
        self._default_download_dir = default_download_dir

    def load(self) -> Settings:
        if not self._path.exists():
            return Settings(download_dir=self._default_download_dir)
        try:
            with self._path.open("rb") as handle:
                data = tomllib.load(handle)
            return self._parse(data)
        except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError, OSError) as exc:
            raise SettingsError(f"Cannot read settings file {self._path}: {exc}") from exc

    def save(self, settings: Settings) -> None:
        document: dict[str, Any] = {
            "download_dir": str(settings.download_dir),
            "max_parallel": settings.max_parallel,
            "disabled_ids": sorted(settings.disabled_ids),
            "source": [_source_to_dict(source) for source in settings.sources],
        }
        try:
            write_atomic(self._path, tomli_w.dumps(document))
        except OSError as exc:
            raise SettingsError(f"Cannot write settings file {self._path}: {exc}") from exc

    def _parse(self, data: dict[str, Any]) -> Settings:
        download_dir = Path(data.get("download_dir", self._default_download_dir))
        max_parallel = max(1, int(data.get("max_parallel", DEFAULT_MAX_PARALLEL)))
        return Settings(
            download_dir=download_dir,
            max_parallel=max_parallel,
            sources=[_source_from_dict(item) for item in data.get("source", [])],
            disabled_ids={str(item) for item in data.get("disabled_ids", [])},
        )


def _source_to_dict(source: SourceConfig) -> dict[str, Any]:
    return {
        "id": source.id,
        "name": source.name,
        "kind": source.kind,
        "location": source.location,
        "platform": source.platform,
        "enabled": source.enabled,
    }


def _source_from_dict(item: dict[str, Any]) -> SourceConfig:
    return SourceConfig(
        id=item["id"],
        name=item["name"],
        kind=item["kind"],
        location=item["location"],
        platform=item["platform"],
        enabled=bool(item.get("enabled", True)),
    )
