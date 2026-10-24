# Plugins

A plugin adds a new kind of source to the app. It is a single Python file with a
`register` function. Plugins are optional and are not part of the tracked files of
this repository.

## Where plugins live

The app loads every `*.py` file from two folders, in this order, each sorted by
file name:

1. `<repo>/local-plugins/` in a source checkout. The folder is git-ignored, so
   create it yourself.
2. `plugins/` inside the app's config folder.

A missing folder is fine and is ignored. Files whose name starts with `_` are not
loaded, so you can keep shared helpers there.

Plugins live outside the repository's tracked files on purpose: the project ships
only generic source types, and what you add for your own use stays on your machine.

## The contract

A plugin module defines:

```python
def register(registry: SourceRegistry, http: HttpClient) -> None: ...
```

Inside `register` you call `registry.register(adapter)` and, optionally,
`registry.add_builtin_source(SourceConfig(...))` to make a ready-made source appear
in the Sources panel.

An adapter has:

- `kind: str`: a unique name for the source type. Registering a kind that already
  exists fails.
- `async detect(location: str) -> bool`: return `True` if this adapter can handle a
  pasted link or path. Return `False` for sources you only add as built-ins.
- `async list_files(source: SourceConfig, progress=None) -> list[GameFile]`: return
  the downloadable files. `progress(files: list[GameFile], items_done: int, items_total: int | None)`
  may be called to report progress.

The `http` client is shared with the rest of the app. It sends the app's User-Agent
and retries failed requests, so use it instead of creating your own.

## A complete minimal plugin

This plugin lists one freely licensed Archive.org item. It is also available as
`examples/plugins/public_domain_item.py`.

```python
from rom_archive_grabber.adapters.sources.archive_org import ArchiveOrgAdapter
from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.models import GameFile, SourceConfig
from rom_archive_grabber.domain.ports import HttpClient, ListProgress

KIND = "example-public-domain"


class ExampleAdapter:
    kind = KIND

    def __init__(self, http: HttpClient) -> None:
        self._archive = ArchiveOrgAdapter(http)

    async def detect(self, location: str) -> bool:
        return False

    async def list_files(
        self, source: SourceConfig, progress: ListProgress | None = None
    ) -> list[GameFile]:
        return await self._archive.list_item("TobuTobuGirlGame", "gb", source.id)


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
```

Copy it into one of the plugin folders and start the app. The source appears in the
Sources panel like any other.

## When a plugin fails

If a plugin has a syntax error, has no `register` function, raises while
registering, or registers a kind that is already taken, the app skips that plugin,
keeps starting, and shows a warning with the file name and the error. Other plugins
still load. Fix or remove the file and restart.

Only add plugins you trust: they run as ordinary Python code with your permissions.
