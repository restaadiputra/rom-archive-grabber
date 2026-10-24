from rom_archive_grabber.domain.models import GameFile
from rom_archive_grabber.ui.services import AppServices


class LoadedFiles:
    """The files the Browse tab works on: cached listings plus files still arriving."""

    def __init__(self, services: AppServices) -> None:
        self._services = services
        self.files: list[GameFile] = []
        self._by_key: dict[str, GameFile] = {}

    def reload(self) -> None:
        """Take the cached listings of the sources that are switched on."""
        self._set(self._services.catalog.files(self._services.all_sources()))

    def merge(self, files: list[GameFile]) -> None:
        """Files of a source being listed replace that source's older cached files."""
        arrived = {file.source_id for file in files}
        self._set([file for file in self.files if file.source_id not in arrived] + files)

    def get(self, key: str) -> GameFile | None:
        return self._by_key.get(key)

    def _set(self, files: list[GameFile]) -> None:
        self.files = files
        self._by_key = {file.key: file for file in files}
