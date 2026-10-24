from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rom_archive_grabber.adapters.json_stores import JsonCatalogStore
from rom_archive_grabber.application.catalog import CatalogService, SourceState
from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import CachedCatalog, GameFile, SourceConfig
from rom_archive_grabber.domain.ports import ListProgress

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.current = NOW

    def now(self) -> datetime:
        return self.current


class FakeAdapter:
    kind = "fake"

    def __init__(self) -> None:
        self.results: list[list[GameFile] | Exception] = []
        self.calls: list[str] = []

    async def detect(self, location: str) -> bool:
        return True

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        self.calls.append(source.id)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_source(source_id: str = "a") -> SourceConfig:
    return SourceConfig(source_id, source_id, "fake", "https://example.com", "nes")


def make_file(source_id: str, name: str) -> GameFile:
    return GameFile(source_id, name, f"{name}.zip", "nes", 10, f"https://example.com/{name}.zip")


@pytest.fixture
def adapter() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(adapter: FakeAdapter, clock: FakeClock, tmp_path: Path) -> CatalogService:
    registry = SourceRegistry()
    registry.register(adapter)
    return CatalogService(registry, JsonCatalogStore(tmp_path), clock)


async def test_refresh_saves_and_files_returns_them(
    service: CatalogService, adapter: FakeAdapter
) -> None:
    files = [make_file("a", "one"), make_file("a", "two")]
    adapter.results.append(files)
    await service.refresh(make_source("a"))
    assert service.files([make_source("a")]) == files
    assert service.state("a") == (SourceState.IDLE, None)


async def test_files_follow_source_order(service: CatalogService, adapter: FakeAdapter) -> None:
    adapter.results += [[make_file("a", "one")], [make_file("b", "two")]]
    await service.refresh(make_source("a"))
    await service.refresh(make_source("b"))
    titles = [f.title for f in service.files([make_source("b"), make_source("a")])]
    assert titles == ["two", "one"]


async def test_refresh_failure_keeps_old_cache(
    service: CatalogService, adapter: FakeAdapter
) -> None:
    files = [make_file("a", "one")]
    adapter.results += [files, RuntimeError("boom")]
    await service.refresh(make_source("a"))
    await service.refresh(make_source("a"))
    assert service.files([make_source("a")]) == files
    assert service.state("a") == (SourceState.ERROR, "boom")


async def test_refresh_failure_with_empty_message_uses_class_name(
    service: CatalogService, adapter: FakeAdapter
) -> None:
    adapter.results.append(ValueError())
    await service.refresh(make_source("a"))
    assert service.state("a") == (SourceState.ERROR, "ValueError")


async def test_unknown_kind_sets_error(service: CatalogService) -> None:
    source = SourceConfig("p", "p", "missing", "x", "nes")
    await service.refresh(source)
    assert service.state("p") == (SourceState.ERROR, "No handler for source type 'missing'")


async def test_refresh_stale_skips_fresh_and_refreshes_25h_old(
    service: CatalogService, adapter: FakeAdapter, clock: FakeClock
) -> None:
    adapter.results += [[make_file("a", "one")], [make_file("a", "new")]]
    await service.refresh(make_source("a"))
    clock.current = NOW + timedelta(hours=23)
    await service.refresh_stale([make_source("a")])
    assert adapter.calls == ["a"]
    clock.current = NOW + timedelta(hours=25)
    await service.refresh_stale([make_source("a")])
    assert adapter.calls == ["a", "a"]
    assert service.files([make_source("a")])[0].title == "new"


async def test_refresh_stale_refreshes_sources_without_cache(
    service: CatalogService, adapter: FakeAdapter
) -> None:
    adapter.results.append([])
    await service.refresh_stale([make_source("a")])
    assert adapter.calls == ["a"]


async def test_is_stale_without_cache_or_after_ttl(
    service: CatalogService, adapter: FakeAdapter, clock: FakeClock
) -> None:
    assert service.is_stale("a")
    adapter.results.append([])
    await service.refresh(make_source("a"))
    assert not service.is_stale("a")
    clock.current = NOW + timedelta(hours=25)
    assert service.is_stale("a")


class FailingStore:
    def load(self, source_id: str) -> CachedCatalog | None:
        return None

    def save(self, source_id: str, catalog: CachedCatalog) -> None:
        raise OSError("disk full")

    def delete(self, source_id: str) -> None:
        pass


async def test_failed_save_marks_source_as_error(adapter: FakeAdapter, clock: FakeClock) -> None:
    registry = SourceRegistry()
    registry.register(adapter)
    service = CatalogService(registry, FailingStore(), clock)
    adapter.results.append([make_file("a", "one")])
    await service.refresh(make_source("a"))
    assert service.state("a") == (SourceState.ERROR, "disk full")


async def test_forget_deletes_cache(service: CatalogService, adapter: FakeAdapter) -> None:
    adapter.results.append([make_file("a", "one")])
    await service.refresh(make_source("a"))
    service.forget("a")
    assert service.files([make_source("a")]) == []
