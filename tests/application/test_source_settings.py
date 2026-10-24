from pathlib import Path

import pytest

from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.application.source_settings import SourceSettings, slugify
from rom_archive_grabber.domain.models import Settings, SourceConfig

BUILTIN = SourceConfig("homebrew", "Homebrew Shelf", "fake", "builtin", "gb")
MINE = SourceConfig("my-list", "My List", "fake", "https://example.com/list.txt", "nes")


class CountingStore:
    def __init__(self) -> None:
        self.saves = 0

    def load(self) -> Settings:
        raise AssertionError("not used")

    def save(self, settings: Settings) -> None:
        self.saves += 1


@pytest.fixture
def store() -> CountingStore:
    return CountingStore()


@pytest.fixture
def settings() -> Settings:
    return Settings(Path("downloads"), sources=[MINE])


@pytest.fixture
def sources(settings: Settings, store: CountingStore) -> SourceSettings:
    registry = SourceRegistry()
    registry.add_builtin_source(BUILTIN)
    return SourceSettings(settings, store, registry)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Homebrew Picks!", "homebrew-picks"),
        ("  My   Games  ", "my-games"),
        ("GB/GBC 2024", "gb-gbc-2024"),
        ("!!!", "source"),
        ("", "source"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_new_id_avoids_builtin_and_user_ids(sources: SourceSettings) -> None:
    assert sources.new_id("Homebrew") == "homebrew-2"
    assert sources.new_id("My List") == "my-list-2"
    assert sources.new_id("Fresh") == "fresh"


def test_new_id_counts_past_taken_suffixes(sources: SourceSettings) -> None:
    sources.add(SourceConfig("my-list-2", "My List", "fake", "x", "nes"))
    assert sources.new_id("My List") == "my-list-3"


def test_listed_puts_builtin_first_and_tells_user_sources_apart(sources: SourceSettings) -> None:
    assert sources.listed() == [BUILTIN, MINE]
    assert not sources.is_user(BUILTIN.id)
    assert sources.is_user(MINE.id)


def test_add_update_remove_save_each_time(
    sources: SourceSettings, settings: Settings, store: CountingStore
) -> None:
    extra = SourceConfig("extra", "Extra", "fake", "https://example.org/x.txt", "gb")
    sources.add(extra)
    sources.update(SourceConfig("extra", "Renamed", "fake", "https://example.org/x.txt", "nes"))
    assert settings.sources[-1].name == "Renamed"
    sources.remove("extra")
    assert settings.sources == [MINE]
    assert store.saves == 3


def test_toggle_builtin_uses_disabled_ids(sources: SourceSettings, settings: Settings) -> None:
    sources.toggle(BUILTIN.id)
    assert settings.disabled_ids == {BUILTIN.id}
    assert not sources.is_enabled(BUILTIN)
    sources.toggle(BUILTIN.id)
    assert settings.disabled_ids == set()


def test_toggle_user_source_flips_enabled(sources: SourceSettings, settings: Settings) -> None:
    sources.toggle(MINE.id)
    assert settings.sources[0].enabled is False
    assert settings.disabled_ids == set()
    sources.toggle(MINE.id)
    assert settings.sources[0].enabled is True


def test_enabling_user_source_listed_as_disabled_clears_that_too(
    sources: SourceSettings, settings: Settings
) -> None:
    settings.disabled_ids.add(MINE.id)
    sources.toggle(MINE.id)
    assert sources.is_enabled(settings.sources[0])
    assert settings.disabled_ids == set()
