from pathlib import Path

from rom_archive_grabber import composition
from rom_archive_grabber.adapters.paths import AppPaths
from rom_archive_grabber.adapters.settings_store import TomlSettingsStore
from rom_archive_grabber.domain.models import Settings


def make_paths(root: Path) -> AppPaths:
    return AppPaths(root / "config", root / "cache", root / "data", root / "downloads")


def test_find_repo_root_walks_up_to_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "src" / "pkg" / "module.py"
    assert composition.find_repo_root(nested) == tmp_path


def test_find_repo_root_is_none_without_pyproject(tmp_path: Path) -> None:
    assert composition.find_repo_root(tmp_path / "a" / "b.py") is None


def test_unreadable_settings_give_defaults_and_an_error(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    paths.settings_file.parent.mkdir(parents=True)
    paths.settings_file.write_text("max_parallel = [", encoding="utf-8")
    store = TomlSettingsStore(paths.settings_file, paths.default_download_dir)
    settings, error = composition.load_settings(store, paths)
    assert settings.sources == []
    assert settings.download_dir == paths.default_download_dir
    assert error is not None


async def test_build_services_wires_the_curated_source(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    http = composition.build_http()
    try:
        services = composition.build_services(paths, http, plugin_folders=[])
        assert [s.id for s in services.all_sources()] == ["curated"]
        assert services.registry.adapter_for("folder-page").kind == "folder-page"
        assert services.startup_error is None
    finally:
        await http.aclose()


async def test_broken_settings_file_is_never_overwritten(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    paths.settings_file.parent.mkdir(parents=True)
    paths.settings_file.write_text("max_parallel = [", encoding="utf-8")
    http = composition.build_http()
    try:
        services = composition.build_services(paths, http, plugin_folders=[])
        assert services.startup_error is not None
        services.settings_store.save(Settings(tmp_path / "elsewhere", 5))
        assert paths.settings_file.read_text(encoding="utf-8") == "max_parallel = ["
        assert services.settings_store.load() is services.settings
    finally:
        await http.aclose()


async def test_readable_settings_are_saved_to_the_file(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    http = composition.build_http()
    try:
        services = composition.build_services(paths, http, plugin_folders=[])
        services.settings_store.save(Settings(tmp_path / "elsewhere", 5))
        assert paths.settings_file.is_file()
    finally:
        await http.aclose()
