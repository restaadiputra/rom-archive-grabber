import os
import subprocess
import sys
from pathlib import Path


def open_folder(path: Path) -> None:
    """Show `path` in the system file manager, creating it first if needed."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    # An argument list, never a shell string, so odd folder names stay harmless.
    subprocess.Popen([opener, str(path)])
