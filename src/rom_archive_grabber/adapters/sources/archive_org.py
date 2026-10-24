import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.names import clean_title, is_game_file
from rom_archive_grabber.domain.ports import HttpClient, ListProgress

_HOSTS = frozenset({"archive.org", "www.archive.org"})
_METADATA_URL = "https://archive.org/metadata/{}"
_SEARCH_URL = "https://archive.org/advancedsearch.php"
_DOWNLOAD_URL = "https://archive.org/download/{}/{}"
_SEARCH_ROWS = 500


def archive_identifier(location: str) -> str | None:
    """The identifier in an `archive.org/details/<identifier>` URL, else None."""
    parts = urlsplit(location)
    match [segment for segment in parts.path.split("/") if segment]:
        case ["details", identifier] if parts.hostname in _HOSTS:
            return identifier
        case _:
            return None


@dataclass(frozen=True, slots=True)
class ArchiveTarget:
    """An item or collection to list, with the platform each item gets."""

    identifier: str
    source_id: str
    platform: str
    overrides: Mapping[str, str] = field(default_factory=dict)
    # File names to leave out, such as source-code or asset archives.
    exclude: frozenset[str] = frozenset()

    def platform_for(self, item_id: str) -> str:
        return self.overrides.get(item_id, self.platform)

    def item(self, item_id: str) -> "_ItemRef":
        return _ItemRef(item_id, self.source_id, self.platform_for(item_id), self.exclude)


def _search_url(collection: str, page: int) -> str:
    # Built by hand because the search API needs the `fl[]` key twice.
    query = urlencode(
        [
            ("q", f"collection:{collection}"),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("rows", str(_SEARCH_ROWS)),
            ("page", str(page)),
            ("output", "json"),
        ]
    )
    return f"{_SEARCH_URL}?{query}"


@dataclass(frozen=True, slots=True)
class _ItemRef:
    identifier: str
    source_id: str
    platform: str
    exclude: frozenset[str] = frozenset()

    def keeps(self, entry: Mapping[str, Any]) -> bool:
        name = str(entry.get("name", ""))
        is_upload = entry.get("source") == "original"
        return is_upload and is_game_file(name) and name not in self.exclude


def _game_file(entry: Mapping[str, Any], item: _ItemRef) -> GameFile:
    name = str(entry["name"])
    size = int(entry["size"]) if "size" in entry else None
    url = _DOWNLOAD_URL.format(item.identifier, quote(name))
    return GameFile(item.source_id, clean_title(name), name, item.platform, size, url)


def _item_files(metadata: Mapping[str, Any], item: _ItemRef) -> list[GameFile]:
    files = [_game_file(entry, item) for entry in metadata.get("files", []) if item.keeps(entry)]
    title = str(metadata.get("metadata", {}).get("title", "")).strip()
    if len(files) == 1 and title:
        files = [replace(files[0], title=title)]
    return files


class ArchiveOrgAdapter:
    kind = "archive-org"

    def __init__(self, http: HttpClient, pause_seconds: float = 0.25) -> None:
        self._http = http
        self._pause_seconds = pause_seconds

    async def detect(self, location: str) -> bool:
        return archive_identifier(location) is not None

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        identifier = archive_identifier(source.location)
        if identifier is None:
            raise ValueError(f"not an archive.org details URL: {source.location}")
        return await self.list_target(
            ArchiveTarget(identifier, source.id, source.platform), progress
        )

    async def list_item(self, identifier: str, platform: str, source_id: str) -> list[GameFile]:
        item = _ItemRef(identifier, source_id, platform)
        return _item_files(await self._metadata(identifier), item)

    async def list_target(
        self, target: ArchiveTarget, progress: ListProgress | None = None
    ) -> list[GameFile]:
        """List one item, or every item of a collection, sequentially."""
        metadata = await self._metadata(target.identifier)
        if metadata.get("metadata", {}).get("mediatype") != "collection":
            files = _item_files(metadata, target.item(target.identifier))
            if progress:
                progress(list(files), 1, 1)
            return files
        item_ids = await self._collection_items(target.identifier)
        files = []
        for done, item_id in enumerate(item_ids, start=1):
            await asyncio.sleep(self._pause_seconds)
            files += _item_files(await self._metadata(item_id), target.item(item_id))
            if progress:
                progress(list(files), done, len(item_ids))
        return files

    async def _metadata(self, identifier: str) -> Mapping[str, Any]:
        data = await self._http.get_json(_METADATA_URL.format(quote(identifier)))
        return data if isinstance(data, dict) else {}

    async def _collection_items(self, collection: str) -> list[str]:
        item_ids: list[str] = []
        page = 1
        while True:
            response = (await self._http.get_json(_search_url(collection, page)))["response"]
            docs = response.get("docs", [])
            item_ids += [str(doc["identifier"]) for doc in docs]
            if not docs or len(item_ids) >= int(response.get("numFound", 0)):
                return item_ids
            page += 1
