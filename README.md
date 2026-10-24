# rom-archive-grabber

A full-screen terminal app for finding and downloading game files from sources you
choose. Browse with the mouse or the keyboard, search and sort, mark what you want,
and let the download queue do the rest. Downloads can be paused, resumed and picked
up again after you close the app.

```
┌ Browse ─ Downloads (1 ↓) ───────────────────────────────────────────────┐
│ Sources          │ Title ▲            Platform   Size     Status  │ Anguna      │
│ ● ▶ Archive.org  │ Damuel             Game Boy   2.0 MB   ✔ have  │ anguna.gba  │
│ ● My GBA list    │ Tobu Tobu Girl     Game Boy   256 KB  ↓ 42%    │ 4.0 MB      │
│ + Add source     │ µCity              GB Color   1.0 MB           │ [Download]  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Features

- **One built-in source:** "Archive.org (curated)", a small, hand-checked list of
  free homebrew games on Archive.org. Every other source is one you add.
- **Add a source by pasting a link:** Archive.org items and collections, plain
  folder pages ("Index of …"), and text files with one link per line. The app works
  out which kind it is.
- **One table for everything:** search across all sources, filter by source or
  platform, and sort by clicking a column header.
- **Download manager:** a queue with pause, resume, start now, cancel, retry and a
  history of finished files. Interrupted downloads resume where they stopped.
- **Plugins:** add your own source types as small Python files that stay on your
  machine.
- Works on Windows (Windows Terminal), macOS and Linux.

## Install

Python 3.11 or newer is required.

```
pipx install git+https://github.com/restaadiputra/rom-archive-grabber
rom-archive-grabber
```

### Run from source

```
git clone https://github.com/restaadiputra/rom-archive-grabber
cd rom-archive-grabber
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
python -m rom_archive_grabber
```

## Adding a source

Click **+ Add source** in the Sources panel, or press `ctrl+p` and choose
**Add source**. Paste a link or a local file path, give it a name and pick a
platform. The app checks the link and recognises three kinds:

- **Archive.org item or collection**, for example `https://archive.org/details/<identifier>`.
- **Folder page**: a web page that lists files as links.
- **Link list**: a text file, online or on your disk, with one entry per line,
  either `Title | URL` or just a URL. Blank lines and lines starting with `#` are
  ignored.

```
# my-list.txt
My Game | https://example.com/files/my-game.zip
https://example.org/files/another-game.zip
```

If a link isn't recognised, the app says so and nothing is added. Each source can
later be edited, refreshed, hidden (the ● / ○ dot), switched off or removed.

## Keys

| Key | Where | Action |
| --- | --- | --- |
| `tab` | anywhere | switch between Browse and Downloads |
| `shift+tab` | anywhere | move focus to the previous widget |
| `ctrl+p` | anywhere | open the command palette |
| `space` | Browse | mark or unmark the selected file |
| `d` | Browse | download the marked files, or the selected one |
| `p` | Downloads | pause the selected download |
| `r` | Downloads | resume the selected download |
| `x` | Downloads | cancel the selected download |
| `o` | Downloads | open the download folder |
| `q` | anywhere | quit |

Everything is also clickable. The command palette offers Add source, Refresh all
sources, Download marked, Pause all, Resume all, Open download folder and Switch tab.

## Where things live

Locations follow your operating system's conventions (via `platformdirs`):

- **Settings**: `settings.toml` in the user config folder for `rom-archive-grabber`.
- **Downloaded files**: `rom-archive-grabber` inside your Downloads folder, one
  subfolder per platform: `<download folder>/<platform>/`.
- **Cached listings**: the user cache folder. **Download queue**: `jobs.json` in
  the user data folder.
- **Plugins**: `plugins/` in the config folder, or `local-plugins/` in a source
  checkout (git-ignored).

Example `settings.toml`:

```toml
download_dir = "D:/Games/rom-archive-grabber"
max_parallel = 2

[[source]]
id = "my-gba-list"
name = "My GBA list"
kind = "link-list"
location = "https://example.com/gba.txt"
platform = "gba"
enabled = true
```

If the settings file can't be read, the app tells you and won't overwrite it until
you fix it.

## Plugins

Plugins add new kinds of source. See [docs/plugins.md](docs/plugins.md); a working
example is in [examples/plugins/](examples/plugins/).

## Development

```
ruff format --check . && ruff check . && mypy && pytest -q
```

The code follows a layered layout: `domain/` (models and interfaces),
`application/` (use cases), `adapters/` (network, files, sources), `ui/` (Textual)
and `composition.py`, which wires them together.

## About this project

This project was vibe coded, and took its inspiration from
[sostenesapollo/rom-cli](https://github.com/sostenesapollo/rom-cli). It is a
fresh implementation with a different goal: a safe-to-share tool that ships no
third-party sites and lets each user choose their own sources.

## Your responsibility

You are responsible for what you add and download. Only use files you have the
right to, such as homebrew games, public-domain collections and backups of games
you own.

## License

[MIT](LICENSE) © 2026 restaadiputra
