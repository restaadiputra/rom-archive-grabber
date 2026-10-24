import contextlib
import os
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    """Write `text` so readers never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        # A failed write must not leave a half-written temp file behind.
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        raise
