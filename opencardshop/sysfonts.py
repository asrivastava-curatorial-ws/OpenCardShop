"""Fonts installed on this computer, offered alongside the CardShop and starter fonts.

Linux and other fontconfig systems: one fast `fc-list` call. Windows and macOS:
the standard font folders are read once and cached per user. Set
OPENCARDSHOP_NO_SYSTEM_FONTS=1 to turn this off.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

from .paths import cache_dir

EXTENSIONS = {".ttf", ".otf", ".ttc"}


def font_folders() -> list[Path]:
    home = Path.home()
    if sys.platform.startswith("win"):
        windows = Path(os.environ.get("WINDIR") or r"C:\Windows")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        return [windows / "Fonts", local / "Microsoft/Windows/Fonts"]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), data / "fonts", home / ".fonts"]


def _from_fontconfig() -> list[tuple[str, str, str]] | None:
    try:
        result = subprocess.run(["fc-list", "--format", "%{file}\t%{family[0]}\t%{style[0]}\t%{index}\n"],
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    fonts = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        file, family, style, index = parts
        # Index 0 only: skips the extra faces of collections and named variable instances,
        # which a plain path cannot address.
        if Path(file).suffix.lower() not in EXTENSIONS or not family.strip() or index.strip() != "0":
            continue
        fonts.append((file, family.strip(), style.strip() or "Regular"))
    return fonts


def _from_folders() -> list[tuple[str, str, str]]:
    cache_file = cache_dir() / "system-fonts.json"
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    fresh, fonts = {}, []
    for folder in font_folders():
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in EXTENSIONS:
                continue
            try:
                if not path.is_file():
                    continue
                stamp = path.stat().st_mtime_ns
            except OSError:
                continue
            key = str(path)
            entry = cache.get(key)
            if not (isinstance(entry, list) and len(entry) == 3 and entry[0] == stamp):
                try:
                    family, style = ImageFont.truetype(key, 12).getname()
                except (OSError, ValueError):
                    family, style = "", ""
                entry = [stamp, family or "", style or ""]
            fresh[key] = entry
            if entry[1]:
                fonts.append((key, entry[1], entry[2] or "Regular"))
    if fresh != cache:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(fresh), encoding="utf-8")
        except OSError:
            pass
    return fonts


def installed_fonts() -> dict[str, list[tuple[Path, str]]]:
    """Family name -> [(font file, style)] for fonts installed on this computer."""
    if os.environ.get("OPENCARDSHOP_NO_SYSTEM_FONTS"):
        return {}
    found = None if sys.platform.startswith("win") else _from_fontconfig()
    if found is None:
        found = _from_folders()
    families: dict[str, list[tuple[Path, str]]] = {}
    for file, family, style in found:
        families.setdefault(family, []).append((Path(file), style))
    return families
