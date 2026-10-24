from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import App


def open_folder_or_notify(app: App[Any], open_folder: Callable[[Path], None], path: Path) -> None:
    """Open `path`, reporting a failure as a notification instead of closing the app."""
    try:
        open_folder(path)
    except OSError as error:
        app.notify(f"Could not open {path}: {error}", title="Open folder", severity="error")
