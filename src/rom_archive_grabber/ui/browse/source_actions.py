import dataclasses
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Protocol, TypeVar

from textual.screen import ModalScreen

from rom_archive_grabber.application.source_settings import SourceSettings
from rom_archive_grabber.domain.models import SourceConfig
from rom_archive_grabber.domain.ports import SettingsError
from rom_archive_grabber.ui.dialogs.add_source import AddSourceDialog, SourceDraft
from rom_archive_grabber.ui.dialogs.confirm import ConfirmDialog
from rom_archive_grabber.ui.services import AppServices

T = TypeVar("T")


class SourceHost(Protocol):
    """What the source actions need from the Browse tab."""

    def notify_error(self, message: str) -> None:
        """Tell the user something went wrong."""
        ...

    def ask(self, screen: ModalScreen[T], then: Callable[[T | None], Awaitable[None]]) -> None:
        """Show `screen`; call `then` with its result once it closes."""
        ...

    def refresh_sources(self, sources: list[SourceConfig]) -> None: ...

    async def sources_changed(self) -> None:
        """Show the files and sources again after the source list changed."""
        ...


class SourceActions:
    """Add, edit, refresh, switch off and remove sources, saving every change."""

    def __init__(self, services: AppServices, host: SourceHost) -> None:
        self._services = services
        self._host = host
        self._handlers: dict[str, Callable[[SourceConfig], Awaitable[None]]] = {
            "edit": self.edit,
            "refresh": self.refresh,
            "toggle": self.toggle,
            "remove": self.remove,
        }

    async def run(self, action: str, source_id: str | None) -> None:
        """Run a Sources panel action; `add` needs no source."""
        if action == "add":
            self.add()
            return
        source = None if source_id is None else self._sources().get(source_id)
        handler = self._handlers.get(action)
        if source is not None and handler is not None:
            await handler(source)

    def add(self) -> None:
        dialog = AddSourceDialog(self._services.platforms.all(), detect=self._detect_kind)
        self._host.ask(dialog, self._add_draft)

    async def edit(self, source: SourceConfig) -> None:
        if not self._sources().is_user(source.id):
            return
        dialog = AddSourceDialog(self._services.platforms.all(), source, detect=self._detect_kind)
        self._host.ask(dialog, partial(self._apply_edit, source))

    async def refresh(self, source: SourceConfig) -> None:
        if self._sources().is_enabled(source):
            self._host.refresh_sources([source])

    async def toggle(self, source: SourceConfig) -> None:
        sources = self._sources()
        self._saving(sources.toggle, source.id)
        await self._host.sources_changed()
        toggled = sources.get(source.id)
        # A source switched off at start-up was never listed, so list it when switched on.
        if toggled is None or not sources.is_enabled(toggled):
            return
        if self._services.catalog.is_stale(source.id):
            self._host.refresh_sources([toggled])

    async def remove(self, source: SourceConfig) -> None:
        if not self._sources().is_user(source.id):
            return
        dialog = ConfirmDialog(f"Remove the source “{source.name}”? Its file list is forgotten.")
        self._host.ask(dialog, partial(self._apply_remove, source))

    async def _add_draft(self, draft: SourceDraft | None) -> None:
        if draft is None:
            return
        sources = self._sources()
        source_id = sources.new_id(draft.name)
        source = SourceConfig(source_id, draft.name, draft.kind, draft.location, draft.platform)
        self._saving(sources.add, source)
        await self._host.sources_changed()
        self._host.refresh_sources([source])

    async def _apply_edit(self, source: SourceConfig, draft: SourceDraft | None) -> None:
        if draft is None:
            return
        edited = dataclasses.replace(source, name=draft.name, platform=draft.platform)
        self._saving(self._sources().update, edited)
        await self._host.sources_changed()
        # Listed files carry the platform they were listed with.
        if edited.platform != source.platform and self._sources().is_enabled(edited):
            self._host.refresh_sources([edited])

    async def _apply_remove(self, source: SourceConfig, confirmed: bool | None) -> None:
        if not confirmed:
            return
        self._saving(self._sources().remove, source.id)
        self._services.catalog.forget(source.id)
        await self._host.sources_changed()

    def _saving(self, change: Callable[[T], None], argument: T) -> None:
        """Apply a settings change; if saving fails the change lasts only until quit."""
        try:
            change(argument)
        except SettingsError as error:
            self._host.notify_error(f"Couldn't save settings: {error}")

    async def _detect_kind(self, location: str) -> str | None:
        adapter = await self._services.registry.detect(location)
        return None if adapter is None else adapter.kind

    def _sources(self) -> SourceSettings:
        return self._services.source_settings()
