from collections.abc import Sequence
from pathlib import Path

from rom_archive_grabber.application.download_queue import latest_by_file
from rom_archive_grabber.domain.models import GameFile, JobStatus, SourceConfig
from rom_archive_grabber.ui.browse.browse_state import BrowseState
from rom_archive_grabber.ui.browse.row_context import RowContext
from rom_archive_grabber.ui.browse.sources_panel import PlatformView, SourceView
from rom_archive_grabber.ui.services import AppServices


class BrowseViews:
    """Builds what the Browse tab shows from the services and the user's choices."""

    def __init__(self, services: AppServices, state: BrowseState) -> None:
        self._services = services
        self._state = state

    def row_context(self, sources: list[SourceConfig]) -> RowContext:
        return RowContext(
            marked=self._state.marked,
            jobs=latest_by_file(self._services.downloads.jobs()),
            source_names={source.id: source.name for source in sources},
            platforms=self._services.platforms,
        )

    def sources(self) -> list[SourceView]:
        """Every source, switched off ones too, so they can be switched back on."""
        sources = self._services.source_settings()
        views = []
        for source in sources.listed():
            state, error = self._services.catalog.state(source.id)
            shown = source.id not in self._state.hidden_sources
            enabled, user = sources.is_enabled(source), sources.is_user(source.id)
            views.append(SourceView(source.id, source.name, state, error, shown, enabled, user))
        return views

    def platforms(self, files: Sequence[GameFile]) -> list[PlatformView]:
        """The platforms present in `files`, by label."""
        platforms = self._services.platforms
        keys = {file.platform for file in files}
        views = [
            PlatformView(key, platforms.get(key).label, key == self._state.platform) for key in keys
        ]
        return sorted(views, key=lambda view: view.label.casefold())

    def folder_for(self, file: GameFile) -> Path:
        """Where the file was downloaded, or where it would go."""
        job = latest_by_file(self._services.downloads.jobs()).get(file.key)
        if job is not None and job.status is JobStatus.DONE and job.dest_path:
            return Path(job.dest_path).parent
        folder = self._services.platforms.get(file.platform).folder
        return self._services.settings.download_dir / folder
