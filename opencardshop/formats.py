"""Strict readers for the formats found in the supplied CardShop Plus archive.

CMF = SZDD-compressed placeable WMF, not a proprietary deferred-drawing format.
CMK uses MFC CArchive class identifiers, counted panels and CString lengths.
The observations and limits are documented in docs/REVERSE_ENGINEERING.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import copy
import struct


class FormatError(ValueError):
    """Input is damaged or uses a format this application cannot decode."""


def expand_szdd(data: bytes, max_size: int = 32 * 1024 * 1024) -> bytes:
    if not data.startswith(b"SZDD"):
        if len(data) > max_size:
            raise FormatError("Graphic exceeds the size limit")
        return data
    if len(data) < 14 or data[:8] != b"SZDD\x88\xf0\x27\x33" or data[8] != 0x41:
        raise FormatError("Unsupported SZDD header or compression method")
    expected = struct.unpack_from("<I", data, 10)[0]
    if expected > max_size:
        raise FormatError("Decompressed graphic exceeds the size limit")
    window = bytearray(b" " * 4096)
    write_pos, read_pos = 4080, 14
    result = bytearray()
    while len(result) < expected:
        if read_pos >= len(data):
            raise FormatError("Truncated SZDD control byte")
        flags = data[read_pos]
        read_pos += 1
        for bit in range(8):
            if len(result) == expected:
                break
            if flags & (1 << bit):
                if read_pos >= len(data):
                    raise FormatError("Truncated SZDD literal")
                values = (data[read_pos],)
                read_pos += 1
                for value in values:
                    result.append(value)
                    window[write_pos] = value
                    write_pos = (write_pos + 1) & 4095
            else:
                if read_pos + 2 > len(data):
                    raise FormatError("Truncated SZDD back-reference")
                lo, hi = data[read_pos:read_pos + 2]
                read_pos += 2
                source = lo | ((hi & 0xF0) << 4)
                count = (hi & 0x0F) + 3
                for offset in range(count):
                    if len(result) == expected:
                        break
                    value = window[(source + offset) & 4095]
                    result.append(value)
                    window[write_pos] = value
                    write_pos = (write_pos + 1) & 4095
    return bytes(result)


@dataclass
class LegacyObject:
    kind: str
    bounds: tuple[int, int, int, int]
    art: str = ""
    text: str = ""
    font: str = "Arial"
    height: int = 250
    width: int = 0
    weight: int = 400
    align: int = 1
    color: str = "#000000"
    italic: bool = False
    underline: bool = False
    strike: bool = False
    raw_font: bytes = b""


@dataclass
class LegacyCard:
    fold: str
    panels: dict[str, list[LegacyObject]]
    signature: str
    header_flags: int | None = None


class ArchiveReader:
    def __init__(self, data: bytes):
        if len(data) > 4 * 1024 * 1024:
            raise FormatError("Card exceeds the input size limit")
        self.data, self.pos = data, 0
        self.next_id = 1
        self.classes: dict[int, str] = {}
        self.objects: dict[int, LegacyObject] = {}

    def take(self, count: int) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise FormatError(f"Truncated card at byte {self.pos}")
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def word(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def string(self) -> str:
        count = self.take(1)[0]
        if count == 0xFF:
            count = self.word()
            if count == 0xFFFF:
                count = struct.unpack("<I", self.take(4))[0]
        if count > 1_000_000:
            raise FormatError("Card string exceeds the size limit")
        return self.take(count).decode("cp1252", errors="replace")

    def object(self) -> LegacyObject:
        tag = self.word()
        if tag == 0xFFFF:
            schema = self.word()
            class_length = self.word()
            if schema != 0 or class_length > 128:
                raise FormatError("Unsupported CMK class schema")
            name = self.take(class_length).decode("ascii")
            self.classes[self.next_id] = name
            self.next_id += 1
        elif tag & 0x8000:
            name = self.classes.get(tag & 0x7FFF)
            if name is None:
                raise FormatError(f"Unknown CMK class reference {tag:#x}")
        else:
            if tag not in self.objects:
                raise FormatError(f"Unknown CMK object reference {tag:#x}")
            return copy.copy(self.objects[tag])
        identifier = self.next_id
        self.next_id += 1
        bounds = struct.unpack("<hhhh", self.take(8))
        obj = LegacyObject(kind=name, bounds=bounds)
        if name == "CGraphic":
            # Resolve DOS/Windows paths by basename; never follow a stored path.
            obj.art = self.string().replace("\\", "/").rsplit("/", 1)[-1].upper()
        elif name == "CTextObj":
            obj.align = self.word()
            rgb = self.take(4)
            obj.color = "#" + rgb[:3].hex()
            obj.text = self.string().replace("\r\n", "\n").replace("\r", "\n")
            tail = self.take(26)
            obj.height, obj.width, obj.weight = struct.unpack_from("<iii", tail)
            obj.italic, obj.underline, obj.strike = (bool(v) for v in struct.unpack_from("<HHH", tail, 12))
            obj.raw_font = tail
            obj.font = self.string()
            if abs(obj.height) > 50_000 or len(obj.font) > 256:
                raise FormatError("Invalid CMK font metrics")
        else:
            raise FormatError(f"Unsupported CMK class {name}")
        self.objects[identifier] = obj
        return obj

    def card(self) -> LegacyCard:
        signature = self.string()
        if signature not in ("Card Maker copyright (c) 1993", "Card Maker copyright (c) 1993 V1.20"):
            raise FormatError("Not a supported CardShop CMK card")
        header_flags = self.word() if signature.endswith("V1.20") else None
        if header_flags not in (None, 0):
            raise FormatError("This CMK uses an unverified V1.20 header flag; embedded Full Save variants are not yet supported")
        fold = {0: "top", 1: "side", 2: "full"}.get(self.word())
        if fold is None:
            raise FormatError("Unknown CMK fold type")
        panels: dict[str, list[LegacyObject]] = {}
        for side in ("front", "inside", "back"):
            count = self.word()
            if count > 4096:
                raise FormatError("Too many objects in a CMK panel")
            panels[side] = [self.object() for _ in range(count)]
        if self.pos != len(self.data):
            raise FormatError(f"Unparsed CMK data at byte {self.pos}")
        return LegacyCard(fold, panels, signature, header_flags)


def read_cmk(path: str | Path) -> LegacyCard:
    return ArchiveReader(Path(path).read_bytes()).card()


@dataclass
class Message:
    front: str = ""
    inside: str = ""
    back: str = ""

    @property
    def label(self) -> str:
        return (self.front or self.inside or self.back).replace("\n", " ")[:120]


def read_messages(path: str | Path) -> list[Message]:
    text = Path(path).read_bytes().decode("cp1252", errors="replace")
    messages: list[Message] = []
    current: Message | None = None
    section = ""
    for line in text.splitlines():
        if line.startswith("|") or line == "\x1a":
            continue
        marker = line[:1]
        if marker == "]":
            current = Message(front=line[1:])
            messages.append(current)
            section = "front"
        elif marker == "[":
            if current is None or current.back or current.inside:
                current = Message()
                messages.append(current)
            current.inside = line[1:]
            section = "inside"
        elif marker == "}":
            current = Message(back=line[1:])
            messages.append(current)
            section = "back"
        elif current is not None and section:
            value = getattr(current, section)
            setattr(current, section, value + "\n" + line)
    for message in messages:
        message.front = message.front.strip()
        message.inside = message.inside.strip()
        message.back = message.back.strip()
    return [m for m in messages if m.front or m.inside or m.back]


@dataclass
class WMF:
    bounds: tuple[int, int, int, int]
    inch: int
    object_count: int
    records: list[tuple[int, bytes]] = field(default_factory=list)


def read_wmf(data: bytes) -> WMF:
    data = expand_szdd(data)
    if len(data) < 40 or data[:4] != b"\xd7\xcd\xc6\x9a":
        raise FormatError("Expected a placeable Windows Metafile")
    bounds = struct.unpack_from("<hhhh", data, 6)
    inch = struct.unpack_from("<H", data, 14)[0]
    if inch == 0 or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise FormatError("Invalid WMF bounds or scale")
    checksum = 0
    for word in struct.unpack_from("<10H", data):
        checksum ^= word
    if checksum != struct.unpack_from("<H", data, 20)[0]:
        raise FormatError("WMF placeable header checksum mismatch")
    file_type, header_words, version, file_words, count, max_record, params = struct.unpack_from("<HHHIHIH", data, 22)
    if header_words != 9 or version not in (0x100, 0x300) or file_type not in (1, 2):
        raise FormatError("Unsupported WMF header")
    if file_words * 2 != len(data) - 22:
        raise FormatError("WMF declared length does not match its contents")
    result = WMF(bounds, inch, count)
    offset = 40
    while offset + 6 <= len(data):
        words, command = struct.unpack_from("<IH", data, offset)
        if words < 3 or offset + words * 2 > len(data):
            raise FormatError(f"Invalid WMF record at byte {offset}")
        result.records.append((command, data[offset + 6:offset + words * 2]))
        offset += words * 2
        if command == 0:
            if offset != len(data):
                raise FormatError("Unexpected data after WMF end record")
            return result
    raise FormatError("WMF has no end record")
