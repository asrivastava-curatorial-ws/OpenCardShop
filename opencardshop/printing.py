"""Physical paper geometry and fold instructions shared by preview and export."""
from __future__ import annotations

from dataclasses import dataclass
import math

from PIL import ImageDraw

PAPERS = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
DEFAULT_MARGINS = (5.0, 5.0, 5.0, 5.0)  # left, right, top, bottom, in mm
# "quarter": all four faces on one side of the sheet, folded twice (the original CardShop method).
# "half": outside faces on side 1 and the inside spread on side 2, folded once (duplex printing).
LAYOUTS = ("quarter", "half")
DUPLEX_SIDES = "two-sided-short-edge"  # correct for both half-fold orientations: the fold is parallel to the short edges


def validate_margins(values):
    try:
        result = tuple(float(v) for v in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter four numeric margins: left, right, top and bottom") from exc
    if len(result) != 4 or not all(math.isfinite(v) and 0 <= v <= 25 for v in result):
        raise ValueError("Each margin must be between 0 and 25 mm")
    return result


@dataclass(frozen=True)
class PaperLayout:
    size_mm: tuple[float, float]
    available_box_mm: tuple[float, float, float, float]
    finished_size_mm: tuple[float, float]
    margins_mm: tuple[float, float, float, float]


def paper_layout(fold, paper="A4", margins=DEFAULT_MARGINS, layout="quarter"):
    if fold not in ("side", "top", "full") or paper not in PAPERS or layout not in LAYOUTS:
        raise ValueError("Unsupported fold, paper size or print layout")
    left, right, top, bottom = validate_margins(margins)
    width, height = PAPERS[paper]
    if layout == "half" and fold != "full":
        # Side fold: landscape sheet, vertical fold. Top fold: portrait sheet, horizontal fold.
        if fold == "side":
            width, height = height, width
        # The fold must bisect the sheet on both printed sides, so margins are symmetric.
        x_margin, y_margin = max(left, right), max(top, bottom)
        box = (x_margin, y_margin, width - x_margin, height - y_margin)
        finished = (width / 2, height) if fold == "side" else (width, height / 2)
        return PaperLayout((width, height), box, finished, (left, right, top, bottom))
    if fold == "top":
        width, height = height, width
    if fold != "full":
        # Both creases must bisect the physical sheet. Centring on an unequal
        # printable rectangle would move the artwork's creases off those folds.
        x_margin, y_margin = max(left, right), max(top, bottom)
        box = (x_margin, y_margin, width - x_margin, height - y_margin)
        finished = (width / 2, height / 2)
    else:
        box = (left, top, width - right, height - bottom)
        finished = (width, height)
    return PaperLayout((width, height), box, finished, (left, right, top, bottom))


def fold_instructions(fold, layout="quarter"):
    if layout == "half" and fold != "full":
        line = "vertical" if fold == "side" else "horizontal"
        return (f"Print two-sided, flip on short edge, at Actual size / 100%. Fold once along the {line} centre line "
                "with side 1 (front and back) outside. Without a duplex unit, print side 1, put the sheet back "
                "in the tray, then print side 2; the test sheet shows which way round.")
    if fold == "side":
        return ("1. With the printed side facing you, fold the top half behind the bottom half. "
                "2. Fold the left half behind the right half. The front remains visible.")
    if fold == "top":
        return ("1. With the landscape print facing you, fold the left half behind the right half. "
                "2. Fold the top half behind the bottom half. The front remains visible.")
    return "Full-page design: no folding needed."


def draw_fold_guides(image, fold, store, dpi, preview=False, layout=None):
    if fold == "full":
        return
    draw = ImageDraw.Draw(image)
    color = "#168189" if preview else "#7b8790"
    dash = max(3, round(dpi * 2 / 25.4))
    thickness = max(1, round(dpi / 180))
    cx, cy = image.width // 2, image.height // 2
    for at in range(0, image.width, dash * 2):
        draw.line((at, cy, min(image.width - 1, at + dash), cy), fill=color, width=thickness)
    for at in range(0, image.height, dash * 2):
        draw.line((cx, at, cx, min(image.height - 1, at + dash)), fill=color, width=thickness)
    font = store.font("Arial", max(9, round(dpi * 7 / 72)), bold=True)
    horizontal = "1. First fold" if fold == "side" else "2. Second fold"
    vertical = "2. Second fold" if fold == "side" else "1. First fold"
    inset = max(2, round(dpi * 2 / 25.4))
    label_left = inset + (round(layout.available_box_mm[0] * dpi / 25.4) if layout else 0)
    label_top = inset + (round(layout.available_box_mm[1] * dpi / 25.4) if layout else 0)
    def label(x, y, text):
        bounds = draw.textbbox((x, y), text, font=font)
        draw.rectangle((bounds[0] - 2, bounds[1] - 1, bounds[2] + 2, bounds[3] + 1), fill="white")
        draw.text((x, y), text, font=font, fill=color)
    label(label_left, cy + inset, horizontal)
    label(cx + inset, label_top, vertical)


def diagnostic_document(fold):
    """Four distinguishable faces, with arrows and corners for a practice fold."""
    from .model import CardDocument, CardObject
    doc = CardDocument(title="Folding and printer test", fold=fold)
    for side in ("front", "inside", "back"):
        if fold == "full" and side != "front":
            continue
        w, h = doc.dimensions(side)
        boxes = [(0.0, 0.0, w, h, side.upper())]
        if side == "inside" and fold == "side":
            boxes = [(0, 0, w / 2, h, "INSIDE LEFT"), (w / 2, 0, w / 2, h, "INSIDE RIGHT")]
        elif side == "inside" and fold == "top":
            boxes = [(0, 0, w, h / 2, "INSIDE TOP"), (0, h / 2, w, h / 2, "INSIDE BOTTOM")]
        for x, y, bw, bh, label in boxes:
            doc.panels[side].append(CardObject("text", x + bw * 0.12, y + bh * 0.38, bw * 0.76, bh * 0.22,
                                               text="UP ↑\n" + label, font="Arial", bold=True, size=28,
                                               color={"front": "#087f86", "inside": "#224987", "back": "#895521"}[side]))
            for name, px, py in (("TL", 0.05, 0.05), ("TR", 0.79, 0.05), ("BL", 0.05, 0.82), ("BR", 0.79, 0.82)):
                doc.panels[side].append(CardObject("text", x + bw * px, y + bh * py, bw * 0.16, bh * 0.07,
                                                   text=name, font="Arial", size=12, color="#445766"))
    return doc


def draw_test_ruler(image, dpi, store, layout):
    draw = ImageDraw.Draw(image)
    to_px = lambda mm: round(mm * dpi / 25.4)
    cx = image.width // 2
    start = cx - to_px(50)
    y = to_px(layout.available_box_mm[1] + 7)
    draw.line((start, y, start + to_px(100), y), fill="#172f43", width=max(1, round(dpi / 150)))
    for mm in range(0, 101, 10):
        x = start + to_px(mm)
        draw.line((x, y - to_px(1.5), x, y + to_px(1.5)), fill="#172f43", width=max(1, round(dpi / 180)))
    font = store.font("Arial", max(9, round(dpi * 8 / 72)))
    text = "100 mm - print at Actual size / 100%"
    width = draw.textlength(text, font=font)
    origin = (cx - width / 2, y + to_px(2))
    bounds = draw.textbbox(origin, text, font=font)
    draw.rectangle((bounds[0] - to_px(1), bounds[1] - to_px(0.5), bounds[2] + to_px(1), bounds[3] + to_px(0.5)), fill="white")
    draw.text(origin, text, font=font, fill="#172f43")
