# OpenCardShop recovery and validation report

Initial editor validation: 4 October 2026. Executable inspection update: 12 October 2026. Printing and runtime update: 12 October 2026. Application version: 1.1.0.

## What was recovered

The initial ZIP contained the content and supporting files. The original executable was supplied separately on 12 October 2026 and is now preserved with them. Its NE structures and resources were inspected, then the executable was launched in an isolated Linux guest with 32-bit Wine 9. The delivery remains a native replacement editor, with documented readers for the supplied formats; the original application source is not available. The original editor opened and a supplied birthday card was loaded. See `RUNTIME_COMPARISON.md` for the observed controls and the limits of the compatibility run.

| Content | Result |
| --- | --- |
| Original files preserved | 2,041 archive files plus the separately supplied EXE, all unchanged |
| Occasions | 28 |
| Legacy card files | 315 parse completely, with no trailing bytes |
| Designed cards | 231: 146 side folds, 76 top folds, 9 full-page designs |
| Blank templates | 84; represented by the editor's three New commands |
| Serialised card objects | 1,599 |
| Unique artwork entries | 616, from 617 files with one identical duplicate |
| Valid vector sources | 611; preserved as recovered SVG and prepared PNG |
| Damaged vectors with usable bitmap previews | 3 |
| Damaged artwork without usable previews | 2 |
| Original font files / families | 60 / 55 |
| Recovered message entries | 1,080 |

## Source damage

These failures are in the supplied files, before the new editor renders them:

| Source | Failure | Result in the editor |
| --- | --- | --- |
| BONV31.CMF | Invalid WMF record at byte 10,928 | Original 165 × 112 bitmap preview |
| BORDER2.CMF | Invalid WMF record at byte 6,798 | Original 84 × 112 bitmap preview |
| REL86.CMF | Invalid WMF record at byte 11,902 | Original 69 × 112 bitmap preview |
| BUS72.CMF | Truncated SZDD back-reference | Explicitly unavailable |
| HAL32.CMF | Truncated SZDD literal | Explicitly unavailable |

None of the 315 supplied card files references these five artwork names. All 231 designed cards therefore have their referenced artwork available. Preview fallbacks retain their original low resolution and cannot recover the missing vector detail. Damaged source bytes are preserved for future investigation.

The per-file machine-readable record is `assets/rendered/asset_report.json`. It includes source hashes, dimensions, conversion outcomes, and all parsed card counts. File integrity for the CardShop Plus content is recorded in the asset pack's `assets/ASSET_PACK.sha256`.

## Automated checks

The final 1.1.0 validation passed all **43 automated tests**: 15 core checks, 6 executable-inspection checks, 11 physical-paper/printing checks, and 11 desktop checks. No tests were skipped in this run. Desktop checks ran against native Linux Tk 8.6.14 using an Xvfb display, with no callback tracebacks or dangling Tk callback errors. Python was 3.12 and Pillow was 12.3.0; the original cache preparation used Inkscape 1.2.2.

The executable checks verify the EXE identity, runtime imports, complete resource decoding, both fold-guide dialogs, Full Save and VBX controls, conflicting version metadata, byte-exact resource extraction, and rejection of truncated/corrupt input.

Core checks cover the entire CMK corpus, all 611 validated WMFs, original panel counts and styles, both CMK signature variants, damaged and oversized SZDD streams, explicit source fallbacks, an independent WMF playback comparison, message parsing and name substitution, and the native portable save format. Portable save/reopen checks compare actual rendered pixels with an empty external content store. Image resources, regular/bold/italic font variants, and imported images survive the round trip. An induced resource failure leaves a previous saved card intact.

Printing checks verify the orientation of every physical face after two independently modelled folds, side/top quadrant positions, one-page A4/Letter/Legal geometry, full-page front output, unequal-margin centring, test-sheet face labels, the 100 mm ruler, preview-only guides, validation of invalid margins, saved print preferences, and backward compatibility with older `.occard` files. GUI checks exercise real canvas events, movement, undo/redo, text/name changes, copy/paste, deletion, save/reopen, library searches, small-window controls, and the print dialog. New checks export an actual Legal test PDF, ensure normal PDF exports have no printed guides, and submit a PDF through a simulated CUPS queue with the selected media, copies, one-sided output, and no extra scaling.

The three practice PDFs in `examples/print-tests/` were exported through the actual command-line application and reopened with PyMuPDF. Each contains one page with the selected paper orientation; page dimensions and file sizes are in `docs/print_sample_check.json`. All three were rendered to images and inspected. A top-fold label/ruler overlap was corrected before the final render. Number labels were moved inside the printable margins. A4 page dimensions differ from the nominal millimetre size by less than 0.05 mm due to raster pixel rounding at 300 dpi.

A separate corpus smoke check rendered 693 editing views from all 231 designs at a width of 360 pixels with no content errors. Full-page designs' normally hidden Inside and Back views were also traversed in this check. Results are in `docs/corpus_render_check.json`. Higher-resolution renders were checked for the side-fold birthday, top-fold Christmas, and full-page certificate examples. Screenshots in `docs/screenshots/` show the actual running application, including the 1080 × 720 client layout and the updated card and practice-sheet previews.

Command-line exports were checked independently of the GUI. This path does not import Tk and can render saved `.occard` and original `.CMK` files without a desktop display. The final ZIP was checked for archive integrity. All 2,042 original files, including the executable, were compared byte-for-byte with the previously delivered archive and remain unchanged (`docs/print_update_integrity_check.json`). Additional command-line checks cover Legal top-fold PDF, Letter test PNG, four-margin Legal card PDF, and rejection of a NaN margin without creating output (`docs/cli_print_check.json`).

## Practical limits

- **Original fidelity:** the original editor was launched through 32-bit Wine in an emulated Linux guest, and a supplied design was opened. This is a limited compatibility comparison, not a reference Windows 3.1 installation. GDI font cell height, line wrapping, antialiasing, and synthetic styles are approximated with FreeType/Pillow. The provided previews are low-resolution references; exact pixel equivalence to Windows 3.x is not claimed.
- **CMK coverage:** only the supplied class schemas and header variants are verified. The legacy embedded Full Save variant described in the help was not supplied and is not claimed as supported. Native saving uses `.occard`, not legacy CMK.
- **WMF coverage:** the independent Python fallback implements the observed subset and rejects unsupported commands. Rotated text in ANY94.CMF requires the Inkscape preparation path for vector recovery; the shipped cache includes it. Importing arbitrary WMFs is not guaranteed.
- **Print fidelity:** PDFs are single-page raster output at 300 dpi by default, with A4/Letter/Legal paper geometry, four minimum margins, and preserved original proportions. SVG artwork is retained separately. Duplex, booklet, and original printer-driver emulation are not implemented.
- **Physical printers:** no job was sent to a real printer during validation. CUPS command options and PDF creation were checked with a simulated queue; printer-specific margins, drivers, paper handling, and real scale remain untested.
- **Distribution coverage:** the source and dependencies use native Linux components; the application was exercised in this Linux workspace with Ubuntu-provided Tk 8.6 libraries. Separate Fedora, Arch, Wayland-only, ARM, and older-distribution installations were not run. Their dependency commands are documented, not claimed as an installation test matrix.
- **Original support components:** the EXE, VBX, DRV, INF, and legacy help binaries remain preserved assets and are not executed by the native Linux editor. The original text help and the new user guide are readable in the package.

## Reproducing the checks

From the extracted program folder:

```bash
python3 -m unittest tests.test_core -v
python3 -m unittest tests.test_ne -v
python3 -m unittest tests.test_printing -v
python3 -m unittest tests.test_gui -v
sha256sum -c --quiet assets/ASSET_PACK.sha256   # with the asset pack installed
```

GUI tests require a desktop display. If PyMuPDF is unavailable, the optional PDF page-inspection assertion in the core suite is skipped; export still uses Pillow. Install `PyMuPDF` in a development virtual environment to reproduce that inspection. Neither PyMuPDF nor Inkscape is required for ordinary editing or printing.
