"""Editable document state and a bounded, portable ZIP/JSON card format."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import copy
import hashlib
import json
import math
import os
import tempfile
import uuid

from .formats import FormatError, LegacyCard
from .printing import PAPERS, DEFAULT_MARGINS, LAYOUTS, validate_margins

SIDES = ("front", "inside", "back")


@dataclass
class CardObject:
    kind: str
    x: float
    y: float
    w: float
    h: float
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    art: str = ""
    text: str = ""
    font: str = "BluePrint"
    size: float = 24.0
    color: str = "#172d3f"
    align: str = "center"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    auto_fit: bool = True
    legacy_cell_height: bool = False


@dataclass
class CardDocument:
    title: str = "Untitled card"
    fold: str = "side"
    recipient: str = ""
    sender: str = ""
    paper: str = "A4"
    print_margins: tuple[float, float, float, float] = field(default=DEFAULT_MARGINS, kw_only=True)
    print_layout: str = field(default="quarter", kw_only=True)  # see printing.LAYOUTS
    panels: dict[str, list[CardObject]] = field(default_factory=lambda: {side: [] for side in SIDES})
    embedded_art: dict[str, bytes] = field(default_factory=dict, repr=False)
    embedded_fonts: dict[str, bytes] = field(default_factory=dict, repr=False)
    source: str = ""

    def dimensions(self, side: str) -> tuple[float, float]:
        if self.fold == "full":
            return 8500.0, 11000.0
        if self.fold == "top":
            return 5500.0, 8500.0 if side == "inside" else 4250.0
        return (8500.0 if side == "inside" else 4250.0), 5500.0

    def substitute(self, text: str) -> str:
        return text.replace("<receiver>", self.recipient or "<receiver>").replace("<sender>", self.sender or "<sender>")

    def snapshot(self) -> "CardDocument":
        return copy.deepcopy(self)

    @classmethod
    def from_legacy(cls, card: LegacyCard, title: str, source: str = "") -> "CardDocument":
        result = cls(title=title, fold=card.fold, source=source)
        for side, objects in card.panels.items():
            for old in objects:
                x1, y1, x2, y2 = old.bounds
                obj = CardObject(
                    kind="art" if old.kind == "CGraphic" else "text",
                    x=float(x1), y=float(y1), w=float(max(1, x2 - x1)), h=float(max(1, y2 - y1)),
                    art=old.art, text=old.text, font=old.font,
                    size=max(1.0, abs(old.height) * 72.0 / 1000.0),
                    color=old.color, align={0: "left", 1: "center", 2: "right"}.get(old.align, "left"),
                    bold=old.weight >= 600, italic=old.italic, underline=old.underline,
                    strike=old.strike, legacy_cell_height=True,
                )
                result.panels[side].append(obj)
        return result


def _metadata(doc: CardDocument) -> dict:
    return {"format": "OpenCardShop", "version": 1, "title": doc.title, "fold": doc.fold,
            "recipient": doc.recipient, "sender": doc.sender, "paper": doc.paper,
            "print_margins": list(doc.print_margins), "print_layout": doc.print_layout,
            "source": doc.source, "panels": {side: [asdict(o) for o in doc.panels[side]] for side in SIDES}}


def save_document(doc: CardDocument, path: str | Path, store) -> None:
    """Embed every used image and font; atomically replace the target on success."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = _metadata(doc)
    resources: dict[str, bytes] = {}
    art_map, font_map = {}, {}
    for objects in doc.panels.values():
        for obj in objects:
            if obj.kind == "art" and obj.art not in art_map:
                data = store.art_bytes(obj.art, doc)
                key = "images/" + hashlib.sha256(data).hexdigest() + ".png"
                resources[key] = data
                art_map[obj.art] = key
            elif obj.kind == "text":
                font_id = f"{obj.font}|bold={int(obj.bold)}|italic={int(obj.italic)}"
                if font_id in font_map:
                    continue
                data = store.font_bytes(obj.font, doc, obj.bold, obj.italic)
                if data:
                    key = "fonts/" + hashlib.sha256(data).hexdigest() + ".ttf"
                    resources[key] = data
                    font_map[font_id] = key
    metadata["art_resources"], metadata["font_resources"] = art_map, font_map
    fd, temp_path = tempfile.mkstemp(prefix=".opencardshop-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w+b") as stream:
            with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
                archive.writestr("document.json", json.dumps(metadata, ensure_ascii=False, indent=2))
                for name, data in resources.items():
                    archive.writestr(name, data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    finally:
        if Path(temp_path).exists():
            Path(temp_path).unlink()


def load_document(path: str | Path) -> CardDocument:
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 8192 or sum(i.file_size for i in entries) > 256 * 1024 * 1024:
            raise FormatError("Card package exceeds the size limit")
        if len({i.filename for i in entries}) != len(entries):
            raise FormatError("Duplicate entries in card package")
        if "document.json" not in archive.namelist() or archive.getinfo("document.json").file_size > 4 * 1024 * 1024:
            raise FormatError("Missing or oversized card metadata")
        raw = json.loads(archive.read("document.json"))
        if raw.get("format") != "OpenCardShop" or raw.get("version") != 1:
            raise FormatError("Unsupported OpenCardShop document version")
        if raw.get("fold") not in ("side", "top", "full"):
            raise FormatError("Invalid card fold")
        doc = CardDocument(title=str(raw.get("title", "Untitled card"))[:256], fold=raw["fold"],
                           recipient=str(raw.get("recipient", ""))[:1024], sender=str(raw.get("sender", ""))[:1024],
                           paper=raw.get("paper", "A4") if raw.get("paper") in PAPERS else "A4",
                           source=str(raw.get("source", "")))
        doc.print_layout = raw.get("print_layout") if raw.get("print_layout") in LAYOUTS else "quarter"
        try:
            doc.print_margins = validate_margins(raw.get("print_margins", DEFAULT_MARGINS))
        except ValueError as exc:
            raise FormatError("Invalid saved print margins") from exc
        object_ids = set()
        for side in SIDES:
            items = raw.get("panels", {}).get(side, [])
            if not isinstance(items, list) or len(items) > 4096:
                raise FormatError("Invalid panel object list")
            for item in items:
                try:
                    obj = CardObject(**item)
                except (TypeError, ValueError) as exc:
                    raise FormatError("Invalid card object") from exc
                if obj.kind not in ("text", "art") or obj.align not in ("left", "center", "right"):
                    raise FormatError("Invalid object type or alignment")
                if not all(isinstance(v, (int, float)) and math.isfinite(v) and abs(v) <= 100_000
                           for v in (obj.x, obj.y, obj.w, obj.h, obj.size)) or obj.w <= 0 or obj.h <= 0 or obj.size <= 0:
                    raise FormatError("Invalid object coordinates or font size")
                if not isinstance(obj.text, str) or len(obj.text) > 1_000_000 or not isinstance(obj.art, str) or len(obj.art) > 512:
                    raise FormatError("Invalid text or artwork reference")
                if not isinstance(obj.font, str) or len(obj.font) > 256 or not isinstance(obj.color, str):
                    raise FormatError("Invalid text style")
                if obj.id in object_ids:
                    obj.id = uuid.uuid4().hex
                object_ids.add(obj.id)
                doc.panels[side].append(obj)
        for field_name, destination in (("art_resources", doc.embedded_art), ("font_resources", doc.embedded_fonts)):
            mapping = raw.get(field_name, {})
            if not isinstance(mapping, dict):
                raise FormatError("Invalid resource map")
            for name, member in mapping.items():
                if not isinstance(name, str) or not isinstance(member, str) or member not in archive.namelist():
                    raise FormatError("Missing embedded resource")
                if not member.startswith(("images/", "fonts/")) or ".." in member.split("/") or archive.getinfo(member).file_size > 32 * 1024 * 1024:
                    raise FormatError("Invalid embedded resource")
                destination[name] = archive.read(member)
        return doc
