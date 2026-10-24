import importlib.util
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from rom_archive_grabber.application.registry import SourceRegistry
from rom_archive_grabber.domain.ports import HttpClient

_MODULE_PREFIX = "rom_archive_grabber_plugin_"


@dataclass(frozen=True, slots=True)
class PluginWarning:
    path: Path
    message: str


def load_plugins(
    folders: Sequence[Path], registry: SourceRegistry, http: HttpClient
) -> list[PluginWarning]:
    """Import every plugin file in the folders and let it register its sources.

    A plugin that fails in any way is skipped and reported as a warning; it never
    stops the app or the other plugins.
    """
    warnings: list[PluginWarning] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py")):
            if path.name.startswith("_"):
                continue
            warning = _load_one(path, registry, http)
            if warning:
                warnings.append(warning)
    return warnings


def _load_one(path: Path, registry: SourceRegistry, http: HttpClient) -> PluginWarning | None:
    module_name = _MODULE_PREFIX + path.stem
    try:
        module = _import(path, module_name)
        register = getattr(module, "register", None)
        if not callable(register):
            raise AttributeError("no register(registry, http) function")
        register(registry, http)
    except (Exception, SystemExit) as error:
        # SystemExit is caught because a plugin may call exit() while importing.
        # KeyboardInterrupt is deliberately not caught so Ctrl+C still stops the app.
        sys.modules.pop(module_name, None)
        return PluginWarning(path, f"{type(error).__name__}: {error}")
    return None


def _import(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before executing so decorators such as @dataclass can find the module.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
