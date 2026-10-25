import asyncio
from collections.abc import Awaitable, Iterable
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
        self._cached: dict[str, CachedCatalog | None] = {}

    def _load(self, source_id: str) -> CachedCatalog | None:
        if source_id not in self._cached:
            self._cached[source_id] = self._store.load(source_id)
        return self._cached[source_id]

    def files(self, sources: Iterable[SourceConfig]) -> list[GameFile]:
        result: list[GameFile] = []
        for source in sources:
            cached = self._load(source.id)
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
            cached = CachedCatalog(files, self._clock.now())
            await asyncio.to_thread(self._store.save, source.id, cached)
            self._cached[source.id] = cached
        except Exception as exc:  # plugin adapters can raise anything; saving can hit OSError
            self._states[source.id] = (SourceState.ERROR, str(exc) or type(exc).__name__)
            return
        self._states[source.id] = (SourceState.IDLE, None)

    async def refresh_stale(self, sources: Iterable[SourceConfig]) -> None:
        for source in sources:
            if self.is_stale(source.id):
                await self.refresh(source)

    async def search(self, sources: Iterable[SourceConfig], query: str) -> list[GameFile]:
        """Search providers that do not offer a browsable full catalog."""
        if not query.strip():
            return []
        searches: list[tuple[SourceConfig, Awaitable[list[GameFile]]]] = []
        for source in sources:
            try:
                adapter = self._registry.adapter_for(source.kind)
            except KeyError:
                continue
            search = getattr(adapter, "search", None)
            if callable(search):
                searches.append((source, search(source, query)))
        batches = await asyncio.gather(
            *(operation for _, operation in searches), return_exceptions=True
        )
        files: list[GameFile] = []
        for (source, _), batch in zip(searches, batches, strict=True):
            if isinstance(batch, BaseException):
                self._states[source.id] = (SourceState.ERROR, str(batch) or type(batch).__name__)
            else:
                self._states[source.id] = (SourceState.IDLE, None)
                files.extend(batch)
        return files

    def state(self, source_id: str) -> tuple[SourceState, str | None]:
        return self._states.get(source_id, (SourceState.IDLE, None))

    def forget(self, source_id: str) -> None:
        self._store.delete(source_id)
        self._cached.pop(source_id, None)
        self._states.pop(source_id, None)

    def is_stale(self, source_id: str) -> bool:
        """True when the source has no cached listing or it is older than `TTL`."""
        cached = self._load(source_id)
        return cached is None or self._clock.now() - cached.fetched_at > self.TTL
