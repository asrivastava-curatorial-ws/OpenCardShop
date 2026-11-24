# CardShop Plus format recovery

These notes describe the supplied `Archive.zip`, not every version of CardShop Plus. The new program was reconstructed from content, the supplied original help text, the supplied OpenCardShop documentation, and inspection of the actual byte streams. The original executable was supplied separately on 12 October 2026 and is now included. Its structures and resources were first inspected without execution (`EXECUTABLE_ANALYSIS.md` and `executable_inventory.json`), then it was launched in a separate compatibility test environment. See `RUNTIME_COMPARISON.md` for the observations and limits.

## Archive inventory

The ZIP contains 2,071 entries, including directories, and 2,041 files. Uncompressed content totals 18,521,574 bytes. The files include 617 `.CMF`, 315 `.CMK`, 642 `.BMP`, 314 `.PRE`, 60 `.TTF`, 28 message `.DAT`, and support/help/driver files. `SECDY31.CMF` appears twice with identical bytes, leaving 616 unique artwork basenames.

`SETUP.INF` references the application executable, which was absent from the initial archive. The separately supplied 247,472-byte `CARDSHOP.EXE` now provides the original NE binary for further investigation. Its import table includes LZEXPAND and GDI; its class names include CTextObj, CGraphic, and CBitmapObj. The first two match the classes recovered from the supplied card corpus. There is still no original application source code, and the Linux implementation remains a reconstructed editor.

## CMF: SZDD-compressed Windows metafiles

The supplied reconstruction PDF describes proprietary polygon blocks. Inspection instead identifies a standard SZDD wrapper around an Aldus placeable Windows Metafile.

The 14-byte SZDD header is the eight-byte magic `53 5A 44 44 88 F0 27 33`, method byte `41`, a missing-filename-character byte, and a little-endian 32-bit uncompressed size. The LZSS stream uses a 4,096-byte dictionary initialised to spaces, starts writing at offset 4,080, and consumes control bits least significant first. A set bit means a literal. A clear bit means a two-byte dictionary reference: a 12-bit position and a length of 3–18 bytes. Back-references can overlap the dictionary as it is updated. The reader enforces an expansion-size limit and reports truncation.

The decompressed stream begins with the placeable key `D7 CD C6 9A` and a 22-byte placeable header. The regular 18-byte METAHEADER follows it. Record data starts at byte 40.

| Record field | Width | Meaning |
| --- | --- | --- |
| Size | DWORD | Total record length in 16-bit words, including the record header |
| Function | WORD | WMF/GDI opcode |
| Parameters | Variable | Begin six bytes after the record start; follow each opcode's parameter order |

The placeable bounds and units-per-inch describe the image's physical scale. Window origin and extent records define the GDI coordinate mapping; negative Y extents in this corpus must be honoured. Simply scaling polygons against the placeable bounds produces incorrect vertical orientation.

Key opcodes observed in this corpus include:

| Opcode | GDI operation |
| --- | --- |
| `0x020B` | SetWindowOrg |
| `0x020C` | SetWindowExt |
| `0x02FA` | CreatePenIndirect |
| `0x02FC` | CreateBrushIndirect |
| `0x012D` | SelectObject |
| `0x01F0` | DeleteObject |
| `0x0324` | Polygon |
| `0x0325` | Polyline |
| `0x0538` | PolyPolygon |

Pen/brush/font objects occupy reusable slots in a GDI object table. SelectObject chooses a handle, not a brush-creation record. DeleteObject releases the slot. Fill mode, selected pen/brush, and coordinate state affect later records. Polygon holes require the appropriate even-odd or winding rule.

`formats.py` validates placeable checksums, declared stream sizes, record boundaries, and EOF. `wmf.py` implements the observed drawing subset independently with Pillow. Inkscape was used to replay the validated vector streams into the shipped PNG and SVG cache. The GUI reads prepared PNGs without invoking external software. The SVGs preserve recovered vector paths; the GUI's print compositor currently rasterises the completed page.

The Python fallback is deliberately limited: it rejects unsupported drawing commands, including rotated WMF text. `ANY94.CMF` contains that case, and its shipped Inkscape-rendered cache is usable. Rebuilding solely with Python can instead use its original bitmap preview. General-purpose WMF playback and arbitrary Windows GDI code are outside this implementation.

## CMK: MFC CArchive objects

The supplied cards are counted panels containing MFC serialised objects. Searching for class-name strings or treating every high-bit tag as the same class misreads these files. A bounded sequential reader tracks a shared class/object identifier space across all three panels.

All integer fields described here are little-endian. A CString begins with an unsigned-byte length. `FF` means an extended WORD length; `FFFF` in that extended field means a DWORD length. The supplied strings are decoded as Windows CP1252. Stored DOS/Windows artwork paths are reduced to case-insensitive basenames rather than followed as filesystem paths.

| Field | Supplied layout |
| --- | --- |
| Signature | CString: `Card Maker copyright (c) 1993` or that string followed by ` V1.20` |
| V1.20 extension | Extra WORD immediately after the signature; zero in all 20 supplied V1.20 files |
| Fold | WORD: 0 top, 1 side, 2 full |
| Front | WORD object count, followed by that many CArchive objects |
| Inside | WORD object count, followed by that many CArchive objects |
| Back | WORD object count, followed by that many CArchive objects |

There are 295 files with the original signature and 20 with the V1.20 signature. All 315 parse exactly to EOF, producing 1,599 objects. Of the 315 cards, 84 are empty templates: one blank for each fold in each of the 28 occasions. The remaining 231 designs include 146 side folds, 76 top folds, and 9 full-page designs.

The supported object tags are:

- `FFFF`: new class, followed by schema WORD, class-name-length WORD, and ASCII class name. The class receives the next global identifier; a newly constructed object receives the following identifier.
- `8000 | class-id`: reuse a previously registered class and construct a new object with the next identifier.
- A low-bit object identifier: reference an already stored object.

The supplied schemas are zero, and the classes are `CGraphic` and `CTextObj`. The reader rejects unknown classes, unsupported schemas, unverified nonzero V1.20 header flags, and trailing bytes. In particular, the original help mentions an embedded-graphics Full Save mode; no such file was supplied and its layout is not claimed as supported.

Both object types begin with four signed 16-bit bounds: left, top, right, bottom.

**CGraphic** then contains a CString artwork path.

**CTextObj** then contains an alignment WORD (0 left, 1 centre, 2 right), a four-byte COLORREF (the first three bytes are red, green, blue), a CString message, a 26-byte font descriptor, and a CString font family. Descriptor fields observed are:

| Offset | Field |
| --- | --- |
| 0 | Signed LONG font height |
| 4 | Signed LONG width |
| 8 | Signed LONG weight, commonly 400 or 700 |
| 12 / 14 / 16 | WORD italic / underline / strike flags |
| 18–25 | Four retained WORD precision, quality, and pitch-related values; their exact semantics have not been independently verified |

Coordinates use 1,000 logical units per inch. Imported positive font heights represent a character cell rather than simply a FreeType point size; the new compositor adjusts them using ascent and descent. Exact line breaking and synthetic styling have not been compared with a running original renderer.

| Fold / view | Logical dimensions |
| --- | --- |
| Side front or back | 4,250 × 5,500 |
| Side inside | 8,500 × 5,500 |
| Top front or back | 5,500 × 4,250 |
| Top inside | 5,500 × 8,500 |
| Full page | 8,500 × 11,000 |

## Other recovered content

`CARDSHOP.INI` supplies the occasion labels. Each occasion's `PREBUILT.INI` orders cards, `ART.INI` chooses artwork, and `MESSAGE.DAT` contains CP1252 messages separated by front `]`, inside `[`, back `}`, and comment `|` markers. There are 1,080 recovered message entries. `.PRE` and `.BMP` files provide original previews. The original 60 TrueType files are read through Pillow/FreeType and map to 55 family names.

## Native document and rendering choices

`.occard` is a versioned ZIP with `document.json`, content-hashed PNG image members, and TTF members. JSON stores each object's bounds, kind, text, style, resource references, document names, and fold. Every used font variant is embedded under a family/bold/italic key. The loader bounds entry counts, uncompressed sizes, coordinates, strings, and resource paths; it does not extract arbitrary ZIP paths onto disk.

The editor uses Tk and Pillow so it has no architecture-specific Windows dependencies. It recreates the original editing concepts and imports the supplied content; it does not emulate the original program. Card saving is atomic. PDF export composites a one-sheet fold layout into an A4, Letter, or Legal page at the requested DPI. The one-page layouts are tested by quadrant positions, independent physical fold transformations, PDF dimensions, margin centring, and diagnostic-sheet checks. Four minimum margins and numbered preview guides are described in the user guide.

## Technical references

- Microsoft, [WMF RecordType enumeration](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-wmf/77db8158-96df-4656-a36c-3066de3d5f59).
- Microsoft, [Placeable WMF header](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-wmf/828e1864-7fe7-42d8-ab0a-1de161b32f27).
- Microsoft, [TN002: Persistent object data format](https://learn.microsoft.com/en-us/cpp/mfc/tn002-persistent-object-data-format?view=msvc-170).
- libmspack, [SZDD implementation](https://github.com/kyz/libmspack/tree/master/libmspack/mspack).
- Inkscape, [command-line usage](https://wiki.inkscape.org/wiki/Using_the_Command_Line).

The CMK field layouts above are empirical observations verified against the supplied corpus; references describe the underlying standard formats rather than documenting CardShop's application-specific fields.
