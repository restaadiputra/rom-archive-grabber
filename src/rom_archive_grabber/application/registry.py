from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.ports import MatchingFileResolver, SourceAdapter


class SourceRegistry:
    """Holds source adapters by kind plus the built-in source list."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}
        self._builtin: list[SourceConfig] = []
        self._resolvers: list[MatchingFileResolver] = []

    def register(self, adapter: SourceAdapter) -> None:
        if adapter.kind in self._adapters:
            raise ValueError(f"source kind already registered: {adapter.kind}")
        self._adapters[adapter.kind] = adapter

    def adapter_for(self, kind: str) -> SourceAdapter:
        return self._adapters[kind]

    async def detect(self, location: str) -> SourceAdapter | None:
        for adapter in self._adapters.values():
            if await self._detects(adapter, location):
                return adapter
        return None

    def add_builtin_source(self, source: SourceConfig) -> None:
        self._builtin.append(source)

    def builtin_sources(self) -> list[SourceConfig]:
        return list(self._builtin)

    def register_resolver(self, resolver: MatchingFileResolver) -> None:
        """Add a plugin resolver for links that need a fresh URL at download time."""
        self._resolvers.append(resolver)

    async def resolve(self, file: GameFile) -> tuple[str, str | None]:
        for resolver in self._resolvers:
            if resolver.handles(file):
                return await resolver.resolve(file)
        return file.url, None

    @staticmethod
    async def _detects(adapter: SourceAdapter, location: str) -> bool:
        try:
            return await adapter.detect(location)
        except Exception:
            # A misbehaving plugin must not break detection for the others.
            return False
