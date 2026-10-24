import asyncio
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.names import clean_title, is_usable_file_name, url_file_name
from rom_archive_grabber.domain.ports import HttpClient, ListProgress

_SEPARATOR = "|"


def _is_http(location: str) -> bool:
    return location.lower().startswith(("http://", "https://"))


def _resolve(target: str, base: str | None) -> str | None:
    if _is_http(target):
        return target
    return urljoin(base, target) if base and _is_http(base) else None


def parse_link_list(text: str, base: str | None) -> list[tuple[str, str]]:
    """Parse lines of `Title | link` or a bare link; `#` lines and blanks are ignored."""
    links: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        title, _, target = line.rpartition(_SEPARATOR)
        url = _resolve(target.strip(), base)
        if url is None or not is_usable_file_name(url_file_name(url)):
            continue
        links.append((title.strip() or clean_title(url_file_name(url)), url))
    return links


def _read_local(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


class LinkListAdapter:
    kind = "link-list"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def detect(self, location: str) -> bool:
        if _is_http(location):
            text, content_type = await self._http.get_text(location)
            looks_listy = content_type.lower().startswith("text/plain") or (
                urlsplit(location).path.lower().endswith(".txt")
            )
            return looks_listy and bool(parse_link_list(text, location))
        if not Path(location).is_file():
            return False
        return bool(parse_link_list(await asyncio.to_thread(_read_local, location), None))

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        if _is_http(source.location):
            text, _ = await self._http.get_text(source.location)
            base: str | None = source.location
        else:
            text = await asyncio.to_thread(_read_local, source.location)
            base = None
        files = [
            GameFile(source.id, title, url_file_name(url), source.platform, None, url)
            for title, url in parse_link_list(text, base)
        ]
        if progress:
            progress(files, len(files), len(files))
        return files
