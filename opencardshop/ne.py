"""Bounded, read-only inspection of Windows 16-bit New Executable files.

This module never loads or executes the inspected program. It retains file
offsets so resource and relocation findings can be independently checked.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import hashlib
import re
import struct

from .formats import FormatError

RESOURCE_TYPES = {1: "cursor", 2: "bitmap", 3: "icon", 4: "menu", 5: "dialog",
                  6: "string_table", 7: "font_directory", 8: "font", 9: "accelerator",
                  10: "raw_data", 12: "cursor_group", 14: "icon_group", 16: "version",
                  240: "dialog_initialisation"}
CONTROL_CLASSES = {0x80: "Button", 0x81: "Edit", 0x82: "Static", 0x83: "ListBox",
                   0x84: "ScrollBar", 0x85: "ComboBox"}


class Reader:
    def __init__(self, data: bytes, pos: int = 0, end: int | None = None):
        self.data, self.pos = data, pos
        self.end = len(data) if end is None else end
        if not 0 <= pos <= self.end <= len(data):
            raise FormatError("Invalid NE byte range")

    def take(self, count: int) -> bytes:
        if count < 0 or self.pos + count > self.end:
            raise FormatError(f"Truncated NE data at byte {self.pos}")
        value = self.data[self.pos:self.pos + count]
        self.pos += count
        return value

    def byte(self):
        return self.take(1)[0]

    def word(self):
        return struct.unpack("<H", self.take(2))[0]

    def cstring(self):
        end = self.data.find(b"\0", self.pos, self.end)
        if end < 0 or end - self.pos > 65535:
            raise FormatError("Unterminated NE resource string")
        value = self.take(end - self.pos).decode("cp1252", "replace")
        self.take(1)
        return value

    def resource_name(self, control=False):
        first = self.data[self.pos] if self.pos < self.end else self.byte()
        if first == 0xFF:
            self.byte()
            return {"ordinal": self.word()}
        if control and first & 0x80:
            return CONTROL_CLASSES.get(self.byte(), f"class_{first:#x}")
        return self.cstring()


def _dialog(data: bytes) -> dict:
    r = Reader(data)
    style = struct.unpack("<I", r.take(4))[0]
    count = r.byte()
    bounds = list(struct.unpack("<hhhh", r.take(8)))
    menu, window_class, caption = r.resource_name(), r.resource_name(), r.cstring()
    result = {"caption": caption, "style": f"0x{style:08x}", "bounds": bounds,
              "menu": menu, "class": window_class, "controls": []}
    if style & 0x40:  # DS_SETFONT: point size followed by an ANSI face name.
        result["font"] = {"points": r.word(), "family": r.cstring()}
    for _ in range(count):
        box = list(struct.unpack("<hhhh", r.take(8)))
        identifier, flags = r.word(), struct.unpack("<I", r.take(4))[0]
        cls, text = r.resource_name(control=True), r.resource_name()
        extra = r.take(r.byte())
        result["controls"].append({"id": identifier, "class": cls, "text": text,
                                   "bounds": box, "style": f"0x{flags:08x}", "extra_bytes": len(extra)})
    if any(data[r.pos:]):
        raise FormatError("Unparsed nonzero dialog resource data")
    return result


def _menu(data: bytes) -> dict:
    r = Reader(data)
    version, skip = r.word(), r.word()
    if version:
        raise FormatError("Unsupported NE menu template version")
    r.take(skip)
    count = 0

    def items(depth=0):
        nonlocal count
        if depth > 32:
            raise FormatError("NE menu nesting exceeds the limit")
        result = []
        while True:
            flags = r.word()
            identifier = None if flags & 0x10 else r.word()
            text = r.cstring()
            item = {"text": text, "id": identifier, "flags": flags}
            count += 1
            if count > 4096:
                raise FormatError("NE menu has too many items")
            if flags & 0x10:
                item["items"] = items(depth + 1)
            result.append(item)
            if flags & 0x80:
                return result

    tree = items()
    if any(data[r.pos:]):
        raise FormatError("Unparsed nonzero menu resource data")
    return {"items": tree, "item_count": count}


def _version(data: bytes) -> dict:
    def node(offset, end, depth=0):
        if depth > 16:
            raise FormatError("NE version nesting exceeds the limit")
        r = Reader(data, offset, end)
        size, value_size = r.word(), r.word()
        if size < 5 or offset + size > end:
            raise FormatError("Invalid NE version node length")
        key = r.cstring()
        r.pos = (r.pos + 3) & ~3
        value = r.take(value_size)
        if r.pos > offset + size:
            raise FormatError("NE version value exceeds its node")
        children = []
        child = (r.pos + 3) & ~3
        while child + 4 <= offset + size and any(data[child:offset + size]):
            sub = node(child, offset + size, depth + 1)
            children.append(sub)
            child = (child + sub["size"] + 3) & ~3
        result = {"key": key, "size": size, "children": children}
        if key == "VS_VERSION_INFO":
            if len(value) != 52 or struct.unpack_from("<I", value)[0] != 0xFEEF04BD:
                raise FormatError("Invalid VS_FIXEDFILEINFO")
            words = struct.unpack("<13I", value)
            result["file_version"] = [words[2] >> 16, words[2] & 65535, words[3] >> 16, words[3] & 65535]
            result["product_version"] = [words[4] >> 16, words[4] & 65535, words[5] >> 16, words[5] & 65535]
        elif key == "Translation":
            result["value_hex"] = value.hex()
        elif value:
            result["value"] = value.rstrip(b"\0").decode("cp1252", "replace")
        return result

    return node(0, len(data))


def inspect_ne(path: str | Path, extract: str | Path | None = None) -> dict:
    source = Path(path)
    data = source.read_bytes()
    if len(data) > 64 * 1024 * 1024 or len(data) < 64 or data[:2] != b"MZ":
        raise FormatError("Not a bounded DOS/NE executable")
    base = struct.unpack_from("<I", data, 0x3C)[0]
    header = Reader(data, base).take(64)
    if header[:2] != b"NE":
        raise FormatError("Not a Windows 16-bit NE executable")
    word = lambda n: struct.unpack_from("<H", header, n)[0]
    dword = lambda n: struct.unpack_from("<I", header, n)[0]
    segment_count, module_count, alignment = word(28), word(30), word(50)
    if segment_count > 4096 or module_count > 4096 or alignment > 16:
        raise FormatError("NE tables exceed supported limits")
    windows = word(62)
    result = {"file_name": source.name, "size_bytes": len(data),
              "sha256": hashlib.sha256(data).hexdigest(), "format": "MZ / NE",
              "ne_offset": base, "target_os": header[54],
              "expected_windows_version": f"{windows >> 8}.{windows & 255:02d}",
              "linker_version": f"{header[2]}.{header[3]:02d}", "flags": f"0x{word(12):04x}",
              "entry_point": {"segment": dword(20) >> 16, "offset": dword(20) & 65535},
              "auto_data_segment": word(14), "heap_bytes": word(16), "stack_bytes": word(18),
              "imports": [], "segments": [], "exports": [], "resources": [], "resource_errors": []}
    import_start = base + word(42)

    def imported_string(offset):
        r = Reader(data, import_start + offset)
        return r.take(r.byte()).decode("cp1252", "replace")

    module_reader = Reader(data, base + word(40))
    result["imports"] = [imported_string(module_reader.word()) for _ in range(module_count)]

    def names(offset, end):
        r = Reader(data, offset, end)
        values = []
        while r.pos < r.end:
            size = r.byte()
            if not size:
                break
            values.append({"name": r.take(size).decode("cp1252", "replace"), "ordinal": r.word()})
        return values

    result["exports"] = names(base + word(38), base + word(40))
    result["nonresident_names"] = names(dword(44), dword(44) + word(32))
    destination = Path(extract) if extract else None
    if destination:
        destination.mkdir(parents=True, exist_ok=True)
    segment_reader = Reader(data, base + word(34))
    for identifier in range(1, segment_count + 1):
        sector, length, flags, minimum = struct.unpack("<4H", segment_reader.take(8))
        offset, size = sector << alignment, length or 65536
        content = Reader(data, offset).take(size) if sector else b""
        relocations = []
        if sector and flags & 0x100:
            r = Reader(data, offset + size)
            count = r.word()
            for _ in range(count):
                kind, options, at, first, second = struct.unpack("<BBHHH", r.take(8))
                relocation = {"source_type": kind, "flags": options, "source_offset": at}
                target_kind = options & 3
                if target_kind in (1, 2):
                    if not 1 <= first <= len(result["imports"]):
                        raise FormatError("Invalid NE import module reference")
                    relocation["module"] = result["imports"][first - 1]
                    relocation["ordinal" if target_kind == 1 else "name"] = second if target_kind == 1 else imported_string(second)
                elif target_kind == 0:
                    relocation["target_segment"], relocation["target_offset"] = first, second
                else:
                    relocation["os_fixup"] = [first, second]
                if at >= size:
                    raise FormatError("NE relocation points outside its segment")
                relocations.append(relocation)
        entry = {"id": identifier, "file_offset": offset, "size": size, "flags": f"0x{flags:04x}",
                 "kind": "data" if flags & 1 else "code", "minimum_allocation": minimum or 65536,
                 "relocations": relocations}
        result["segments"].append(entry)
        if destination:
            (destination / f"segment_{identifier}.bin").write_bytes(content)
    resource_start = base + word(36)
    resource_end = base + word(38)
    r = Reader(data, resource_start, resource_end)
    shift = r.word()
    if shift > 16:
        raise FormatError("Unsupported NE resource alignment")

    def resource_id(value):
        if value & 0x8000:
            return value & 0x7FFF
        sr = Reader(data, resource_start + value, resource_end)
        return sr.take(sr.byte()).decode("cp1252", "replace")

    while True:
        type_word = r.word()
        if not type_word:
            break
        count = r.word()
        r.take(4)  # reserved
        if len(result["resources"]) + count > 4096:
            raise FormatError("Too many NE resources")
        type_id = resource_id(type_word)
        for _ in range(count):
            sector, length, flags, identifier, handle, usage = struct.unpack("<6H", r.take(12))
            offset, size = sector << shift, length << shift
            raw = Reader(data, offset).take(size)
            item = {"type": type_id, "type_name": RESOURCE_TYPES.get(type_id, str(type_id)),
                    "id": resource_id(identifier), "file_offset": offset, "size": size,
                    "sha256": hashlib.sha256(raw).hexdigest()}
            try:
                if type_id == 5:
                    item["dialog"] = _dialog(raw)
                elif type_id == 4:
                    item["menu"] = _menu(raw)
                elif type_id == 16:
                    item["version"] = _version(raw)
                elif type_id == 6:
                    sr = Reader(raw)
                    strings = {}
                    for i in range(16):
                        value = sr.take(sr.byte()).decode("cp1252", "replace")
                        if value:
                            strings[str((item["id"] - 1) * 16 + i)] = value
                    if any(raw[sr.pos:]):
                        raise FormatError("Unparsed nonzero string-table resource data")
                    item["strings"] = strings
                elif type_id == 9:
                    ar = Reader(raw)
                    items = []
                    while True:
                        flags, key, command = ar.byte(), ar.word(), ar.word()
                        items.append({"flags": flags, "key": key, "command": command})
                        if flags & 0x80:
                            break
                    if any(raw[ar.pos:]):
                        raise FormatError("Unparsed nonzero accelerator resource data")
                    item["accelerators"] = items
            except (FormatError, struct.error) as exc:
                item["decode_error"] = str(exc)
                result["resource_errors"].append({"type": type_id, "id": item["id"], "error": str(exc)})
            result["resources"].append(item)
            if destination:
                # Numeric names keep untrusted resource strings out of file paths.
                (destination / f"resource_{len(result['resources']):03d}.bin").write_bytes(raw)
    result["resource_counts"] = dict(Counter(item["type_name"] for item in result["resources"]))
    imported_functions = {}
    for segment in result["segments"]:
        for relocation in segment["relocations"]:
            if "module" not in relocation:
                continue
            function = {key: relocation[key] for key in ("module", "ordinal", "name") if key in relocation}
            imported_functions[(function["module"], str(function.get("ordinal", function.get("name"))))] = function
    result["imported_functions"] = [imported_functions[key] for key in sorted(imported_functions)]
    result["application_class_names"] = [name for name in ("CMainFrame", "CCmDoc", "CCmView", "CAttBar", "CTextObj", "CGraphic", "CBitmapObj", "CDlist", "CDListHead") if name.encode() + b"\0" in data]
    strings = [match.group().decode("cp1252", "replace") for match in re.finditer(rb"[\x20-\x7e]{5,}", data)]
    result["dynamic_library_mentions"] = sorted({s for s in strings if re.search(r"\.(VBX|DLL)(?:[;\s]|$)", s, re.I)})
    return result
