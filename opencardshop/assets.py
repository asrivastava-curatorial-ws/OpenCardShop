"""Case-independent, indexed access to original and prepared content."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
import configparser
import io
import json
import struct

from PIL import Image, ImageFont
from .formats import FormatError, read_cmk, read_messages, read_wmf
from .model import CardDocument
from .mylibrary import MyLibrary, PREFIX as MINE_PREFIX
from .starter import PREFIX as STARTER_PREFIX, StarterLibrary
from .sysfonts import installed_fonts
from .wmf import render_wmf

STARTER_ROOT = Path(__file__).resolve().parents[1] / "assets/starter"
STARTER_KEY = "STARTER:"
MINE_KEY = "MINE:library"
MINE_LABEL = "My library"


@dataclass
class Template:
    path: Path
    label: str
    fold: str
    search: str


def font_key(family: str, bold: bool, italic: bool) -> str:
    return f"{family}|bold={int(bold)}|italic={int(italic)}"


class AssetStore:
    def __init__(self, root: str | Path, rendered: str | Path | None = None, starter: str | Path | None = STARTER_ROOT,
                 personal: str | Path | bool = True):
        self.root = Path(root).resolve()
        self.rendered = Path(rendered).resolve() if rendered else self.root.parent / "rendered"
        self.files = {str(p.relative_to(self.root)).replace("\\", "/").casefold(): p for p in self.root.rglob("*") if p.is_file()}
        self.art_files = {p.name.upper(): p for p in self.root.rglob("*") if p.is_file() and p.suffix.upper() == ".CMF"}
        self.bitmaps = {p.stem.upper(): p for p in self.root.rglob("*") if p.is_file() and p.suffix.upper() == ".BMP" and p.parent.name.casefold() == "art"}
        self.prepared = {p.stem.upper(): p for p in self.rendered.glob("*.png")} if self.rendered.exists() else {}
        self.issues: dict[str, str] = {}
        report = self.rendered / "asset_report.json"
        if report.exists():
            for entry in json.loads(report.read_text()).get("artwork", []):
                if entry["status"] != "vector":
                    self.issues[entry["name"]] = entry.get("reason", entry["status"])
        ini = self.files.get("cardshop.ini")
        self.occasions: dict[str, str] = {}
        if ini:
            parser = configparser.ConfigParser(interpolation=None)
            parser.optionxform = str
            parser.read_string(ini.read_bytes().decode("cp1252", "replace"))
            for key, label in parser.items("OCCASIONS"):
                if any(n.startswith(key.casefold() + "/") for n in self.files):
                    self.occasions[key.upper()] = label.strip()
        if not self.occasions and self.root.is_dir():
            for path in sorted(self.root.iterdir()):
                if path.is_dir() and any(p.suffix.upper() == ".CMK" for p in path.iterdir()):
                    self.occasions[path.name.upper()] = path.name.title()
        # CardShop Plus occasions come first; the open starter pack's occasions follow.
        self.library_occasions = len(self.occasions)
        self.starter: StarterLibrary | None = None
        if starter is not None and (Path(starter) / "library.json").is_file():
            try:
                self.starter = StarterLibrary(starter)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, FormatError):
                self.starter = None
        if self.starter:
            labels = set(self.occasions.values())
            for key, occasion in self.starter.occasions.items():
                label = occasion.label + (" · starter pack" if self.library_occasions else "")
                while label in labels:
                    label += " "
                labels.add(label)
                self.occasions[STARTER_KEY + key] = label
        # The user's own pictures, messages and designs, offered in every card.
        self.mine: MyLibrary | None = None
        if personal is not False:
            self.mine = MyLibrary(personal if isinstance(personal, (str, Path)) else None)
            self.occasions[MINE_KEY] = MINE_LABEL
        self._templates: dict[str, list[Template]] = {}
        self.fonts: dict[str, list[tuple[Path, str]]] = {}
        self.fallbacks: dict[str, Path] = {}
        for path in self.root.rglob("*"):
            if path.suffix.upper() != ".TTF":
                continue
            try:
                family, style = ImageFont.truetype(str(path), 18).getname()
                self.fonts.setdefault(family, []).append((path, style))
            except OSError:
                continue
        # Then the starter pack's open fonts, then fonts installed on this computer.
        # A family already provided by an earlier source is never mixed with another.
        known = {name.casefold() for name in self.fonts}
        extra: dict[str, list[tuple[Path, str]]] = {}
        for path in self.starter.fonts if self.starter else []:
            try:
                family, style = ImageFont.truetype(str(path), 18).getname()
            except OSError:
                continue
            if family.casefold() not in known:
                extra.setdefault(family, []).append((path, style))
        self.fonts.update(extra)
        known |= {name.casefold() for name in extra}
        for family, items in installed_fonts().items():
            if family.casefold() not in known:
                self.fonts[family] = items
                known.add(family.casefold())
        # The original did not bundle Arial or Times New Roman. Use metric-compatible
        # Linux fonts where available, with a shipped DejaVu fallback for portability.
        candidates = {
            "Arial": (str(Path(__file__).resolve().parents[1] / "assets/fallback_fonts/LiberationSans-Regular.ttf"), "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "LiberationSans-Regular.ttf"),
            "Times New Roman": (str(Path(__file__).resolve().parents[1] / "assets/fallback_fonts/LiberationSerif-Regular.ttf"), "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf", "LiberationSerif-Regular.ttf"),
            "Sans": (str(Path(__file__).resolve().parents[1] / "assets/fallback_fonts/DejaVuSans.ttf"), "DejaVuSans.ttf"),
        }
        for family, paths in candidates.items():
            for name in paths:
                try:
                    face = ImageFont.truetype(name, 18)
                    self.fallbacks[family] = Path(face.path)
                    break
                except OSError:
                    continue
        if "Sans" not in self.fallbacks:
            raise FormatError("No usable fallback TrueType font was found")

    def find(self, relative: str) -> Path | None:
        return self.files.get(relative.replace("\\", "/").casefold())

    def _starter_occasion(self, occasion: str):
        if self.starter and occasion.startswith(STARTER_KEY):
            return self.starter.occasions.get(occasion[len(STARTER_KEY):])
        return None

    def library_changed(self) -> None:
        """Rescan My library after it changes (or after files are copied into its folder)."""
        if self.mine:
            self.mine.reload()
        self._image.cache_clear()

    def templates(self, occasion: str) -> list[Template]:
        if occasion == MINE_KEY:
            return [Template(card.path, card.title, card.fold, card.title.casefold())
                    for card in self.mine.cards] if self.mine else []
        if occasion.startswith(STARTER_KEY):
            found = self._starter_occasion(occasion)
            return [Template(card.path, card.title, card.fold, (card.title + " " + found.label).casefold())
                    for card in found.cards] if found else []
        key = occasion.upper()
        if key not in self._templates:
            paths = sorted((p for n, p in self.files.items() if n.startswith(key.casefold() + "/") and p.suffix.upper() == ".CMK"), key=lambda p: p.stem)
            index = self.find(key + "/PREBUILT.INI")
            order = [s.strip().upper() for s in index.read_text(encoding="cp1252").splitlines()] if index else []
            rank = {name: i for i, name in enumerate(order)}
            paths.sort(key=lambda p: (rank.get(p.stem.upper(), 10_000), p.stem))
            templates = []
            for path in paths:
                legacy = read_cmk(path)
                if not any(legacy.panels.values()):
                    continue
                messages = [o.text.replace("\n", " ") for o in legacy.panels["front"] if o.text]
                preview = messages[0] if messages else path.stem.title()
                label = path.stem + "  ·  " + preview[:72]
                search = " ".join([path.stem] + messages + [o.art for objects in legacy.panels.values() for o in objects]).casefold()
                templates.append(Template(path, label, legacy.fold, search))
            self._templates[key] = templates
        return self._templates[key]

    def occasion_art(self, occasion: str, all_art: bool = False) -> list[str]:
        if occasion == MINE_KEY:
            return list(self.mine.art) if self.mine else []
        if occasion.startswith(STARTER_KEY):
            found = self._starter_occasion(occasion)
            return sorted(self.starter.art) if self.starter and (all_art or not found) else list(found.art)
        if all_art:
            return sorted(self.art_files)
        ini = self.find(occasion + "/ART.INI")
        names = []
        if ini:
            for line in ini.read_text(encoding="cp1252").splitlines():
                name = Path(line.strip()).stem.upper() + ".CMF"
                if name in self.art_files and name not in names:
                    names.append(name)
        return names or sorted(self.art_files)

    def messages(self, occasion: str):
        if occasion == MINE_KEY:
            return list(self.mine.messages) if self.mine else []
        if occasion.startswith(STARTER_KEY):
            found = self._starter_occasion(occasion)
            return list(found.messages) if found else []
        path = self.find(occasion + "/MESSAGE.DAT")
        return read_messages(path) if path else []

    @lru_cache(maxsize=24)
    def _image(self, name: str) -> Image.Image:
        if self.starter and name in self.starter.art:
            with Image.open(self.starter.art[name]) as image:
                return image.convert("RGBA")
        if name.startswith(MINE_PREFIX):
            path = self.mine.art.get(name) if self.mine else None
            if path is None:
                raise FormatError(f"Picture is no longer in My library: {name[len(MINE_PREFIX):]}")
            with Image.open(path) as image:
                if image.width * image.height > 40_000_000:
                    raise FormatError("Picture exceeds the pixel limit")
                return image.convert("RGBA")
        key = Path(name).stem.upper()
        if key in self.prepared:
            with Image.open(self.prepared[key]) as image:
                return image.convert("RGBA")
        file = self.art_files.get(name.upper())
        if file is None:
            raise FormatError(f"Artwork not found: {name}")
        try:
            metafile = read_wmf(file.read_bytes())
            left, top, right, bottom = metafile.bounds
            scale = min(1800 / max(right - left, bottom - top), 0.3)
            size = max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale))
            return render_wmf(file.read_bytes(), size, self.font)
        except (FormatError, struct.error) as exc:
            if key in self.bitmaps:
                self.issues[name.upper()] = "Damaged vector; original bitmap preview used"
                with Image.open(self.bitmaps[key]) as image:
                    return image.convert("RGBA")
            raise FormatError(f"{name} is damaged and has no bitmap preview: {exc}") from exc

    def image(self, name: str, doc: CardDocument | None = None) -> Image.Image:
        if doc and name in doc.embedded_art:
            with Image.open(io.BytesIO(doc.embedded_art[name])) as image:
                if image.width * image.height > 40_000_000:
                    raise FormatError("Embedded image exceeds the pixel limit")
                return image.convert("RGBA")
        return self._image(name)

    def art_bytes(self, name: str, doc: CardDocument | None = None) -> bytes:
        if doc and name in doc.embedded_art:
            return doc.embedded_art[name]
        # Starter and My library pictures are stored as-is (WebP or PNG) to keep cards small.
        source = (self.starter.art.get(name) if self.starter else None) or \
                 (self.mine.art.get(name) if self.mine and name.startswith(MINE_PREFIX) else None)
        if source and source.stat().st_size <= 32 * 1024 * 1024:
            return source.read_bytes()
        output = io.BytesIO()
        self.image(name, doc).save(output, "PNG")
        return output.getvalue()

    def thumbnail(self, name: str, size=(64, 64)) -> Image.Image:
        key = Path(name).stem.upper()
        if key in self.bitmaps and not name.startswith((STARTER_PREFIX, MINE_PREFIX)):
            with Image.open(self.bitmaps[key]) as bitmap:
                image = bitmap.convert("RGBA")
        else:
            image = self.image(name).copy()
        image.thumbnail(size, Image.Resampling.LANCZOS)
        return image

    def template_thumbnail(self, template: Template) -> Image.Image:
        if template.path.suffix.casefold() == ".occard":
            canvas = Image.new("RGB", (44, 56), "white")
            preview = template.path.with_suffix(".png")
            if preview.is_file():
                with Image.open(preview) as image:
                    small = image.convert("RGB")
                small.thumbnail((44, 56), Image.Resampling.LANCZOS)
                canvas.paste(small, ((44 - small.width) // 2, (56 - small.height) // 2))
            return canvas
        path = template.path.with_suffix(".PRE")
        if not path.exists():
            path = self.find(str(template.path.relative_to(self.root).with_suffix(".PRE")))
        if path and path.exists():
            with Image.open(path) as image:
                return image.convert("RGB").resize((44, 56), Image.Resampling.NEAREST)
        return Image.new("RGB", (44, 56), "white")

    def _font_path(self, family: str, bold=False, italic=False) -> Path:
        found = next((items for name, items in self.fonts.items() if name.casefold() == family.casefold()), None)
        if found:
            def score(item):
                style = item[1].lower()
                return int(("bold" in style) != bold) + int(("italic" in style or "oblique" in style) != italic)
            return min(found, key=score)[0]
        fallback = self.fallbacks.get(family, self.fallbacks["Sans"])
        if family in ("Arial", "Times New Roman") and (bold or italic):
            variant = "BoldItalic" if bold and italic else ("Bold" if bold else "Italic")
            candidate = fallback.with_name(fallback.name.replace("Regular", variant))
            if candidate.exists():
                return candidate
        return fallback

    def font_bytes(self, family: str, doc: CardDocument | None = None, bold=False, italic=False) -> bytes:
        key = font_key(family, bold, italic)
        if doc and key in doc.embedded_fonts:
            return doc.embedded_fonts[key]
        if doc and family in doc.embedded_fonts:
            return doc.embedded_fonts[family]
        return self._font_path(family, bold, italic).read_bytes()

    def font(self, family: str, pixels: int, bold=False, italic=False, doc: CardDocument | None = None):
        pixels = max(1, min(4096, round(pixels)))
        if doc and (font_key(family, bold, italic) in doc.embedded_fonts or family in doc.embedded_fonts):
            return ImageFont.truetype(io.BytesIO(self.font_bytes(family, doc, bold, italic)), pixels)
        return self._cached_font(family, pixels, bold, italic)

    @lru_cache(maxsize=256)
    def _cached_font(self, family, pixels, bold, italic):
        return ImageFont.truetype(str(self._font_path(family, bold, italic)), pixels)
