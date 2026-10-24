from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_data_path, user_downloads_path

APP_NAME = "rom-archive-grabber"


@dataclass(frozen=True, slots=True)
class AppPaths:
    config_dir: Path
    cache_dir: Path
    data_dir: Path
    default_download_dir: Path

    @classmethod
    def from_platform(cls) -> "AppPaths":
        return cls(
            config_dir=user_config_path(APP_NAME),
            cache_dir=user_cache_path(APP_NAME),
            data_dir=user_data_path(APP_NAME),
            default_download_dir=user_downloads_path() / APP_NAME,
        )

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.toml"

    @property
    def plugins_dir(self) -> Path:
        return self.config_dir / "plugins"

    @property
    def catalog_dir(self) -> Path:
        return self.cache_dir / "catalogs"

    @property
    def jobs_file(self) -> Path:
        return self.data_dir / "jobs.json"
