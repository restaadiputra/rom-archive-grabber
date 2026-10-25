from rom_archive_grabber.domain.models import GameFile
from rom_archive_grabber.ui.services import AppServices


class LoadedFiles:
    """The files the Browse tab works on: cached listings plus files still arriving."""

    def __init__(self, services: AppServices) -> None:
        self._services = services
        self.files: list[GameFile] = []
        self._search_files: list[GameFile] = []
        self._by_key: dict[str, GameFile] = {}
        self.revision = 0

    def reload(self) -> None:
        """Take the cached listings of the sources that are switched on."""
        sources = self._services.all_sources()
        enabled = {source.id for source in sources}
        search_files = [file for file in self._search_files if file.source_id in enabled]
        self._set(self._services.catalog.files(sources) + search_files)

    def set_search_results(self, files: list[GameFile]) -> None:
        if files == self._search_files:
            return
        self._search_files = files
        self.reload()

    def merge(self, files: list[GameFile]) -> None:
        """Files of a source being listed replace that source's older cached files."""
        arrived = {file.source_id for file in files}
        self._set([file for file in self.files if file.source_id not in arrived] + files)

    def replace_source(self, source_id: str, files: list[GameFile]) -> None:
        """Replace one finished source, including when its new listing is empty."""
        self._set([file for file in self.files if file.source_id != source_id] + files)

    def get(self, key: str) -> GameFile | None:
        return self._by_key.get(key)

    def _set(self, files: list[GameFile]) -> None:
        # Providers can list the same URL more than once. DataTable requires a
        # unique row key, and the lookup must match the row we keep.
        self._by_key = {}
        for file in files:
            self._by_key.setdefault(file.key, file)
        self.files = list(self._by_key.values())
        self.revision += 1
