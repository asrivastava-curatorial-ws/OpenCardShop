"""The open starter pack: freely licensed artwork and fonts, new messages, ready-made cards.

Layout of assets/starter/:
  library.json   occasions, each listing its artwork, cards and messages
  art/*.webp     clipart and backgrounds (PNG also accepted; licences in ATTRIBUTION.md)
  cards/*.occard ready-made cards, each with a front-view thumbnail cards/<name>.png
  fonts/*.ttf    open-licence fonts with their OFL texts
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

from .formats import FormatError, Message

PREFIX = "starter/"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,120}$")
FORMAT = "OpenCardShop starter library"


@dataclass
class StarterCard:
    path: Path
    title: str
    fold: str
    thumbnail: Path | None


@dataclass
class StarterOccasion:
    key: str
    label: str
    art: list[str]
    cards: list[StarterCard]
    messages: list[Message]


def _text(value, limit=2000) -> str:
    return value[:limit] if isinstance(value, str) else ""


class StarterLibrary:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        index = self.root / "library.json"
        if index.stat().st_size > 4 * 1024 * 1024:
            raise FormatError("Starter library index is too large")
        data = json.loads(index.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != 1:
            raise FormatError("Unsupported starter library")
        self.art: dict[str, Path] = {PREFIX + p.name: p for p in sorted((self.root / "art").glob("*"))
                                     if p.suffix.lower() in (".png", ".webp") and SAFE_NAME.match(p.name)}
        self.fonts: list[Path] = sorted(p for p in (self.root / "fonts").glob("*") if p.suffix.lower() in (".ttf", ".otf"))
        self.occasions: dict[str, StarterOccasion] = {}
        occasions = data.get("occasions", [])
        if not isinstance(occasions, list):
            raise FormatError("Invalid starter occasions")
        for item in occasions[:200]:
            if not isinstance(item, dict) or not SAFE_NAME.match(str(item.get("id", ""))):
                continue
            key = str(item["id"])
            art = [PREFIX + name for name in item.get("art", [])[:500]
                   if isinstance(name, str) and SAFE_NAME.match(name) and PREFIX + name in self.art]
            cards = []
            for card in item.get("cards", [])[:200]:
                file = card.get("file") if isinstance(card, dict) else None
                if not isinstance(file, str) or not SAFE_NAME.match(file) or not file.endswith(".occard"):
                    continue
                path = self.root / "cards" / file
                fold = card.get("fold")
                if not path.is_file() or fold not in ("side", "top", "full"):
                    continue
                thumbnail = path.with_suffix(".png")
                cards.append(StarterCard(path, _text(card.get("title"), 120) or path.stem, fold,
                                         thumbnail if thumbnail.is_file() else None))
            messages = []
            for entry in item.get("messages", [])[:1000]:
                if isinstance(entry, dict):
                    message = Message(front=_text(entry.get("front")), inside=_text(entry.get("inside")),
                                      back=_text(entry.get("back")))
                    if message.front or message.inside or message.back:
                        messages.append(message)
            self.occasions[key] = StarterOccasion(key, _text(item.get("label"), 80) or key.title(), art, cards, messages)
