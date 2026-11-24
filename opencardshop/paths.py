"""Per-user folders and settings.

Installed copies (/usr/share/opencardshop, or the Windows install folder) cannot
store anything beside the program, so the chosen CardShop Plus folder and caches
live in the usual per-user locations. Set OPENCARDSHOP_HOME to keep everything in
one folder instead (used by the tests).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _folder(kind: str) -> Path:
    override = os.environ.get("OPENCARDSHOP_HOME")
    if override:
        return Path(override) / kind
    home = Path.home()
    if sys.platform.startswith("win"):
        roaming = Path(os.environ.get("APPDATA") or home / "AppData/Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        return {"config": roaming / "OpenCardShop", "data": local / "OpenCardShop",
                "cache": local / "OpenCardShop" / "Cache"}[kind]
    if sys.platform == "darwin":
        support = home / "Library/Application Support/OpenCardShop"
        return {"config": support, "data": support, "cache": home / "Library/Caches/OpenCardShop"}[kind]
    variable, default = {"config": ("XDG_CONFIG_HOME", ".config"), "data": ("XDG_DATA_HOME", ".local/share"),
                         "cache": ("XDG_CACHE_HOME", ".cache")}[kind]
    return Path(os.environ.get(variable) or home / default) / "opencardshop"


def config_dir() -> Path:
    return _folder("config")


def data_dir() -> Path:
    return _folder("data")


def cache_dir() -> Path:
    return _folder("cache")


def load_settings() -> dict:
    try:
        value = json.loads((config_dir() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_settings(**changes) -> None:
    """Merge changes into settings.json; failures are ignored (settings are a convenience)."""
    settings = load_settings()
    settings.update(changes)
    folder = config_dir()
    temp = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=folder, prefix=".settings-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
        os.replace(temp, folder / "settings.json")
        temp = None
    except OSError:
        pass
    finally:
        if temp and Path(temp).exists():
            Path(temp).unlink()


def has_library(folder: Path) -> bool:
    """True when folder looks like CardShop Plus CD content (contains CARDSHOP.INI)."""
    try:
        return folder.is_dir() and any(p.name.upper() == "CARDSHOP.INI" for p in folder.iterdir())
    except OSError:
        return False


def default_library() -> tuple[Path, Path | None]:
    """Locate CardShop Plus content: the folder chosen last time, a copy beside the
    program (assets/original), or the per-user data folder. Returns the content
    folder and its prepared-artwork cache; an empty folder means "starter pack only".
    """
    remembered = load_settings().get("library")
    if isinstance(remembered, str) and has_library(Path(remembered)):
        return Path(remembered), None
    bundled = ROOT / "assets/original"
    if has_library(bundled):
        return bundled, ROOT / "assets/rendered"
    personal = data_dir() / "cardshop"
    if has_library(personal):
        return personal, None
    return bundled, ROOT / "assets/rendered"


def open_path(path: Path) -> None:
    """Open a file or folder with the desktop's default application (raises OSError)."""
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 - the user's own file or folder
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
