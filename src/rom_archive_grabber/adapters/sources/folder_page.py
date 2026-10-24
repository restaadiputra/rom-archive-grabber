from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.names import (
    clean_title,
    is_game_file,
    is_usable_file_name,
    url_file_name,
)
from rom_archive_grabber.domain.ports import HttpClient, ListProgress

_SKIPPED_PREFIXES = ("mailto:", "javascript:", "#")


class _PageScanner(HTMLParser):
    """Collects anchor hrefs and the document title."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def _scan(html: str) -> _PageScanner:
    scanner = _PageScanner()
    scanner.feed(html)
    scanner.close()
    return scanner


def _game_url(href: str, base_url: str) -> str | None:
    if href.lower().startswith(_SKIPPED_PREFIXES) or href.endswith("/"):
        return None
    url = urldefrag(urljoin(base_url, href))[0]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.query:
        return None
    name = url_file_name(url)
    return url if is_usable_file_name(name) and is_game_file(name) else None


def _game_links(scanner: _PageScanner, base_url: str) -> list[str]:
    urls = (_game_url(href, base_url) for href in scanner.hrefs)
    return list(dict.fromkeys(url for url in urls if url))


def parse_folder_page(html: str, base_url: str) -> list[str]:
    """Absolute, de-duplicated game-file URLs linked from a directory listing."""
    return _game_links(_scan(html), base_url)


def _folder_base(location: str) -> str:
    """Treat a path without a trailing slash as a folder unless it names a file."""
    parts = urlsplit(location)
    if parts.path.endswith("/") or "." in parts.path.rsplit("/", 1)[-1]:
        return location
    return parts._replace(path=f"{parts.path}/").geturl()


class FolderPageAdapter:
    kind = "folder-page"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def detect(self, location: str) -> bool:
        html, content_type = await self._http.get_text(location)
        if "text/html" not in content_type.lower():
            return False
        scanner = _scan(html)
        is_index = scanner.title.strip().lower().startswith("index of")
        return is_index or bool(_game_links(scanner, _folder_base(location)))

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        html, _ = await self._http.get_text(source.location)
        names = [
            (url, url_file_name(url))
            for url in parse_folder_page(html, _folder_base(source.location))
        ]
        files = [
            GameFile(source.id, clean_title(name), name, source.platform, None, url)
            for url, name in names
        ]
        if progress:
            progress(files, len(files), len(files))
        return files
