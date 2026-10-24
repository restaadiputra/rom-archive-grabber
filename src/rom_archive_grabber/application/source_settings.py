import dataclasses
import re

from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import Settings, SourceConfig
from rom_archive_grabber.domain.ports import SettingsStore

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_FALLBACK_SLUG = "source"


def slugify(name: str) -> str:
    """`Homebrew Picks!` → `homebrew-picks`; a name with no letters or digits → `source`."""
    return _NOT_ALNUM.sub("-", name.lower()).strip("-") or _FALLBACK_SLUG


class SourceSettings:
    """The user's sources and switched-off ids; every change is saved straight away.

    Built-in and plugin sources come from the registry and cannot be edited or removed,
    only switched off through `Settings.disabled_ids`.
    """

    def __init__(self, settings: Settings, store: SettingsStore, registry: SourceRegistry) -> None:
        self._settings = settings
        self._store = store
        self._registry = registry

    def listed(self) -> list[SourceConfig]:
        """Every source, switched off or not: built-in ones first, then the user's."""
        return self._registry.builtin_sources() + self._settings.sources

    def get(self, source_id: str) -> SourceConfig | None:
        return next((source for source in self.listed() if source.id == source_id), None)

    def is_user(self, source_id: str) -> bool:
        return any(source.id == source_id for source in self._settings.sources)

    def is_enabled(self, source: SourceConfig) -> bool:
        return source.enabled and source.id not in self._settings.disabled_ids

    def new_id(self, name: str) -> str:
        """An id from the name, with `-2`, `-3`… added when another source has it."""
        taken = {source.id for source in self.listed()}
        base = slugify(name)
        candidate, suffix = base, 2
        while candidate in taken:
            candidate, suffix = f"{base}-{suffix}", suffix + 1
        return candidate

    def add(self, source: SourceConfig) -> None:
        self._settings.sources.append(source)
        self._save()

    def update(self, source: SourceConfig) -> None:
        """Replace the user source with the same id."""
        self._settings.sources = [
            source if old.id == source.id else old for old in self._settings.sources
        ]
        self._save()

    def remove(self, source_id: str) -> None:
        self._settings.sources = [s for s in self._settings.sources if s.id != source_id]
        self._settings.disabled_ids.discard(source_id)
        self._save()

    def toggle(self, source_id: str) -> None:
        """Switch a source off, or back on."""
        if self.is_user(source_id):
            self._toggle_user(source_id)
        else:
            self._settings.disabled_ids ^= {source_id}
            self._save()

    def _toggle_user(self, source_id: str) -> None:
        source = next(s for s in self._settings.sources if s.id == source_id)
        if self.is_enabled(source):
            self.update(dataclasses.replace(source, enabled=False))
            return
        # Older settings may switch a user source off by id; turning it on clears both.
        self._settings.disabled_ids.discard(source_id)
        self.update(dataclasses.replace(source, enabled=True))

    def _save(self) -> None:
        self._store.save(self._settings)
