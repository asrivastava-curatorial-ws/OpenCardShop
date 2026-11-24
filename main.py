#!/usr/bin/env python3
"""GUI entry point and offline command-line renderer."""
from pathlib import Path
import argparse
import sys


def main():
    _prepare_windows()
    parser = argparse.ArgumentParser(description="OpenCardShop: native, offline greeting-card editor")
    parser.add_argument("file", nargs="?", type=Path, help="Open an .occard or original .CMK file")
    parser.add_argument("--assets", type=Path, help="Use a different extracted CardShop content folder")
    parser.add_argument("--export", type=Path, help="Export FILE to PDF or PNG without opening a GUI")
    parser.add_argument("--side", choices=("front", "inside", "back"), default="front")
    parser.add_argument("--paper", choices=("A4", "Letter", "Legal"), help="Paper size; defaults to the saved card's setting")
    parser.add_argument("--dpi", type=int, default=300)
    margins = parser.add_mutually_exclusive_group()
    margins.add_argument("--margin", type=float, help="Use one margin in mm on all four edges")
    margins.add_argument("--margins", type=float, nargs=4, metavar=("LEFT", "RIGHT", "TOP", "BOTTOM"), help="Four minimum margins in mm")
    parser.add_argument("--guides", action="store_true")
    parser.add_argument("--layout", choices=("quarter", "half"),
                        help="quarter: one-sided, folded twice; half: two-sided (flip on short edge), folded once. "
                             "Defaults to the saved card's setting")
    parser.add_argument("--rotate-side-2", action="store_true", help="Half layout: turn side 2 upside down")
    parser.add_argument("--test-page", action="store_true", help="Export a marked folding/printer test instead of the card artwork")
    parser.add_argument("--fold", choices=("side", "top", "full"), help="Fold type for a test page when no card file is given")
    from opencardshop import __version__
    parser.add_argument("--version", action="version", version="OpenCardShop " + __version__)
    args = parser.parse_args()
    try:
        from opencardshop.assets import AssetStore
        from opencardshop.formats import read_cmk
        from opencardshop.model import CardDocument, load_document
        from opencardshop.render import export_pdf, export_panel
        from opencardshop.printing import validate_margins
        if args.export:
            if not args.file and not args.test_page:
                parser.error("--export requires a card file, or use --test-page")
            if args.file and args.fold:
                parser.error("--fold applies to a test page without a card file")
            if not 36 <= args.dpi <= 600:
                parser.error("--dpi must be between 36 and 600")
            from opencardshop.paths import default_library
            library, rendered = default_library() if args.assets is None else (args.assets, None)
            store = AssetStore(library, rendered)
            doc = (CardDocument.from_legacy(read_cmk(args.file), args.file.stem)
                   if args.file and args.file.suffix.casefold() == ".cmk" else
                   load_document(args.file) if args.file else CardDocument(fold=args.fold or "side"))
            paper = args.paper or doc.paper
            chosen_margins = validate_margins(args.margins if args.margins is not None else
                                              (args.margin,) * 4 if args.margin is not None else doc.print_margins)
            layout = args.layout or doc.print_layout
            if args.export.suffix.casefold() == ".pdf":
                export_pdf(doc, store, args.export, paper, args.dpi, guides=args.guides,
                           margins=chosen_margins, test_page=args.test_page, layout=layout,
                           rotate_second=args.rotate_side_2)
            elif args.export.suffix.casefold() == ".png":
                if args.test_page and layout == "half":
                    from opencardshop.render import half_fold_pages, side_by_side
                    pages = half_fold_pages(doc, store, paper, args.dpi, chosen_margins, test_page=True,
                                            rotate_second=args.rotate_side_2)
                    side_by_side(pages, gap=round(args.dpi / 4)).save(args.export, dpi=(args.dpi, args.dpi))
                elif args.test_page:
                    from opencardshop.render import print_sheet
                    print_sheet(doc, store, paper, args.dpi, margins=chosen_margins, test_page=True).save(args.export, dpi=(args.dpi, args.dpi))
                else:
                    export_panel(doc, args.side, store, args.export, args.dpi)
            else:
                parser.error("--export target must end in .pdf or .png")
            print("Exported", args.export)
            return 0
        import tkinter as tk
        from opencardshop.app import CardShopApp
        root = tk.Tk(className="OpenCardShop")
        CardShopApp(root, args.assets, args.file)
        root.mainloop()
        return 0
    except ImportError as exc:
        return _startup_error(f"Missing Python dependency: {exc}\n"
                              "On Ubuntu/Mint/Debian: sudo apt install python3 python3-tk python3-pil python3-pil.imagetk")
    except Exception as exc:
        return _startup_error(f"OpenCardShop could not start: {exc}\n"
                              "Run the graphical editor from a desktop session.")


def _prepare_windows():
    """Point Tcl/Tk at their scripts in the Windows installer's runtime (runtime\\tcl), or in
    a conda-style Library folder, and let extension modules find their DLLs."""
    if not sys.platform.startswith("win"):
        return
    import os
    base = Path(sys.base_prefix)
    for folder in (base / "DLLs", base / "Library" / "bin"):
        if folder.is_dir():
            os.add_dll_directory(str(folder))
    for variable, name, marker in (("TCL_LIBRARY", "tcl8.6", "init.tcl"), ("TK_LIBRARY", "tk8.6", "tk.tcl")):
        for parent in (base / "tcl", base / "Library" / "lib"):
            if variable not in os.environ and (parent / name / marker).is_file():
                os.environ[variable] = str(parent / name)


def _startup_error(text):
    """Report on stderr, and in a dialog when there is no console (Windows pythonw)."""
    print(text, file=sys.stderr)
    if sys.platform.startswith("win") and sys.stderr is None:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "OpenCardShop", 0x10)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
