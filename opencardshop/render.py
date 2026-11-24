"""Document compositor, text layout and single-sheet quarter-fold printing."""
from __future__ import annotations

from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageColor

from .formats import FormatError
from .model import CardDocument
from .printing import paper_layout, draw_fold_guides, diagnostic_document, draw_test_ruler
from .printing import DEFAULT_MARGINS


def _wrap(text, font, width, draw):
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph or draw.textlength(paragraph, font=font) <= width:
            lines.append(paragraph)
            continue
        line = ""
        for word in paragraph.split(" "):
            candidate = word if not line else line + " " + word
            if line and draw.textlength(candidate, font=font) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def _layout(obj, text, store, doc, scale, width, height):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    wanted = max(1, round(obj.size / 72.0 * 1000.0 * scale))

    def measure(pixels):
        font = store.font(obj.font, pixels, obj.bold, obj.italic, doc)
        if obj.legacy_cell_height:
            ascent, descent = font.getmetrics()
            font = store.font(obj.font, max(1, round(pixels * pixels / max(1, ascent + descent))), obj.bold, obj.italic, doc)
        face_name = font.getname()[1].casefold()
        stroke = max(1, round(pixels / 45)) if obj.bold and "bold" not in face_name else 0
        spacing = max(0, round(pixels * 0.07))
        lines = _wrap(text, font, max(1, width - 2 * stroke), probe)
        bounds = [probe.textbbox((0, 0), line or " ", font=font, stroke_width=stroke) for line in lines]
        # Match the original positive LOGFONT cell-height for imported text.
        line_height = max(1, pixels if obj.legacy_cell_height else sum(font.getmetrics()))
        used_width = max((b[2] - b[0] for b in bounds), default=0)
        used_height = line_height * len(lines) + spacing * max(0, len(lines) - 1)
        return font, stroke, spacing, line_height, lines, bounds, used_width, used_height

    result = measure(wanted)
    if obj.auto_fit and (result[6] > width or result[7] > height):
        low, high, best = 1, wanted, result
        while low <= high:
            mid = (low + high) // 2
            candidate = measure(mid)
            if candidate[6] <= width and candidate[7] <= height:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        result = best if high >= 1 else measure(1)
    return result


def _draw_text(image, obj, doc, store, scale):
    text = doc.substitute(obj.text)
    if not text:
        return
    if len(text) > 20_000:
        raise FormatError("A text object exceeds the 20,000-character render limit")
    width, height = max(1, round(obj.w * scale)), max(1, round(obj.h * scale))
    if width * height > 40_000_000:
        raise FormatError("A text box is too large to render")
    font, stroke, spacing, line_height, lines, bounds, used_w, used_h = _layout(obj, text, store, doc, scale, width, height)
    color = ImageColor.getrgb(obj.color)
    # Render per object so clipping, synthetic italic and decoration stay local.
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index, (line, box) in enumerate(zip(lines, bounds)):
        line_width = box[2] - box[0]
        x = (width - line_width) / 2 if obj.align == "center" else (width - line_width if obj.align == "right" else 0)
        y = index * (line_height + spacing)
        draw.text((x - box[0], y - box[1]), line, font=font, fill=color, stroke_width=stroke, stroke_fill=color)
        thickness = max(1, round(line_height / 18))
        if obj.underline:
            underline_y = min(height - 1, y + box[3] - box[1] + thickness)
            draw.line((x, underline_y, x + line_width, underline_y), fill=color, width=thickness)
        if obj.strike:
            strike_y = y + max(1, box[3] - box[1]) * 0.55
            draw.line((x, strike_y, x + line_width, strike_y), fill=color, width=thickness)
    if obj.italic and "italic" not in font.getname()[1].casefold() and "oblique" not in font.getname()[1].casefold():
        layer = layer.transform(layer.size, Image.Transform.AFFINE, (1, 0.18, -0.18 * height, 0, 1, 0), Image.Resampling.BICUBIC)
    image.alpha_composite(layer, (round(obj.x * scale), round(obj.y * scale)))


def render_panel(doc: CardDocument, side: str, store, width: int | None = None, dpi: float = 150.0,
                 guides: bool = False, background="white", errors: list | None = None) -> Image.Image:
    units_w, units_h = doc.dimensions(side)
    scale = width / units_w if width else dpi / 1000.0
    pixels_w, pixels_h = max(1, round(units_w * scale)), max(1, round(units_h * scale))
    if pixels_w * pixels_h > 40_000_000:
        raise FormatError("Panel exceeds the 40-megapixel render limit")
    image = Image.new("RGBA", (pixels_w, pixels_h), background)
    for obj in doc.panels[side]:
        if obj.x + obj.w <= 0 or obj.y + obj.h <= 0 or obj.x >= units_w or obj.y >= units_h:
            continue
        try:
            if obj.kind == "text":
                _draw_text(image, obj, doc, store, scale)
            else:
                source = store.image(obj.art, doc)
                x, y, w, h = obj.x * scale, obj.y * scale, obj.w * scale, obj.h * scale
                left, top = max(0, math.floor(x)), max(0, math.floor(y))
                right, bottom = min(pixels_w, math.ceil(x + w)), min(pixels_h, math.ceil(y + h))
                if right <= left or bottom <= top:
                    continue
                source_box = ((left - x) / w * source.width, (top - y) / h * source.height,
                              (right - x) / w * source.width, (bottom - y) / h * source.height)
                tile = source.transform((right - left, bottom - top), Image.Transform.EXTENT,
                                        source_box, Image.Resampling.BICUBIC)
                image.alpha_composite(tile, (left, top))
        except (FormatError, OSError, ValueError) as exc:
            if errors is None:
                raise
            errors.append(f"{obj.art or obj.font}: {exc}")
            draw = ImageDraw.Draw(image)
            box = (obj.x * scale, obj.y * scale, (obj.x + obj.w) * scale, (obj.y + obj.h) * scale)
            draw.rectangle(box, outline="#bd382c", width=2)
            draw.text((max(0, box[0]) + 5, max(0, box[1]) + 5), "Unavailable artwork", fill="#bd382c")
    if guides and doc.fold != "full" and side == "inside":
        draw = ImageDraw.Draw(image)
        if doc.fold == "side":
            _dashed(draw, (pixels_w / 2, 0, pixels_w / 2, pixels_h), "#bbc6d0")
        else:
            _dashed(draw, (0, pixels_h / 2, pixels_w, pixels_h / 2), "#bbc6d0")
    return image


def _dashed(draw, line, color, dash=12):
    x1, y1, x2, y2 = line
    distance = math.hypot(x2 - x1, y2 - y1)
    if not distance:
        return
    for start in range(0, math.ceil(distance), dash * 2):
        end = min(distance, start + dash)
        draw.line((x1 + (x2 - x1) * start / distance, y1 + (y2 - y1) * start / distance,
                   x1 + (x2 - x1) * end / distance, y1 + (y2 - y1) * end / distance), fill=color, width=1)


def compose_flat_sheet(doc: CardDocument, store, dpi=150, guides=False) -> Image.Image:
    """Impose all three editing views onto one printed side of one sheet.

    Side: upside-down inside across upper half; back/front across lower half.
    Top: upside-down inside down left half; upside-down back above front at right.
    Fold with printed surfaces outside at each fold; instructions are in USER_GUIDE.
    """
    if doc.fold == "full":
        return render_panel(doc, "front", store, dpi=dpi)
    front = render_panel(doc, "front", store, dpi=dpi)
    back = render_panel(doc, "back", store, dpi=dpi)
    inside = render_panel(doc, "inside", store, dpi=dpi)
    if doc.fold == "side":
        page = Image.new("RGBA", (front.width * 2, front.height * 2), "white")
        page.alpha_composite(inside.transpose(Image.Transpose.ROTATE_180), (0, 0))
        page.alpha_composite(back, (0, front.height))
        page.alpha_composite(front, (front.width, front.height))
    else:
        page = Image.new("RGBA", (front.width * 2, front.height * 2), "white")
        page.alpha_composite(inside.transpose(Image.Transpose.ROTATE_180), (0, 0))
        page.alpha_composite(back.transpose(Image.Transpose.ROTATE_180), (front.width, 0))
        page.alpha_composite(front, (front.width, front.height))
    if guides:
        draw = ImageDraw.Draw(page)
        _dashed(draw, (page.width / 2, 0, page.width / 2, page.height), "#b8c1cb", max(4, round(dpi / 15)))
        _dashed(draw, (0, page.height / 2, page.width, page.height / 2), "#b8c1cb", max(4, round(dpi / 15)))
    return page


def print_sheet(doc: CardDocument, store, paper="A4", dpi=300, margin_mm=5.0, guides=False,
                *, margins=None, test_page=False, preview_guides=False) -> Image.Image:
    if not math.isfinite(dpi) or not 36 <= dpi <= 600:
        raise ValueError("Choose a resolution from 36 to 600 dpi")
    layout = paper_layout(doc.fold, paper, margins if margins is not None else (margin_mm,) * 4)
    mm_w, mm_h = layout.size_mm
    size = (round(mm_w / 25.4 * dpi), round(mm_h / 25.4 * dpi))
    sheet = Image.new("RGB", size, "white")
    flat = compose_flat_sheet(diagnostic_document(doc.fold) if test_page else doc, store, dpi=dpi)
    left, top, right, bottom = (round(value / 25.4 * dpi) for value in layout.available_box_mm)
    available = (right - left, bottom - top)
    ratio = min(available[0] / flat.width, available[1] / flat.height)
    resized = flat.resize((max(1, round(flat.width * ratio)), max(1, round(flat.height * ratio))), Image.Resampling.LANCZOS).convert("RGB")
    if doc.fold == "full":
        # Full-page designs centre inside their printable rectangle.
        cx, cy = (left + right) / 2, (top + bottom) / 2
        sheet.paste(resized, (round(cx - resized.width / 2), round(cy - resized.height / 2)))
    else:
        _place_quarters(sheet, resized, doc.fold, left, top)
    if guides or test_page or preview_guides:
        draw_fold_guides(sheet, doc.fold, store, dpi, preview=preview_guides and not guides and not test_page, layout=layout)
    if test_page:
        # Drawn after the guides so the dashed fold line does not cross the ruler caption.
        draw = ImageDraw.Draw(sheet)
        draw.rectangle((left, top, right - 1, bottom - 1), outline="#6e7e87", width=max(1, round(dpi / 180)))
        draw_test_ruler(sheet, dpi, store, layout)
    return sheet


def _place_quarters(sheet, flat, fold, margin_x, margin_y):
    """Centre each folded panel within its quarter of the physical sheet.

    The designs are Letter-proportioned, so on A4 or Legal there is spare space
    in one direction. Panels stay against the hinge crease (the spine of a side
    fold, the top edge of a top fold) so artwork spanning an open spread stays
    continuous, and the spare space is shared equally between the panel's other
    folded edge and its cut edge, never encroaching on the printer margin.
    """
    qx, qy = sheet.width / 2, sheet.height / 2
    lw, th = flat.width // 2, flat.height // 2
    rw, bh = flat.width - lw, flat.height - th

    def gap(quarter, content, margin):
        return max(0.0, min((quarter - content) / 2, quarter - content - margin))

    dx = 0.0 if fold == "side" else gap(qx, max(lw, rw), margin_x)
    dy = 0.0 if fold == "top" else gap(qy, max(th, bh), margin_y)
    for column, (x0, x1) in enumerate(((0, lw), (lw, flat.width))):
        for row, (y0, y1) in enumerate(((0, th), (th, flat.height))):
            x = round(qx - dx) - (x1 - x0) if column == 0 else round(qx + dx)
            y = round(qy - dy) - (y1 - y0) if row == 0 else round(qy + dy)
            sheet.paste(flat.crop((x0, y0, x1, y1)), (x, y))


def half_fold_pages(doc: CardDocument, store, paper="A4", dpi=300, margins=DEFAULT_MARGINS, guides=False, *,
                    test_page=False, rotate_second=False, preview_guides=False) -> list[Image.Image]:
    """Two sheet sides for a card folded once: side 1 carries the back and front, side 2 the inside spread.

    Side fold, landscape sheet:  side 1 = [back | front], side 2 = [inside left | inside right].
    Top fold, portrait sheet:    side 1 = back (upside down) above front, side 2 = inside top above inside bottom.
    Printed two-sided with flip on short edge, the inside half behind the front is the inside panel next
    to the front once folded. Each spread is centred, so the fold falls on the sheet's centre line on both
    sides. rotate_second turns side 2 by 180 degrees for printers that feed a re-inserted sheet the other way.
    """
    if doc.fold == "full":
        return [print_sheet(doc, store, paper, dpi, guides=guides, margins=margins, test_page=test_page,
                            preview_guides=preview_guides)]
    if not math.isfinite(dpi) or not 36 <= dpi <= 600:
        raise ValueError("Choose a resolution from 36 to 600 dpi")
    layout = paper_layout(doc.fold, paper, margins, layout="half")
    source = diagnostic_document(doc.fold) if test_page else doc
    front, back, inside = (render_panel(source, side, store, dpi=dpi) for side in ("front", "back", "inside"))
    if doc.fold == "side":
        outside = Image.new("RGBA", (front.width * 2, front.height), "white")
        outside.alpha_composite(back, (0, 0))
        outside.alpha_composite(front, (front.width, 0))
    else:
        outside = Image.new("RGBA", (front.width, front.height * 2), "white")
        outside.alpha_composite(back.transpose(Image.Transpose.ROTATE_180), (0, 0))
        outside.alpha_composite(front, (0, front.height))
    to_px = lambda mm: round(mm / 25.4 * dpi)
    size = (to_px(layout.size_mm[0]), to_px(layout.size_mm[1]))
    left, top, right, bottom = (to_px(v) for v in layout.available_box_mm)
    pages = []
    for number, spread in enumerate((outside, inside), 1):
        sheet = Image.new("RGB", size, "white")
        ratio = min((right - left) / spread.width, (bottom - top) / spread.height)
        resized = spread.resize((max(1, round(spread.width * ratio)), max(1, round(spread.height * ratio))),
                                Image.Resampling.LANCZOS).convert("RGB")
        sheet.paste(resized, (round(size[0] / 2 - resized.width / 2), round(size[1] / 2 - resized.height / 2)))
        draw = ImageDraw.Draw(sheet)
        if guides or test_page or preview_guides:
            color = "#168189" if preview_guides and not guides and not test_page else "#7b8790"
            line = (size[0] / 2, 0, size[0] / 2, size[1]) if doc.fold == "side" else (0, size[1] / 2, size[0], size[1] / 2)
            _dashed(draw, line, color, max(3, to_px(2)))
        if test_page:
            draw.rectangle((left, top, right - 1, bottom - 1), outline="#6e7e87", width=max(1, round(dpi / 180)))
            _registration_marks(draw, doc.fold, size, layout, dpi, scale=number == 2)
            font = store.font("Arial", max(9, round(dpi * 9 / 72)), bold=True)
            label = f"SIDE {number} OF 2 - " + ("OUTSIDE: BACK AND FRONT" if number == 1 else "INSIDE")
            width = draw.textlength(label, font=font)
            draw.text((size[0] / 2 - width / 2, bottom - to_px(9)), label, font=font, fill="#172f43")
            if number == 1:
                draw_test_ruler(sheet, dpi, store, layout)
        if number == 2 and rotate_second:
            sheet = sheet.transpose(Image.Transpose.ROTATE_180)
        pages.append(sheet)
    return pages


def _registration_marks(draw, fold, size, layout, dpi, scale=False):
    """Targets on the fold line at the same physical place on both sides. Hold the printed test
    sheet to the light: side 1's targets should sit on side 2's, and side 2's millimetre scale
    across the fold shows any shift."""
    to_px = lambda mm: round(mm / 25.4 * dpi)
    left, top, right, bottom = (to_px(v) for v in layout.available_box_mm)
    cx, cy = size[0] / 2, size[1] / 2
    points = [(cx, top + to_px(25)), (cx, bottom - to_px(25))] if fold == "side" else [(left + to_px(25), cy), (right - to_px(25), cy)]
    width, radius, arm = max(1, round(dpi / 150)), to_px(3), to_px(6)
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="#bd382c", width=width)
        draw.line((x - arm, y, x + arm, y), fill="#bd382c", width=width)
        draw.line((x, y - arm, x, y + arm), fill="#bd382c", width=width)
        if scale:
            for mm in range(-5, 6):
                tick = to_px(1.5 if mm % 5 else 3)
                if fold == "side":
                    tx = x + to_px(mm)
                    draw.line((tx, y + to_px(8), tx, y + to_px(8) + tick), fill="#172f43", width=width)
                else:
                    ty = y + to_px(mm)
                    draw.line((x + to_px(8), ty, x + to_px(8) + tick, ty), fill="#172f43", width=width)


def side_by_side(pages: list[Image.Image], gap: int = 24) -> Image.Image:
    """Show both printed sides of a two-sided layout next to each other (previews and PNG export)."""
    if len(pages) == 1:
        return pages[0]
    height = max(page.height for page in pages)
    result = Image.new("RGB", (sum(page.width for page in pages) + gap * (len(pages) - 1), height), "#c9d2da")
    x = 0
    for page in pages:
        result.paste(page, (x, (height - page.height) // 2))
        x += page.width + gap
    return result


def export_pdf(doc: CardDocument, store, path: str | Path, paper="A4", dpi=300, margin_mm=5.0, guides=False,
               *, margins=None, test_page=False, layout="quarter", rotate_second=False):
    title = "Folding and printer test" if test_page else doc.title
    if layout == "half" and doc.fold != "full":
        pages = half_fold_pages(doc, store, paper, dpi, margins if margins is not None else (margin_mm,) * 4, guides,
                                test_page=test_page, rotate_second=rotate_second)
        pages[0].save(path, "PDF", resolution=float(dpi), quality=95, save_all=True, append_images=pages[1:],
                      title=title, author="OpenCardShop", subject="Two-sided greeting card, folded once")
        return
    sheet = print_sheet(doc, store, paper, dpi, margin_mm, guides, margins=margins, test_page=test_page)
    sheet.save(path, "PDF", resolution=float(dpi), quality=95, title=title,
               author="OpenCardShop", subject="Single-sided folded greeting card")


def export_panel(doc, side, store, path, dpi=300):
    image = render_panel(doc, side, store, dpi=dpi)
    image.save(path, "PNG", dpi=(dpi, dpi))
