import re
from urllib.parse import unquote, urlsplit

GAME_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".zip",
        ".7z",
        ".rar",
        ".iso",
        ".nsp",
        ".xci",
        ".gb",
        ".gbc",
        ".gba",
        ".nes",
        ".sfc",
        ".smc",
        ".n64",
        ".z64",
        ".v64",
        ".nds",
        ".cia",
        ".chd",
        ".cue",
        ".bin",
        ".gen",
        ".md",
        ".sms",
        ".gg",
    }
)

UNSAFE_FILE_NAMES: frozenset[str] = frozenset({"", ".", ".."})
MAX_NAME_LENGTH = 150
_FALLBACK_NAME = "download"
_ILLEGAL_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


def _extension(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def url_file_name(url: str) -> str:
    """Last path segment, decoded; only what follows any separator survives."""
    decoded = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return decoded.replace("\\", "/").rsplit("/", 1)[-1]


def is_usable_file_name(name: str) -> bool:
    return name not in UNSAFE_FILE_NAMES


def is_game_file(name: str) -> bool:
    return _extension(name) in GAME_EXTENSIONS


def clean_title(file_name: str) -> str:
    dot = file_name.rfind(".")
    stem = file_name[:dot] if dot > 0 else file_name
    return _WHITESPACE.sub(" ", stem.replace("_", " ")).strip()


def _sanitise(part: str) -> str:
    return _WHITESPACE.sub(" ", _ILLEGAL_CHARS.sub(" ", part)).strip(" .")


def safe_file_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    dot = base.rfind(".")
    stem, ext = (base[:dot], base[dot:]) if dot > 0 else (base, "")
    stem = _sanitise(stem)
    clean_ext = _sanitise(ext)
    ext = f".{clean_ext}" if clean_ext else ""
    if not stem:
        return _FALLBACK_NAME
    if stem.upper() in _RESERVED_STEMS:
        stem = f"_{stem}"
    return stem[: MAX_NAME_LENGTH - len(ext)] + ext
