from collections.abc import Iterable
from datetime import timedelta
from enum import StrEnum

from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import CachedCatalog, GameFile, SourceConfig
from rom_archive_grabber.domain.ports import CatalogStore, Clock, ListProgress


class SourceState(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    ERROR = "error"


class CatalogService:
    """Keeps a cached file listing per source and refreshes it on demand."""

    TTL = timedelta(hours=24)

    def __init__(self, registry: SourceRegistry, store: CatalogStore, clock: Clock) -> None:
        self._registry = registry
        self._store = store
        self._clock = clock
        self._states: dict[str, tuple[SourceState, str | None]] = {}

    def files(self, sources: Iterable[SourceConfig]) -> list[GameFile]:
        result: list[GameFile] = []
        for source in sources:
            cached = self._store.load(source.id)
            if cached is not None:
                result.extend(cached.files)
        return result

    async def refresh(self, source: SourceConfig, progress: ListProgress | None = None) -> None:
        self._states[source.id] = (SourceState.LOADING, None)
        try:
            adapter = self._registry.adapter_for(source.kind)
        except KeyError:
            message = f"No handler for source type '{source.kind}'"
            self._states[source.id] = (SourceState.ERROR, message)
            return
        try:
            files = await adapter.list_files(source, progress)
            self._store.save(source.id, CachedCatalog(files, self._clock.now()))
        except Exception as exc:  # plugin adapters can raise anything; saving can hit OSError
            self._states[source.id] = (SourceState.ERROR, str(exc) or type(exc).__name__)
            return
        self._states[source.id] = (SourceState.IDLE, None)

    async def refresh_stale(self, sources: Iterable[SourceConfig]) -> None:
        for source in sources:
            if self.is_stale(source.id):
                await self.refresh(source)

    def state(self, source_id: str) -> tuple[SourceState, str | None]:
        return self._states.get(source_id, (SourceState.IDLE, None))

    def forget(self, source_id: str) -> None:
        self._store.delete(source_id)
        self._states.pop(source_id, None)

    def is_stale(self, source_id: str) -> bool:
        """True when the source has no cached listing or it is older than `TTL`."""
        cached = self._store.load(source_id)
        return cached is None or self._clock.now() - cached.fetched_at > self.TTL
