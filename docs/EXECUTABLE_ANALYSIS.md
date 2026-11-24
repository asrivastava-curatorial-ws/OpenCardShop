# Original CARDSHOP.EXE inspection

Inspection date: 12 October 2026. This file was supplied separately after the native Linux editor had been built and tested.

## Binary identity

| Field | Observed value |
| --- | --- |
| Uploaded filename | CARDSHOP.EXE |
| File size | 247,472 bytes |
| SHA-256 | 2570a011ab396be084927c71e67d49bb8b38515e0ed9466fcbca5b81945205e0 |
| Container | DOS MZ stub followed by a Windows NE executable |
| NE header position | Byte 128 |
| Target OS field | 2: Windows |
| Expected platform field | 3.10, the Windows 3.1 platform encoding |
| Linker version bytes | 5.50 |
| Segments | 7: five code segments and two data segments |
| Imported modules | 8 |
| Relocation records | 768 |
| Distinct imported functions | 290 |

The binary was preserved byte-for-byte at `assets/original/CARDSHOP.EXE`. The Linux editor does not load it. The inspection tool reads its tables and resources without executing any instructions.

## Version identifiers

The original About dialog (resource 100) displays **CardShop Plus! Version 1.5**, with copyright identifying High Desert Software, Inc. and publication by The Software Toolworks, Inc.

The executable's version resource is different: FileVersion and ProductVersion strings are **1.2.001**, the fixed version fields are 1.2.0.1, and OriginalFilename is **CM.EXE**. Its description is **CM MFC Application**. Both sets of identifiers are retained in the inventory. The About caption is the user-visible branding; the differing metadata is not evidence that the supplied file is corrupt. These values do not establish a build date or whether every dialog was used in this particular distribution.

## Dependencies and drawing evidence

The imported modules are LZEXPAND, KERNEL, GDI, USER, KEYBOARD, WIN87EM, COMMDLG, and SHELL. The import relocation records include the LZEXPAND functions LZINIT, LZREAD, LZSEEK, and LZCLOSE. This is consistent with the standard Windows compressed-file handling already identified in the CMF assets.

GDI import ordinal 123 is PlayMetaFile. Relocation chains place its call-site operands in code segment 1 at offset 0x0E3C and code segment 4 at offset 0xA716. Other imported GDI functions include GetMetaFileBits, SetMetaFileBits, TextOut, ExtTextOut, CreateFontIndirect, StretchDIBits, and CreateDIBitmap. This corroborates the vector/bitmap/text drawing architecture; an import alone does not prove a specific application path was executed.

Original dialog resources 101, 102, and 105 refer to **THREED.VBX** and its SSCommand/SSPanel controls through VBControl entries. This is a dynamic UI dependency that does not appear in the eight-module import table. THREED.VBX is already present in the supplied content archive. The native Tk UI replaces those legacy controls and needs no VBX runtime.

## Recovered resources

All 61 NE resources were located within the file bounds. The menu, dialog, string, accelerator, and version decoders reported no unparsed nonzero payload or decoding error.

| Resource kind | Count |
| --- | --- |
| Dialogs | 19 |
| String-table blocks | 19, containing 119 nonempty strings |
| Main menu | 1, containing 45 entries including popup headings and separators |
| Accelerator table | 1, containing 22 shortcuts |
| Version resource | 1 |
| Bitmap | 1 |
| Icon / icon group | 1 / 1 |
| Cursors / cursor groups | 7 / 7 |
| Dialog-initialisation resources | 3 |

Named resource identifiers and numeric identifiers are kept distinct. Raw offsets, allocated lengths, hashes, decoded control geometry, text, menus, and import records are stored in `docs/executable_inventory.json`. Binary resources can be extracted reproducibly rather than copied into the delivery as redundant files.

## What this confirms for the Linux editor

| Original evidence | Corresponding native behavior / limit |
| --- | --- |
| New Card submenu: Side Fold, Top Fold, Full Size | The same three document fold types are available |
| Front, Inside, and Back commands | Three editing views, with Inside spanning two panels |
| Preview dialogs 194 and 196 each label a first and second fold | Consistent with the two-fold, quarter-sheet printing method documented in the original help |
| Receiver and Sender controls; `<receiver>` / `<sender>` string resources | The same name-substitution tokens are supported |
| Text alignment commands; import description names BMP and WMF | Native text alignment and artwork import cover these concepts |
| CTextObj and CGraphic class names | Match the serialised classes recovered from all supplied card files |
| CBitmapObj class name | An additional original bitmap-object class exists; no supplied CMK uses it, and its legacy serialised layout is not claimed as supported |
| Save As dialog 205 includes Full Save | Confirms the embedded legacy-save option described in the help; native portable saving uses `.occard` |
| Margins dialog 199 has separate left/right/top/bottom fields | Version 1.1.0 adds four minimum margins, preserving physical-sheet fold centres |
| Print dialog 198 includes a test page and paper-order form | Version 1.1.0 adds a marked printer/folding test sheet; the obsolete paper order and registration forms are not part of the native editor |

The preview resources strengthen the folding explanation, but their presence is not a runtime comparison of the print compositor. Original fold imposition, font placement, and exact appearance should ultimately be compared with output from a running original installation before claiming visual equivalence.

The EXE does not contain source code that can simply be recompiled for Linux. It supplies machine code, tables, and resources that make further reverse engineering possible. No unsupported Full Save or CBitmapObj reader was added solely on the basis of a class name or checkbox.

## Reproduce the inspection

From the program folder:

```bash
python3 tools/inspect_ne.py --report /tmp/cardshop-executable.json
python3 tools/inspect_ne.py --extract /tmp/cardshop-original-resources
python3 -m unittest tests.test_ne -v
```

The inspector uses Python's standard library and the project's bounded-format error type. It does not need Wine, a Windows installation, or a display. Its extract option writes numbered files, avoiding untrusted resource names as filesystem paths.

After this static inspection, the supplied executable was launched in an isolated emulated Linux guest using classic 32-bit Wine 9. The original editor opened and a supplied card was loaded. The observations and remaining limits are recorded in [RUNTIME_COMPARISON.md](RUNTIME_COMPARISON.md). The working native Linux program remains the normal launch path (`bash run.sh`).

The NE layout and Win16 template interpretation were checked against the Wine project's [header definitions](https://github.com/wine-mirror/wine/blob/master/include/winnt.h), [Win16 dialog reader](https://github.com/wine-mirror/wine/blob/master/dlls/user.exe16/dialog.c), [NE relocation loader](https://github.com/wine-mirror/wine/blob/master/dlls/krnl386.exe16/ne_segment.c), and [GDI ordinal definitions](https://github.com/wine-mirror/wine/blob/master/dlls/gdi.exe16/gdi.exe16.spec). Version and CardShop behavior claims above come from the supplied binary, not from those general platform references.
