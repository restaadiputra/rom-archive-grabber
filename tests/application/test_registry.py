import pytest

from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.ports import ListProgress


class FakeAdapter:
    def __init__(self, kind: str, *, detects: bool = False, raises: bool = False) -> None:
        self.kind = kind
        self._detects = detects
        self._raises = raises

    async def detect(self, location: str) -> bool:
        if self._raises:
            raise RuntimeError("boom")
        return self._detects

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        return []


async def test_registry_detect_order_and_raising_adapter_skipped() -> None:
    registry = SourceRegistry()
    registry.register(FakeAdapter("broken", raises=True))
    registry.register(FakeAdapter("no"))
    first = FakeAdapter("first", detects=True)
    registry.register(first)
    registry.register(FakeAdapter("second", detects=True))
    assert await registry.detect("https://example.com") is first


async def test_detect_returns_none_for_unknown() -> None:
    registry = SourceRegistry()
    registry.register(FakeAdapter("no"))
    assert await registry.detect("https://example.com") is None


def test_duplicate_kind_rejected() -> None:
    registry = SourceRegistry()
    registry.register(FakeAdapter("a"))
    with pytest.raises(ValueError, match="a"):
        registry.register(FakeAdapter("a"))


def test_adapter_for_missing_kind_raises_key_error() -> None:
    adapter = FakeAdapter("a")
    registry = SourceRegistry()
    registry.register(adapter)
    assert registry.adapter_for("a") is adapter
    with pytest.raises(KeyError):
        registry.adapter_for("b")


def test_builtin_sources_are_kept_in_order() -> None:
    registry = SourceRegistry()
    one = SourceConfig("one", "One", "link-list", "https://example.com/1.txt", "gb")
    two = SourceConfig("two", "Two", "link-list", "https://example.com/2.txt", "gb")
    registry.add_builtin_source(one)
    registry.add_builtin_source(two)
    assert registry.builtin_sources() == [one, two]
