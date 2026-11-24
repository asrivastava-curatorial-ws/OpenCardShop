"""My library: the user's own pictures, messages and card designs, reusable in every card.

Stored per user (see paths.data_dir()), so it survives updates and works for installed
copies. Layout of the my-library folder:
  art/           pictures; any PNG, JPEG, WebP, GIF or BMP copied here also appears
  cards/         saved designs (.occard), each with a front thumbnail (.png)
  messages.json  [{"front": ..., "inside": ..., "back": ...}, ...]
The whole folder can be exported to, and merged from, a .zip file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED
import io
import json
import os
import re
import tempfile

from PIL import Image

from .formats import FormatError, Message
from .paths import data_dir

PREFIX = "mine/"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,120}$")
MAX_SIDE = 2400


@dataclass
class MyCard:
    path: Path
    title: str
    fold: str


def _slug(text: str, default: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:60]
    return slug or default


def _card_info(path: Path) -> MyCard | None:
    try:
        with ZipFile(path) as archive:
            info = archive.getinfo("document.json")
            if info.file_size > 4 * 1024 * 1024:
                return None
            data = json.loads(archive.read(info))
    except (OSError, KeyError, ValueError, BadZipFile):
        return None
    fold = data.get("fold")
    if data.get("format") != "OpenCardShop" or fold not in ("side", "top", "full"):
        return None
    return MyCard(path, str(data.get("title") or path.stem)[:120], fold)


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".mylibrary-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, target)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()


class MyLibrary:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else data_dir() / "my-library"
        self.reload()

    @property
    def art_dir(self) -> Path:
        return self.root / "art"

    @property
    def cards_dir(self) -> Path:
        return self.root / "cards"

    @property
    def messages_file(self) -> Path:
        return self.root / "messages.json"

    def reload(self) -> None:
        self.art: dict[str, Path] = {}
        if self.art_dir.is_dir():
            for path in sorted(self.art_dir.iterdir(), key=lambda p: p.name.casefold()):
                if path.suffix.lower() in IMAGE_TYPES and SAFE_NAME.match(path.name) and path.is_file():
                    self.art[PREFIX + path.name] = path
        self.cards: list[MyCard] = []
        if self.cards_dir.is_dir():
            for path in sorted(self.cards_dir.glob("*.occard"), key=lambda p: p.name.casefold()):
                card = _card_info(path)
                if card:
                    self.cards.append(card)
        self.messages: list[Message] = []
        try:
            entries = json.loads(self.messages_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entries = []
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict):
                message = Message(*(str(entry.get(k, ""))[:2000] for k in ("front", "inside", "back")))
                if message.front or message.inside or message.back:
                    self.messages.append(message)

    def is_empty(self) -> bool:
        return not (self.art or self.cards or self.messages)

    def _unique(self, folder: Path, stem: str, suffix: str) -> Path:
        candidate, number = folder / f"{stem}{suffix}", 2
        while candidate.exists():
            candidate, number = folder / f"{stem}-{number}{suffix}", number + 1
        return candidate

    # Pictures -----------------------------------------------------------------
    def add_picture(self, image: Image.Image, name: str = "picture") -> str:
        """Store a picture as PNG and return its library name (mine/<file>)."""
        image = image.convert("RGBA")
        if image.width * image.height > 40_000_000:
            raise FormatError("Picture is larger than 40 megapixels")
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        self.art_dir.mkdir(parents=True, exist_ok=True)
        target = self._unique(self.art_dir, _slug(Path(name).stem, "picture"), ".png")
        output = io.BytesIO()
        image.save(output, "PNG", optimize=True)
        _write_atomic(target, output.getvalue())
        self.reload()
        return PREFIX + target.name

    def remove_picture(self, name: str) -> None:
        path = self.art.get(name)
        if path and path.exists():
            path.unlink()
        self.reload()

    # Messages -----------------------------------------------------------------
    def _save_messages(self) -> None:
        data = [{k: getattr(m, k) for k in ("front", "inside", "back") if getattr(m, k)} for m in self.messages]
        _write_atomic(self.messages_file, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def add_message(self, front: str = "", inside: str = "", back: str = "") -> bool:
        message = Message(front.strip()[:2000], inside.strip()[:2000], back.strip()[:2000])
        if not (message.front or message.inside or message.back) or message in self.messages:
            return False
        self.messages.append(message)
        self._save_messages()
        return True

    def remove_message(self, message: Message) -> None:
        if message in self.messages:
            self.messages.remove(message)
            self._save_messages()

    # Card designs -------------------------------------------------------------
    def add_card(self, doc, store, title: str | None = None) -> Path:
        from .model import save_document
        from .render import render_panel
        doc = doc.snapshot()
        doc.title = (title or doc.title or "My design").strip()[:120] or "My design"
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        target = self._unique(self.cards_dir, _slug(doc.title, "design"), ".occard")
        save_document(doc, target, store)
        try:
            preview = render_panel(doc, "front", store, width=180, errors=[]).convert("RGB")
            preview.save(target.with_suffix(".png"), "PNG", optimize=True)
        except (OSError, ValueError, FormatError):
            pass
        self.reload()
        return target

    def remove_card(self, path: Path) -> None:
        for file in (Path(path), Path(path).with_suffix(".png")):
            if file.parent == self.cards_dir and file.exists():
                file.unlink()
        self.reload()

    # Sharing between computers ----------------------------------------------------
    def export_zip(self, target: str | Path) -> int:
        count = 0
        with ZipFile(target, "w", ZIP_DEFLATED) as archive:
            for folder in (self.art_dir, self.cards_dir):
                if folder.is_dir():
                    for path in sorted(folder.iterdir()):
                        if path.is_file() and SAFE_NAME.match(path.name):
                            archive.write(path, f"my-library/{folder.name}/{path.name}")
                            count += 1
            if self.messages:
                archive.writestr("my-library/messages.json", self.messages_file.read_bytes())
        return count

    def import_zip(self, source: str | Path) -> dict[str, int]:
        """Merge a library exported by export_zip; returns what was added."""
        from .model import load_document
        added = {"pictures": 0, "cards": 0, "messages": 0}
        with ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 5000 or sum(i.file_size for i in entries) > 1024 * 1024 * 1024:
                raise FormatError("Library archive exceeds the size limit")
            for info in entries:
                parts = info.filename.replace("\\", "/").split("/")
                if info.is_dir() or len(parts) != 3 or parts[0] != "my-library" or not SAFE_NAME.match(parts[2]):
                    continue
                kind, name = parts[1], parts[2]
                if info.file_size > 64 * 1024 * 1024:
                    continue
                data = archive.read(info)
                if kind == "art" and Path(name).suffix.lower() in IMAGE_TYPES:
                    try:
                        with Image.open(io.BytesIO(data)) as image:
                            image.load()
                            self.add_picture(image, name)
                        added["pictures"] += 1
                    except (OSError, ValueError, FormatError, Image.DecompressionBombError):
                        continue
                elif kind == "cards" and name.endswith(".occard"):
                    with tempfile.TemporaryDirectory() as folder:
                        temp = Path(folder) / "card.occard"
                        temp.write_bytes(data)
                        try:
                            load_document(temp)
                        except (OSError, ValueError, KeyError, FormatError, BadZipFile):
                            continue
                        self.cards_dir.mkdir(parents=True, exist_ok=True)
                        target = self._unique(self.cards_dir, _slug(Path(name).stem, "design"), ".occard")
                        _write_atomic(target, data)
                        thumbnail = f"my-library/cards/{Path(name).stem}.png"
                        if thumbnail in archive.namelist():
                            _write_atomic(target.with_suffix(".png"), archive.read(thumbnail))
                        added["cards"] += 1
            if "my-library/messages.json" in archive.namelist():
                try:
                    entries = json.loads(archive.read("my-library/messages.json"))
                except ValueError:
                    entries = []
                for entry in entries if isinstance(entries, list) else []:
                    if isinstance(entry, dict) and self.add_message(*(str(entry.get(k, "")) for k in ("front", "inside", "back"))):
                        added["messages"] += 1
        self.reload()
        return added
