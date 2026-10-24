from pathlib import Path

import pytest

from rom_archive_grabber.adapters.settings_store import TomlSettingsStore
from rom_archive_grabber.domain.models import Settings, SourceConfig
from rom_archive_grabber.domain.ports import SettingsError


def _store(tmp_path: Path) -> TomlSettingsStore:
    return TomlSettingsStore(tmp_path / "cfg" / "settings.toml", tmp_path / "downloads")


def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    settings = _store(tmp_path).load()
    assert settings.download_dir == tmp_path / "downloads"
    assert settings.max_parallel == 2
    assert settings.sources == []


def test_round_trip_preserves_sources_and_disabled_ids(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = SourceConfig(
        id="my-gba-list",
        name="My GBA list",
        kind="link-list",
        location="https://example.com/gba.txt",
        platform="gba",
        enabled=False,
    )
    original = Settings(
        download_dir=tmp_path / "elsewhere",
        max_parallel=3,
        sources=[source],
        disabled_ids={"curated", "another"},
    )
    store.save(original)
    assert store.load() == original


def test_malformed_settings_raises_settings_error(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("download_dir = ", encoding="utf-8")
    with pytest.raises(SettingsError) as err:
        TomlSettingsStore(path, tmp_path / "downloads").load()
    assert str(path) in str(err.value)


def test_max_parallel_below_one_is_clamped_to_one(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("max_parallel = 0\n", encoding="utf-8")
    assert TomlSettingsStore(path, tmp_path / "downloads").load().max_parallel == 1


def test_failed_write_raises_settings_error_and_leaves_no_temp_file(tmp_path: Path) -> None:
    folder = tmp_path / "cfg"
    store = TomlSettingsStore(folder / "settings.toml", tmp_path / "downloads")
    (folder / "settings.toml").mkdir(parents=True)  # a folder where the file belongs
    with pytest.raises(SettingsError, match="Cannot write settings file"):
        store.save(Settings(download_dir=tmp_path / "downloads"))
    assert not list(folder.glob("*.tmp"))
