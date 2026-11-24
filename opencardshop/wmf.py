"""Pillow playback of the WMF record subset present in this asset collection.

Prepared PNGs were generated with Inkscape's WMF reader. This independent
renderer makes newly selected asset folders usable without Inkscape, Wine,
Windows, Cairo, network services or a compiler.
"""
from __future__ import annotations

import struct
from PIL import Image, ImageChops, ImageDraw, ImageFont
from .formats import FormatError, read_wmf


def render_wmf(data: bytes, size: tuple[int, int], font_loader=None) -> Image.Image:
    metafile = read_wmf(data)
    if metafile.object_count > 4096:
        raise FormatError("WMF object table exceeds the size limit")
    width, height = (max(1, min(4096, int(v))) for v in size)
    aa = 2 if max(width, height) <= 1800 else 1
    width *= aa
    height *= aa
    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = metafile.bounds
    origin = [left, bottom]
    extent = [right - left, top - bottom]
    table: list[dict | None] = [None] * max(1, metafile.object_count)
    pen = {"type": "pen", "style": 0, "width": 0, "color": (0, 0, 0, 255)}
    brush = {"type": "brush", "style": 0, "color": (255, 255, 255, 255)}
    font = {"type": "font", "family": "Arial", "height": 120, "weight": 400}
    text_color, background, background_mode, alignment, fill_mode = (0, 0, 0, 255), (255, 255, 255, 255), 1, 0, 1

    def insert(obj):
        for index, slot in enumerate(table):
            if slot is None:
                table[index] = obj
                return
        raise FormatError("WMF creates more objects than its table allows")

    def point(x, y):
        return ((x - origin[0]) / extent[0] * width, (y - origin[1]) / extent[1] * height)

    def stroke_width():
        return max(aa, round(abs(pen["width"] / extent[0] * width)))

    def area(points):
        return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))

    def polygons(contours, closed=True):
        contours = [[point(x, y) for x, y in contour] for contour in contours]
        if closed and brush["style"] != 1:
            color = brush["color"]
            if len(contours) == 1:
                draw.polygon(contours[0], fill=color)
            else:
                mask = Image.new("1", (width, height), 0)
                if fill_mode == 1:
                    for contour in contours:
                        layer = Image.new("1", (width, height), 0)
                        ImageDraw.Draw(layer).polygon(contour, fill=1)
                        mask = ImageChops.logical_xor(mask, layer)
                else:
                    ordered = sorted(contours, key=lambda c: abs(area(c)), reverse=True)
                    outer_sign = 1 if area(ordered[0]) >= 0 else -1
                    mask_draw = ImageDraw.Draw(mask)
                    for contour in ordered:
                        mask_draw.polygon(contour, fill=int(area(contour) * outer_sign >= 0))
                image.paste(color, (0, 0), mask)
        if pen["style"] & 0xF != 5:
            for contour in contours:
                if len(contour) < 2:
                    continue
                points = contour + [contour[0]] if closed else contour
                draw.line(points, fill=pen["color"], width=stroke_width(), joint="curve")

    for command, payload in metafile.records:
        if command == 0:
            break
        if command == 0x020B:
            y, x = struct.unpack_from("<hh", payload)
            origin = [x, y]
        elif command == 0x020C:
            y, x = struct.unpack_from("<hh", payload)
            if not x or not y:
                raise FormatError("Zero WMF window extent")
            extent = [x, y]
        elif command == 0x02FA:
            style, x, y = struct.unpack_from("<Hhh", payload)
            insert({"type": "pen", "style": style, "width": x, "color": tuple(payload[6:9]) + (255,)})
        elif command == 0x02FC:
            style = struct.unpack_from("<H", payload)[0]
            if style not in (0, 1):
                raise FormatError("Hatched WMF brushes require an external WMF renderer")
            insert({"type": "brush", "style": style, "color": tuple(payload[2:5]) + (255,)})
        elif command == 0x02FB:
            h, w, esc, orientation, weight = struct.unpack_from("<hhhhh", payload)
            if esc or orientation:
                raise FormatError("Rotated WMF text requires an external WMF renderer")
            insert({"type": "font", "family": payload[18:].split(b"\0", 1)[0].decode("cp1252", "replace"),
                    "height": h, "weight": weight})
        elif command == 0x012D:
            index = struct.unpack_from("<H", payload)[0]
            if index & 0x8000:
                stock = index & 0x7FFF
                if stock in (0, 1, 2, 3, 4, 5):
                    value = [255, 192, 128, 64, 0, 0][stock]
                    selected = {"type": "brush", "style": 1 if stock == 5 else 0, "color": (value, value, value, 255)}
                elif stock in (6, 7, 8):
                    value = 255 if stock == 6 else 0
                    selected = {"type": "pen", "style": 5 if stock == 8 else 0, "width": 0, "color": (value, value, value, 255)}
                else:
                    selected = font
            else:
                selected = table[index] if index < len(table) else None
            if selected is None:
                raise FormatError("WMF selects a missing graphics object")
            if selected["type"] == "pen":
                pen = selected
            elif selected["type"] == "brush":
                brush = selected
            elif selected["type"] == "font":
                font = selected
        elif command == 0x01F0:
            index = struct.unpack_from("<H", payload)[0]
            if index >= len(table):
                raise FormatError("WMF deletes an invalid graphics object")
            table[index] = None
        elif command == 0x0106:
            fill_mode = struct.unpack_from("<H", payload)[0]
        elif command in (0x0324, 0x0325):
            count = struct.unpack_from("<H", payload)[0]
            if count == 0 or 2 + count * 4 > len(payload):
                raise FormatError("Invalid WMF polygon")
            coordinates = struct.unpack_from("<" + "hh" * count, payload, 2)
            points = list(zip(coordinates[::2], coordinates[1::2]))
            polygons([points], closed=command == 0x0324)
        elif command == 0x0538:
            count = struct.unpack_from("<H", payload)[0]
            lengths = struct.unpack_from("<" + "H" * count, payload, 2)
            offset = 2 + count * 2
            if not count or offset + sum(lengths) * 4 > len(payload):
                raise FormatError("Invalid WMF polypolygon")
            contours = []
            for length in lengths:
                coords = struct.unpack_from("<" + "hh" * length, payload, offset)
                contours.append(list(zip(coords[::2], coords[1::2])))
                offset += length * 4
            polygons(contours)
        elif command == 0x0209:
            text_color = tuple(payload[:3]) + (255,)
        elif command == 0x0201:
            background = tuple(payload[:3]) + (255,)
        elif command == 0x0102:
            background_mode = struct.unpack_from("<H", payload)[0]
        elif command == 0x012E:
            alignment = struct.unpack_from("<H", payload)[0]
        elif command == 0x0521:
            count = struct.unpack_from("<H", payload)[0]
            text = payload[2:2 + count].decode("cp1252", "replace")
            coordinate_offset = 2 + count + (count & 1)
            y, x = struct.unpack_from("<hh", payload, coordinate_offset)
            position = point(x, y)
            pixels = max(1, round(abs(font["height"] / extent[1] * height)))
            if font_loader:
                face = font_loader(font["family"], pixels, font["weight"] >= 600, False)
            else:
                face = ImageFont.truetype("DejaVuSans.ttf", pixels)
            horizontal = "m" if alignment & 6 == 6 else ("r" if alignment & 2 else "l")
            vertical = "s" if alignment & 24 == 24 else ("b" if alignment & 8 else "t")
            anchor = horizontal + vertical
            if background_mode == 2 and text:
                box = draw.textbbox(position, text, font=face, anchor=anchor)
                draw.rectangle(box, fill=background)
            draw.text(position, text, font=face, fill=text_color, anchor=anchor)
        elif command == 0x0104:
            if struct.unpack_from("<H", payload)[0] != 13:
                raise FormatError("Unsupported WMF raster operation")
        elif command == 0x0105:
            # META_SETRELABS is undefined and must be ignored by WMF readers.
            pass
        else:
            raise FormatError(f"WMF command {command:#06x} is outside this collection's renderer subset")
    return image.resize((width // aa, height // aa), Image.Resampling.LANCZOS) if aa != 1 else image
