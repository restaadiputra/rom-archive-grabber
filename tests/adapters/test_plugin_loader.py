import sys
from pathlib import Path
from unittest.mock import MagicMock

import respx

from rom_archive_grabber.adapters.http_client import HttpxClient
from rom_archive_grabber.adapters.plugin_loader import PluginWarning, load_plugins
from rom_archive_grabber.application.registry import SourceRegistry

REPO_ROOT = Path(__file__).parents[2]

VALID_PLUGIN = """
from rom_archive_grabber.domain.models import SourceConfig


class DemoAdapter:
    kind = "demo"

    async def detect(self, location):
        return location == "demo://"

    async def list_files(self, source, progress=None):
        return []


def register(registry, http):
    registry.register(DemoAdapter())
    registry.add_builtin_source(SourceConfig("demo", "Demo", "demo", "demo://", "gb"))
"""


def _load(
    folder: Path, registry: SourceRegistry | None = None
) -> tuple[SourceRegistry, list[PluginWarning]]:
    registry = registry or SourceRegistry()
    return registry, load_plugins([folder], registry, MagicMock())


def test_loads_valid_plugin_and_registers_kind(tmp_path: Path) -> None:
    (tmp_path / "demo.py").write_text(VALID_PLUGIN, encoding="utf-8")

    registry, warnings = _load(tmp_path)

    assert warnings == []
    assert registry.adapter_for("demo").kind == "demo"
    assert [source.id for source in registry.builtin_sources()] == ["demo"]


def test_plugin_with_syntax_error_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def register(:\n", encoding="utf-8")
    (tmp_path / "good.py").write_text(VALID_PLUGIN, encoding="utf-8")

    registry, warnings = _load(tmp_path)

    assert [warning.path.name for warning in warnings] == ["broken.py"]
    assert registry.adapter_for("demo").kind == "demo"


def test_plugin_register_raising_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "boom.py").write_text(
        "def register(registry, http):\n    raise RuntimeError('boom')\n", encoding="utf-8"
    )

    _, warnings = _load(tmp_path)

    assert len(warnings) == 1
    assert "boom" in warnings[0].message


def test_plugin_calling_exit_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "quit.py").write_text("raise SystemExit(1)\n", encoding="utf-8")

    _, warnings = _load(tmp_path)

    assert [warning.path.name for warning in warnings] == ["quit.py"]


def test_plugin_without_register_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "empty.py").write_text("X = 1\n", encoding="utf-8")

    _, warnings = _load(tmp_path)

    assert "register" in warnings[0].message
    assert "rom_archive_grabber_plugin_empty" not in sys.modules


def test_duplicate_kind_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(VALID_PLUGIN, encoding="utf-8")
    (tmp_path / "b.py").write_text(VALID_PLUGIN, encoding="utf-8")

    _, warnings = _load(tmp_path)

    assert [warning.path.name for warning in warnings] == ["b.py"]


def test_underscore_files_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "_helper.py").write_text("raise RuntimeError('not a plugin')\n", encoding="utf-8")

    _, warnings = _load(tmp_path)

    assert warnings == []


def test_missing_folder_is_ignored(tmp_path: Path) -> None:
    _, warnings = _load(tmp_path / "does-not-exist")

    assert warnings == []


def test_example_plugin_loads() -> None:
    registry, warnings = _load(REPO_ROOT / "examples" / "plugins")

    assert warnings == []
    assert registry.adapter_for("example-public-domain").kind == "example-public-domain"
    assert [source.id for source in registry.builtin_sources()] == ["example-public-domain"]


@respx.mock
async def test_example_plugin_lists_its_item() -> None:
    respx.get("https://archive.org/metadata/TobuTobuGirlGame").respond(
        json={
            "metadata": {"title": "Tobu Tobu Girl"},
            "files": [{"name": "tobu.gb", "source": "original", "size": "32768"}],
        }
    )
    registry = SourceRegistry()
    client = HttpxClient("rom-archive-grabber/test")
    load_plugins([REPO_ROOT / "examples" / "plugins"], registry, client)
    source = registry.builtin_sources()[0]

    files = await registry.adapter_for(source.kind).list_files(source)

    assert [(f.file_name, f.platform, f.source_id) for f in files] == [
        ("tobu.gb", "gb", "example-public-domain")
    ]
    await client.aclose()
