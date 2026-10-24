import tomllib

from rom_archive_grabber.domain.models import Platform

_FALLBACK_KEY = "other"


class PlatformCatalog:
    def __init__(self, platforms: list[Platform]) -> None:
        self._platforms = list(platforms)
        self._by_key = {platform.key: platform for platform in platforms}

    def all(self) -> list[Platform]:
        return list(self._platforms)

    def get(self, key: str) -> Platform:
        """Return the platform for a key; unknown keys map to ``other``."""
        return self._by_key.get(key) or self._by_key[_FALLBACK_KEY]


def load_platforms(text: str) -> PlatformCatalog:
    rows = tomllib.loads(text)["platform"]
    return PlatformCatalog([Platform(row["key"], row["label"], row["folder"]) for row in rows])
