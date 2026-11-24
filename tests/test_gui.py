"""Meaningful desktop behavior checks. Run from an X11/XWayland desktop."""
from pathlib import Path
import os
import subprocess
import tkinter as tk
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from opencardshop.app import CardShopApp
from PIL import Image

from opencardshop.model import CardDocument, load_document


@unittest.skipUnless(os.environ.get("DISPLAY"), "A display is required for GUI tests")
@unittest.skipUnless((Path(__file__).resolve().parents[1] / "assets/original/CARDSHOP.INI").is_file(),
                     "Needs the CardShop Plus asset pack or your CD in assets/original")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.app = CardShopApp(self.root)
        self.root.update()
        self.app.render()
        self.root.update()
        self.failures = []
        self.error_patch = patch("opencardshop.app.messagebox.showerror", side_effect=lambda title, text, **kw: self.failures.append((title, text)))
        self.error_patch.start()

    def tearDown(self):
        self.error_patch.stop()
        self.root.destroy()
        self.assertEqual(self.failures, [])

    def test_name_edit_and_properties_survive_undo_redo(self):
        self.app.recipient_var.set("Aditi")
        self.app.sender_var.set("Ravi")
        self.app._flush_names()
        self.assertEqual(self.app.doc.recipient, "Aditi")
        obj = self.app.doc.panels["front"][1]
        self.app.selected = {obj.id}
        self.app.update_properties()
        self.app.text_editor.delete("1.0", "end")
        self.app.text_editor.insert("1.0", "Happy birthday, <receiver>!")
        self.app.color_var.set("#05666d")
        self.app.apply_properties()
        self.assertEqual(self.app.doc.panels["front"][1].text, "Happy birthday, <receiver>!")
        self.app.undo()
        self.assertEqual(self.app.doc.panels["front"][1].text, "Hey <receiver>")
        self.app.redo()
        self.assertEqual(self.app.doc.panels["front"][1].color, "#05666d")

    def test_mouse_drag_changes_position_and_can_be_undone(self):
        obj = self.app.doc.panels["front"][0]
        before = (obj.x, obj.y)
        x = round(self.app.origin[0] + (obj.x + obj.w / 2) * self.app.scale)
        y = round(self.app.origin[1] + (obj.y + obj.h / 2) * self.app.scale)
        self.app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        self.app.canvas.event_generate("<B1-Motion>", x=x + 30, y=y + 20)
        self.app.canvas.event_generate("<ButtonRelease-1>", x=x + 30, y=y + 20)
        self.root.update()
        self.assertGreater(self.app.doc.panels["front"][0].x, before[0])
        self.app.undo()
        self.assertEqual((self.app.doc.panels["front"][0].x, self.app.doc.panels["front"][0].y), before)

    def test_copy_between_sides_and_delete_are_reversible(self):
        original = self.app.doc.panels["front"][0]
        self.app.selected = {original.id}
        self.app.copy()
        self.app.switch_side("back")
        count = len(self.app.doc.panels["back"])
        self.app.paste()
        self.assertEqual(len(self.app.doc.panels["back"]), count + 1)
        self.assertNotEqual(self.app.doc.panels["back"][-1].id, original.id)
        self.app.delete()
        self.assertEqual(len(self.app.doc.panels["back"]), count)
        self.app.undo()
        self.assertEqual(len(self.app.doc.panels["back"]), count + 1)

    def test_saved_card_reopens_with_embedded_resources(self):
        self.app.add_text("A saved message", "inside")
        with TemporaryDirectory() as folder:
            target = Path(folder) / "saved.occard"
            self.app.path = target
            self.assertTrue(self.app.save())
            self.assertFalse(self.app.dirty)
            self.app.open_path(target)
            self.assertTrue(any(o.text == "A saved message" for o in self.app.doc.panels["inside"]))
            self.assertGreater(len(self.app.doc.embedded_art), 0)

    def test_template_search_and_all_artwork_are_available(self):
        self.app.search_var.set("BDAY1")
        self.app.refresh_library()
        self.assertTrue(any(row.path.stem == "BDAY1" for row in self.app.template_rows.values()))
        self.app.search_var.set("")
        self.app.all_art_var.set(True)
        self.app.refresh_library()
        self.assertEqual(len(self.app.art_rows), 616)

    def test_small_window_keeps_library_buttons_visible(self):
        self.root.geometry("1080x720")
        self.root.update()
        def buttons(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == "TButton":
                    yield child
                yield from buttons(child)
        controls = list(buttons(self.root))
        for label in ("Add / open selected", "Add paired front + inside message", "Print / PDF"):
            button = next(b for b in controls if b.cget("text") == label)
            self.assertLess(button.winfo_rooty() + button.winfo_height(), self.root.winfo_rooty() + self.root.winfo_height())
            self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())

    def test_print_preview_dialog_opens_and_full_page_disables_sides(self):
        self.app.print_dialog()
        self.root.update()
        self.assertTrue(any(isinstance(w, tk.Toplevel) for w in self.root.winfo_children()))
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.destroy()
        self.app._set_document(CardDocument(fold="full"))
        self.assertEqual(str(self.app.side_buttons["inside"].cget("state")), "disabled")

    def test_print_settings_and_practice_pdf_use_selected_paper(self):
        self.app.print_dialog()
        controls = self.app.print_controls
        controls.paper.set("Legal")
        controls.mode.set("Folding and printer test")
        for key, value in zip(controls.margins, (3, 7, 9, 11)):
            controls.margins[key].set(str(value))
        controls.refresh()
        self.root.update()
        self.assertIn("108.0", controls.info.get())
        self.assertIn("177.8", controls.info.get())
        self.assertEqual(str(controls.guides_check.cget("state")), "disabled")
        with TemporaryDirectory() as folder:
            path = Path(folder) / "practice.pdf"
            with patch("opencardshop.print_ui.filedialog.asksaveasfilename", return_value=str(path)):
                controls.save_pdf()
            self.assertTrue(path.is_file())
            self.assertEqual(self.app.doc.paper, "Legal")
            self.assertEqual(self.app.doc.print_margins, (3, 7, 9, 11))
            self.assertTrue(self.app.dirty)
            self.app.undo()
            self.assertEqual(self.app.doc.paper, "A4")

    def test_bad_margin_is_reported_before_export(self):
        self.app.print_dialog()
        controls = self.app.print_controls
        controls.margins["left"].set("nan")
        controls.refresh()
        self.assertIn("between 0 and 25", controls.info.get())
        self.assertFalse(self.app.dirty)

    def test_default_print_export_keeps_card_guides_unprinted(self):
        self.app.print_dialog()
        controls = self.app.print_controls
        controls.refresh()
        self.assertFalse(controls.guides.get())
        with TemporaryDirectory() as folder:
            path = Path(folder) / "card.pdf"
            from opencardshop.render import export_pdf
            with patch("opencardshop.print_ui.filedialog.asksaveasfilename", return_value=str(path)), \
                    patch("opencardshop.print_ui.export_pdf", wraps=export_pdf) as exporter:
                controls.save_pdf()
            self.assertFalse(exporter.call_args.kwargs["guides"])
            self.assertFalse(exporter.call_args.kwargs["test_page"])

    def test_printer_submission_uses_the_selected_test_sheet_and_single_sided_options(self):
        self.app.print_dialog()
        controls = self.app.print_controls
        controls.paper.set("Legal")
        controls.mode.set("Folding and printer test")
        controls.margins["bottom"].set("12")
        submitted = []
        def run(command, **kwargs):
            if command[0] == "lpstat":
                return subprocess.CompletedProcess(command, 0, "TestPrinter accepting requests\n", "")
            self.assertEqual(command[:5], ["lp", "-d", "TestPrinter", "-n", "2"])
            for option in ("media=Legal", "sides=one-sided", "print-scaling=none"):
                self.assertIn(option, command)
            self.assertTrue(Path(command[-1]).read_bytes().startswith(b"%PDF"))
            submitted.append(command)
            return subprocess.CompletedProcess(command, 0, "request id is TestPrinter-1\n", "")
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        from opencardshop.render import export_pdf
        with patch("opencardshop.print_ui.shutil.which", return_value="/usr/bin/lp"), \
                patch("opencardshop.print_ui.subprocess.run", side_effect=run), \
                patch("opencardshop.print_ui.export_pdf", wraps=export_pdf) as exporter:
            controls.physical_print()
            chooser = next(w for w in controls.window.winfo_children() if isinstance(w, tk.Toplevel))
            widgets = list(children(chooser))
            next(w for w in widgets if w.winfo_class() == "TSpinbox").set("2")
            next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "Print").invoke()
            self.assertEqual(len(submitted), 1)
            self.assertTrue(exporter.call_args.kwargs["test_page"])
            self.assertEqual(exporter.call_args.kwargs["margins"], (5, 5, 5, 12))
            self.assertEqual(self.app.doc.paper, "Legal")
            self.assertIn("TestPrinter-1", self.app.status_var.get())

    def test_print_without_cups_opens_pdf_in_viewer(self):
        """Windows, or Linux without CUPS: Print opens the print-ready PDF in the default viewer."""
        self.app.print_dialog()
        controls = self.app.print_controls
        controls.paper.set("Letter")
        opened = []
        with patch("opencardshop.print_ui.shutil.which", return_value=None), \
                patch("opencardshop.print_ui.open_path", side_effect=opened.append), \
                patch("opencardshop.print_ui.messagebox.showinfo") as told:
            controls.physical_print()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].read_bytes().startswith(b"%PDF"))
        self.assertIn("Actual size", told.call_args.args[1])
        self.assertEqual(self.app.doc.paper, "Letter")



@unittest.skipUnless(os.environ.get("DISPLAY"), "A display is required for GUI tests")
class NoLibraryGuiTests(unittest.TestCase):
    """Without any CardShop Plus content, the starter pack is offered and cards can be made, saved and printed."""

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = tk.Tk()
        self.app = CardShopApp(self.root, Path(self.folder.name) / "no-library")
        self.root.update()
        self.failures = []
        self.error_patch = patch("opencardshop.app.messagebox.showerror", side_effect=lambda title, text, **kw: self.failures.append((title, text)))
        self.error_patch.start()

    def tearDown(self):
        self.error_patch.stop()
        self.root.destroy()
        self.folder.cleanup()
        self.assertEqual(self.failures, [])

    def test_two_sided_half_fold_printing(self):
        """Duplex printers get one two-page job (flip on short edge); without duplex, side 1 then side 2."""
        from opencardshop.print_ui import LAYOUT_LABELS
        self.app.print_dialog()
        controls = self.app.print_controls
        controls.layout.set(LAYOUT_LABELS["half"])
        controls.refresh()
        self.assertIn("flip on short edge", controls.info.get())
        jobs = []

        def run(command, **kwargs):
            if command[0] == "lpstat":
                return subprocess.CompletedProcess(command, 0, "TestPrinter accepting requests\n", "")
            pdf = Path(command[-1]).read_bytes()
            self.assertEqual(pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r"), 2)
            jobs.append(command)
            return subprocess.CompletedProcess(command, 0, f"request id is TestPrinter-{len(jobs)}\n", "")

        def press_print():
            chooser = next(w for w in controls.window.winfo_children() if isinstance(w, tk.Toplevel))
            stack = [chooser]
            while stack:
                widget = stack.pop()
                if widget.winfo_class() == "TButton" and widget.cget("text") == "Print":
                    widget.invoke()
                    return
                stack.extend(widget.winfo_children())

        with patch("opencardshop.print_ui.shutil.which", return_value="/usr/bin/lp"), \
                patch("opencardshop.print_ui.subprocess.run", side_effect=run):
            controls.physical_print()
            press_print()
            self.assertEqual(len(jobs), 1)
            self.assertIn("sides=two-sided-short-edge", jobs[0])
            self.assertEqual(self.app.doc.print_layout, "half")

            self.app.print_dialog()
            controls = self.app.print_controls
            self.assertEqual(controls.layout.get(), LAYOUT_LABELS["half"], "the layout is remembered in the card")
            controls.manual.set(True)
            jobs.clear()
            with patch("opencardshop.print_ui.messagebox.askokcancel", return_value=True) as asked:
                controls.physical_print()
                press_print()
            self.assertEqual(asked.call_count, 1)
            self.assertEqual([("page-ranges=1" in j, "page-ranges=2" in j, "sides=one-sided" in j) for j in jobs],
                             [(True, False, True), (False, True, True)])

    def test_blank_card_with_own_text_and_picture_saves_and_prints(self):
        self.assertEqual(self.app.store.library_occasions, 0)
        self.assertIn("starter pack", self.app.status_var.get())
        self.assertTrue(self.app.doc.source.startswith("starter/"), "a starter card is open on first start")
        self.app.new_card("side")
        self.app.recipient_var.set("Aditi")
        self.app.add_text("Happy birthday, <receiver>!", "front")
        added = self.app.doc.panels["front"][-1]
        self.assertIn(added.font, self.app.store.fonts, "new text uses a font that is available without the CD")
        picture = Path(self.folder.name) / "picture.png"
        Image.new("RGB", (300, 200), "#d04a2b").save(picture)
        with patch("opencardshop.app.filedialog.askopenfilename", return_value=str(picture)):
            self.app.import_art()
        self.root.update()
        self.assertTrue(any(o.kind == "art" for o in self.app.doc.panels["front"]))
        card = Path(self.folder.name) / "mine.occard"
        self.app.path = card
        self.assertTrue(self.app.save())
        reopened = load_document(card)
        self.assertTrue(any(o.text == "Happy birthday, <receiver>!" for o in reopened.panels["front"]))
        from opencardshop.render import export_pdf
        pdf = Path(self.folder.name) / "mine.pdf"
        export_pdf(reopened, self.app.store, pdf, "A4")
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))


    def test_starter_card_opens_as_an_unsaved_copy(self):
        self.app.occasion_var.set("Diwali")
        self.app.refresh_library()
        first = next(iter(self.app.template_rows))
        self.app.card_tree.selection_set(first)
        self.app.use_template()
        self.assertEqual(self.app.doc.title, "Shubh Deepavali")
        self.assertIsNone(self.app.path)
        self.assertGreater(len(self.app.art_rows), 5)
        self.assertGreater(len(self.app.message_rows), 5)


@unittest.skipUnless(os.environ.get("DISPLAY"), "A display is required for GUI tests")
class MyLibraryGuiTests(unittest.TestCase):
    """Pictures, messages and designs saved to My library are offered again in later sessions."""

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.home = patch.dict(os.environ, {"OPENCARDSHOP_HOME": self.folder.name})
        self.home.start()
        self.failures = []
        self.error_patch = patch("opencardshop.app.messagebox.showerror", side_effect=lambda title, text, **kw: self.failures.append((title, text)))
        self.error_patch.start()
        self.root = tk.Tk()
        self.app = CardShopApp(self.root, Path(self.folder.name) / "no-cd")
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self.error_patch.stop()
        self.home.stop()
        self.folder.cleanup()
        self.assertEqual(self.failures, [])

    def test_save_reuse_and_remove_library_items(self):
        app = self.app
        picture = next(o for o in app.doc.panels["front"] if o.kind == "art" and "bg-" not in o.art)
        app.selected = {picture.id}
        app.library_save_picture()
        self.assertEqual(app.occasion_var.get(), "My library")
        self.assertEqual(len(app.art_rows), 1)
        text = next(o for o in app.doc.panels["front"] if o.kind == "text")
        app.selected = {text.id}
        app.library_save_text()
        app._save_new_message("Front words", "Inside words", "")
        self.assertEqual(len(app.message_rows), 2)
        with patch("opencardshop.app.simpledialog.askstring", return_value="Kiosk design"):
            app.library_save_design()
        self.assertEqual([t.label for t in app.template_rows.values()], ["Kiosk design"])

        # A new session (or a new card) offers the same items.
        self.root.destroy()
        self.root = tk.Tk()
        app = self.app = CardShopApp(self.root, Path(self.folder.name) / "no-cd")
        app.occasion_var.set("My library")
        app.refresh_library()
        self.assertEqual((len(app.template_rows), len(app.art_rows), len(app.message_rows)), (1, 1, 2))
        app.new_card("top")
        app.library_tabs.select(1)
        app.art_tree.selection_set(next(iter(app.art_rows)))
        app.add_library_art()
        placed = app.doc.panels["front"][-1]
        self.assertIn(placed.art, app.doc.embedded_art, "placed pictures carry their own copy")

        app.library_tabs.select(2)
        app.message_tree.selection_set(next(iter(app.message_rows)))
        with patch("opencardshop.app.messagebox.askyesno", return_value=True):
            app.library_remove()
        self.assertEqual(len(app.message_rows), 1)

    def test_message_dialog_saves_all_three_parts(self):
        from opencardshop.app import MessageDialog
        saved = []
        dialog = MessageDialog(self.root, lambda *parts: saved.append(parts))
        dialog.fields["front"].insert("1.0", "Welcome to the museum!")
        dialog.fields["back"].insert("1.0", "Made at VITM by <sender>")
        dialog.save()
        self.assertEqual(saved, [("Welcome to the museum!", "", "Made at VITM by <sender>")])


if __name__ == "__main__":
    unittest.main()
