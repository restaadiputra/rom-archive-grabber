"""Example plugin: adds one freely licensed Archive.org item as a source.

Copy this file into `local-plugins/` (in the repository) or into the `plugins/`
folder of the app's config directory to try it.
"""

from rom_archive_grabber.adapters.sources.archive_org import ArchiveOrgAdapter
from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.ports import HttpClient, ListProgress

KIND = "example-public-domain"
# Tobu Tobu Girl, a freely licensed Game Boy homebrew game.
ITEM_IDENTIFIER = "TobuTobuGirlGame"


class ExampleAdapter:
    kind = KIND

    def __init__(self, http: HttpClient) -> None:
        self._archive = ArchiveOrgAdapter(http)

    async def detect(self, location: str) -> bool:
        # This source is only added as a built-in, never matched from a pasted link.
        return False

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        return await self._archive.list_item(ITEM_IDENTIFIER, "gb", source.id)


def register(registry: SourceRegistry, http: HttpClient) -> None:
    registry.register(ExampleAdapter(http))
    registry.add_builtin_source(
        SourceConfig(
            id="example-public-domain",
            name="Example plugin: Tobu Tobu Girl",
            kind=KIND,
            location="",
            platform="gb",
        )
    )
