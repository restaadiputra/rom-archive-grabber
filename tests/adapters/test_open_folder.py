import os
import subprocess
import sys
from pathlib import Path

import pytest

from rom_archive_grabber.adapters import open_folder as module


class Recorder:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, arg: object) -> None:
        self.calls.append(arg)


def test_creates_the_folder_and_opens_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "downloads" / "nes"
    recorder = Recorder()
    if sys.platform == "win32":
        monkeypatch.setattr(os, "startfile", recorder)
        expected: object = str(folder)
    else:
        monkeypatch.setattr(subprocess, "Popen", recorder)
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        expected = [opener, str(folder)]
    module.open_folder(folder)
    assert folder.is_dir()
    assert recorder.calls == [expected]


def test_uses_xdg_open_with_an_argument_list_on_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "Popen", recorder)
    module.open_folder(tmp_path)
    assert recorder.calls == [["xdg-open", str(tmp_path)]]
