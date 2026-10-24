import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field

from rom_archive_grabber.adapters.sources.archive_org import ArchiveOrgAdapter, ArchiveTarget
from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.ports import HttpError, ListProgress

CURATED_SOURCE = SourceConfig(
    id="curated", name="Archive.org (curated)", kind="curated", location="", platform="other"
)


@dataclass(frozen=True, slots=True)
class CuratedCollection:
    """An archive.org item or collection vetted as homebrew, public-domain or freeware."""

    identifier: str
    platform: str
    note: str
    overrides: Mapping[str, str]
    # File names that are not playable, such as source-code or asset archives.
    exclude: frozenset[str] = field(default_factory=frozenset)

    def target(self, source_id: str) -> ArchiveTarget:
        return ArchiveTarget(
            self.identifier, source_id, self.platform, self.overrides, self.exclude
        )


def load_curated(text: str) -> list[CuratedCollection]:
    rows = tomllib.loads(text).get("collection", [])
    return [
        CuratedCollection(
            row["identifier"],
            row["platform"],
            row["note"],
            dict(row.get("overrides", {})),
            frozenset(row.get("exclude", [])),
        )
        for row in rows
    ]


class CuratedArchiveAdapter:
    """The built-in source: every curated archive.org entry listed as one catalog."""

    kind = "curated"

    def __init__(self, archive: ArchiveOrgAdapter, collections: list[CuratedCollection]) -> None:
        self._archive = archive
        self._collections = list(collections)

    async def detect(self, location: str) -> bool:
        # Never offered for user-entered locations; it is registered as a built-in.
        return False

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        files: list[GameFile] = []
        errors: list[HttpError] = []
        total = len(self._collections)
        for done, collection in enumerate(self._collections, start=1):
            try:
                files += await self._archive.list_target(collection.target(source.id))
            except HttpError as error:
                # One unreachable entry must not hide the rest of the built-in catalog.
                errors.append(error)
            if progress:
                progress(list(files), done, total)
        if errors and len(errors) == total:
            raise errors[-1]
        return files
