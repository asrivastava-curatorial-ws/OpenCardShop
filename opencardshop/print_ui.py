"""Native print controls, a live preview, and a marked practice sheet."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from .printing import PAPERS, DEFAULT_MARGINS, DUPLEX_SIDES, validate_margins, paper_layout, fold_instructions
from .paths import cache_dir, open_path
from .render import print_sheet, export_pdf, half_fold_pages, side_by_side

LAYOUT_LABELS = {"quarter": "One-sided, fold twice (quarter-size card)", "half": "Two-sided, fold once (half-size card)"}


class PrintDialog:
    def __init__(self, app):
        self.app = app
        app._flush_names()
        self.window = window = tk.Toplevel(app.root)
        window.title("Print / folded PDF")
        window.geometry(f"{min(900, app.root.winfo_screenwidth() - 60)}x{min(850, app.root.winfo_screenheight() - 70)}")
        window.transient(app.root)
        window.grab_set()
        self.job = None
        self.closed = False
        self.paper = tk.StringVar(value=app.doc.paper)
        self.margins = {key: tk.StringVar(value=f"{value:g}") for key, value in zip(("left", "right", "top", "bottom"), app.doc.print_margins)}
        self.guides = tk.BooleanVar(value=False)
        self.mode = tk.StringVar(value="Card")
        self.layout = tk.StringVar(value=LAYOUT_LABELS.get(app.doc.print_layout, LAYOUT_LABELS["quarter"]))
        self.manual = tk.BooleanVar(value=False)
        self.rotate_second = tk.BooleanVar(value=False)
        settings = ttk.Frame(window, padding=(16, 12))
        settings.pack(fill="x")
        ttk.Label(settings, text="Paper").grid(row=0, column=0, sticky="w")
        paper = ttk.Combobox(settings, textvariable=self.paper, values=tuple(PAPERS), width=10, state="readonly")
        paper.grid(row=0, column=1, padx=(6, 20), sticky="w")
        ttk.Label(settings, text="What to print").grid(row=0, column=2, sticky="w")
        mode = ttk.Combobox(settings, textvariable=self.mode, values=("Card", "Folding and printer test"), width=24, state="readonly")
        mode.grid(row=0, column=3, columnspan=3, padx=6, sticky="w")
        ttk.Label(settings, text="Layout").grid(row=1, column=0, sticky="w", pady=(10, 0))
        layout = ttk.Combobox(settings, textvariable=self.layout, values=tuple(LAYOUT_LABELS.values()), width=38, state="readonly")
        layout.grid(row=1, column=1, columnspan=3, padx=(6, 12), sticky="w", pady=(10, 0))
        if app.doc.fold == "full":
            layout.configure(state="disabled")
        self.manual_check = ttk.Checkbutton(settings, text="No duplex unit: print side 1, then side 2", variable=self.manual)
        self.manual_check.grid(row=1, column=4, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(settings, text="Margins (mm)").grid(row=2, column=0, sticky="w", pady=(10, 0))
        edges = ttk.Frame(settings)
        edges.grid(row=2, column=1, columnspan=5, sticky="w", pady=(10, 0))
        for key, variable in self.margins.items():
            ttk.Label(edges, text=key.title()).pack(side="left", padx=(0, 4))
            ttk.Spinbox(edges, from_=0, to=25, textvariable=variable, width=5, increment=0.5).pack(side="left", padx=(0, 14))
        ttk.Button(edges, text="Defaults", command=self.defaults).pack(side="left")
        self.guides_check = ttk.Checkbutton(settings, text="Print numbered fold guides on card (practice copy)", variable=self.guides)
        self.guides_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=(9, 0))
        self.rotate_check = ttk.Checkbutton(settings, text="Turn side 2 upside down (if the test shows it inverted)", variable=self.rotate_second)
        self.rotate_check.grid(row=3, column=3, columnspan=3, sticky="w", pady=(9, 0))
        self.info = tk.StringVar()
        ttk.Label(settings, textvariable=self.info, style="Muted.TLabel", wraplength=830).grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
        self.preview = ttk.Label(window, anchor="center")
        self.preview.pack(fill="both", expand=True, padx=16)
        self.note = tk.StringVar(value=fold_instructions(app.doc.fold, self.layout_key()))
        ttk.Label(window, textvariable=self.note, style="Muted.TLabel", wraplength=840).pack(fill="x", padx=20, pady=7)
        buttons = ttk.Frame(window, padding=16)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Refresh preview", command=self.refresh).pack(side="left")
        ttk.Button(buttons, text="Print to printer", command=self.physical_print).pack(side="right", padx=6)
        ttk.Button(buttons, text="Save PDF", command=self.save_pdf, style="Accent.TButton").pack(side="right", padx=6)
        for variable in (self.paper, self.mode, self.guides, self.layout, self.rotate_second, *self.margins.values()):
            variable.trace_add("write", lambda *args: self.schedule())
        window.bind("<Destroy>", self.cleanup, add=True)
        self.preview.bind("<Configure>", lambda event: self.schedule())
        self.schedule()

    def cleanup(self, event):
        if event.widget == self.window:
            self.closed = True
            if self.job:
                self.window.after_cancel(self.job)
                self.job = None

    def schedule(self):
        if self.closed:
            return
        if self.job:
            self.window.after_cancel(self.job)
        self.job = self.window.after(100, self.refresh)

    def layout_key(self):
        if self.app.doc.fold == "full":
            return "quarter"
        return next((key for key, label in LAYOUT_LABELS.items() if label == self.layout.get()), "quarter")

    def values(self):
        margins = validate_margins(v.get() for v in self.margins.values())
        paper_layout(self.app.doc.fold, self.paper.get(), margins, self.layout_key())
        return self.paper.get(), margins, self.guides.get(), self.mode.get() != "Card"

    def export(self, path, paper, margins, guides, test):
        export_pdf(self.app.doc, self.app.store, path, paper, margins=margins, guides=guides, test_page=test,
                   layout=self.layout_key(), rotate_second=self.rotate_second.get())

    def defaults(self):
        for variable, value in zip(self.margins.values(), DEFAULT_MARGINS):
            variable.set(f"{value:g}")

    def refresh(self):
        if self.closed:
            return
        if self.job:
            self.window.after_cancel(self.job)
            self.job = None
        try:
            paper, margins, guides, test = self.values()
            half = self.layout_key() == "half"
            self.guides_check.configure(state="disabled" if test else "normal")
            self.manual_check.configure(state="normal" if half else "disabled")
            self.rotate_check.configure(state="normal" if half else "disabled")
            layout = paper_layout(self.app.doc.fold, paper, margins, self.layout_key())
            if half:
                image = side_by_side(half_fold_pages(self.app.doc, self.app.store, paper, dpi=60, margins=margins, guides=guides,
                                                     test_page=test, rotate_second=self.rotate_second.get(),
                                                     preview_guides=True), gap=30)
            else:
                image = print_sheet(self.app.doc, self.app.store, paper, dpi=80, margins=margins,
                                    guides=guides, test_page=test, preview_guides=True)
            image.thumbnail((max(150, self.preview.winfo_width() - 10), max(150, self.preview.winfo_height() - 10)), Image.Resampling.LANCZOS)
            self.preview.image = ImageTk.PhotoImage(image)
            self.preview.configure(image=self.preview.image)
            w, h = layout.finished_size_mm
            if half:
                description = (f"Finished card: {w:.1f} × {h:.1f} mm · side 1 (left preview): back and front · "
                               "side 2 (right preview): inside · one fold. Print two-sided, flip on short edge, at Actual size / 100%.")
            elif self.app.doc.fold != "full":
                description = f"Finished card: {w:.1f} × {h:.1f} mm · one printed side · two folds. Print the PDF at Actual size / 100%."
            else:
                description = f"Page: {w:.1f} × {h:.1f} mm · no folding. Print the PDF at Actual size / 100%."
            if self.app.doc.fold != "full" and (margins[0] != margins[1] or margins[2] != margins[3]):
                description += " Unequal margins reserve matching space at the opposite edge to keep the folds centred."
            self.info.set(description)
            instructions = fold_instructions(self.app.doc.fold, self.layout_key())
            if test and half:
                self.note.set(instructions + " Hold the printed test to the light: the red targets on both sides should overlap; "
                              "side 2's millimetre scale shows any shift. The ruler must measure 100 mm.")
            elif test:
                self.note.set(instructions + " Test sheets include printed fold guides. Check the UP arrows after folding; the ruler must measure 100 mm.")
            else:
                self.note.set(instructions + " Enable Print numbered fold guides to include the preview's guide lines in the PDF.")
        except (ValueError, OSError) as exc:
            self.info.set(str(exc))

    def remember(self, paper, margins):
        doc, layout = self.app.doc, self.layout_key()
        if doc.paper != paper or doc.print_margins != margins or (doc.fold != "full" and doc.print_layout != layout):
            self.app.checkpoint()
            doc.paper, doc.print_margins = paper, margins
            if doc.fold != "full":
                doc.print_layout = layout
            self.app.changed()

    def save_pdf(self):
        try:
            paper, margins, guides, test = self.values()
            initial = "folding_test.pdf" if test else self.app.doc.title + "_print.pdf"
            filename = filedialog.asksaveasfilename(parent=self.window, title="Save print-ready PDF", defaultextension=".pdf",
                                                   initialfile=initial, filetypes=[("PDF document", "*.pdf")])
            if not filename:
                return
            self.export(filename, paper, margins, guides, test)
            self.remember(paper, margins)
            kind = "two-sided PDF: " if self.layout_key() == "half" else "one-sheet PDF: "
            self.app.status_var.set("Exported " + ("folding test: " if test else kind) + Path(filename).name)
            self.window.destroy()
        except Exception as exc:
            messagebox.showerror("Cannot export PDF", str(exc), parent=self.window)

    def print_with_viewer(self):
        """Windows, or Linux without CUPS: open the print-ready PDF in the default PDF viewer."""
        try:
            paper, margins, guides, test = self.values()
            folder = cache_dir() / "print"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / ("folding-test.pdf" if test else "card-to-print.pdf")
            self.export(path, paper, margins, guides, test)
            self.remember(paper, margins)
            open_path(path)
            self.app.status_var.set("Print-ready PDF opened: " + str(path))
            sides = ("two-sided with flip on short edge (without duplex: print page 1, put the sheet back in the tray, "
                     "then print page 2)" if self.layout_key() == "half" else "one-sided")
            messagebox.showinfo("Print from your PDF viewer",
                                f"The print-ready PDF opens in your PDF viewer. Print it on {paper} paper, {sides}, "
                                "at Actual size / 100% (turn off Fit to page).", parent=self.window)
        except Exception as exc:
            messagebox.showerror("Cannot print card", str(exc), parent=self.window)

    def physical_print(self):
        if sys.platform.startswith("win") or not shutil.which("lp") or not shutil.which("lpstat"):
            self.print_with_viewer()
            return
        try:
            self.values()
            listing = subprocess.run(["lpstat", "-a"], capture_output=True, text=True, timeout=5)
            if listing.returncode:
                raise RuntimeError(listing.stderr.strip() or "Cannot query configured printers")
            printers = [line.split()[0] for line in listing.stdout.splitlines() if line.split()]
            if not printers:
                raise RuntimeError("No configured printer was found. Add a printer in Linux Settings, or use Save PDF.")
            chooser = tk.Toplevel(self.window)
            chooser.title("Select printer")
            chooser.transient(self.window)
            chooser.grab_set()
            frame = ttk.Frame(chooser, padding=18)
            frame.pack()
            printer, copies = tk.StringVar(value=printers[0]), tk.StringVar(value="1")
            ttk.Label(frame, text="Printer").pack(anchor="w")
            ttk.Combobox(frame, textvariable=printer, values=printers, state="readonly", width=35).pack(pady=8)
            ttk.Label(frame, text="Copies").pack(anchor="w")
            ttk.Spinbox(frame, from_=1, to=99, textvariable=copies, width=8).pack(anchor="w", pady=8)
            def send():
                try:
                    count = int(copies.get())
                    if not 1 <= count <= 99:
                        raise ValueError("Choose 1 to 99 copies")
                    paper, margins, guides, test = self.values()
                    half = self.layout_key() == "half"

                    def submit(path, *options):
                        job = subprocess.run(["lp", "-d", printer.get(), "-n", str(count), "-o", "media=" + paper,
                                              *options, "-o", "print-scaling=none", str(path)],
                                             capture_output=True, text=True, timeout=20)
                        if job.returncode:
                            raise RuntimeError(job.stderr.strip() or "Printer rejected the job")
                        return job.stdout.strip()

                    with tempfile.TemporaryDirectory(prefix="opencardshop-print-") as folder:
                        path = Path(folder) / "card.pdf"
                        self.export(path, paper, margins, guides, test)
                        if half and self.manual.get():
                            status = submit(path, "-o", "sides=one-sided", "-o", "page-ranges=1")
                            if not messagebox.askokcancel(
                                    "Print side 2", "Side 1 has been sent. When it has printed, put the sheet back in the tray "
                                    "so that the blank side will be printed, then press OK to print side 2.", parent=chooser):
                                self.app.status_var.set("Side 1 sent; side 2 was cancelled.")
                                chooser.destroy()
                                return
                            status = submit(path, "-o", "sides=one-sided", "-o", "page-ranges=2")
                        else:
                            status = submit(path, "-o", "sides=" + (DUPLEX_SIDES if half else "one-sided"))
                    self.remember(paper, margins)
                    self.app.status_var.set(status or "Card sent to printer.")
                    chooser.destroy()
                    self.window.destroy()
                except Exception as exc:
                    messagebox.showerror("Cannot print card", str(exc), parent=chooser)
            ttk.Button(frame, text="Print", style="Accent.TButton", command=send).pack(fill="x")
        except Exception as exc:
            messagebox.showerror("Printer unavailable", str(exc), parent=self.window)
