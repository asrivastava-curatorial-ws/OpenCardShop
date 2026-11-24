"""Physical fold orientation, margin centring, and print document checks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import unittest

from PIL import Image, ImageDraw, ImageChops
from opencardshop.assets import AssetStore
from opencardshop.model import CardDocument, CardObject, save_document, load_document
from opencardshop.printing import paper_layout, validate_margins, diagnostic_document
from opencardshop.render import compose_flat_sheet, print_sheet, render_panel, export_pdf

ROOT = Path(__file__).resolve().parents[1]


class PrintingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = AssetStore(ROOT / "assets/original", ROOT / "assets/rendered")

    def marked_card(self, fold):
        doc = CardDocument(fold=fold)
        for side, color in (("front", "#90dbdb"), ("inside", "#c5d4ed"), ("back", "#e2bc99")):
            w, h = doc.dimensions(side)
            width, height = round(w * .04), round(h * .04)
            image = Image.new("RGBA", (width, height), color)
            draw = ImageDraw.Draw(image)
            for x, y, c in ((12, 12, "#ff0000"), (width - 30, 12, "#00ff00"),
                            (width - 30, height - 30, "#0000ff"), (12, height - 30, "#ff00ff")):
                draw.rectangle((x, y, x + 18, y + 18), fill=c)
            data = io.BytesIO();image.save(data, "PNG")
            doc.embedded_art[side] = data.getvalue()
            doc.panels[side].append(CardObject("art", 0, 0, w, h, art=side))
        return doc

    def assert_image(self, first, second):
        self.assertEqual(first.size, second.size)
        self.assertIsNone(ImageChops.difference(first.convert("RGB"), second.convert("RGB")).getbbox())

    def test_side_fold_faces_are_upright_after_the_two_physical_folds(self):
        doc = self.marked_card("side")
        flat = compose_flat_sheet(doc, self.store, dpi=40)
        cx, cy = flat.width // 2, flat.height // 2
        front = flat.crop((cx, cy, flat.width, flat.height))
        # Folding left behind right and turning the closed card over each reverse
        # the horizontal direction, so the back's two reversals cancel.
        back = flat.crop((0, cy, cx, flat.height)).transpose(Image.Transpose.FLIP_LEFT_RIGHT).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        # First horizontal crease reverses Y; viewing the inside reverses X.
        inside = flat.crop((0, 0, flat.width, cy)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        for side, actual in (("front", front), ("back", back), ("inside", inside)):
            self.assert_image(actual, render_panel(doc, side, self.store, dpi=40))

    def test_top_fold_faces_are_upright_after_the_two_physical_folds(self):
        doc = self.marked_card("top")
        flat = compose_flat_sheet(doc, self.store, dpi=40)
        cx, cy = flat.width // 2, flat.height // 2
        front = flat.crop((cx, cy, flat.width, flat.height))
        # Top-behind-bottom reverses Y; turning the back toward the viewer
        # reverses X. Both reversals are required for an upright back cover.
        back = flat.crop((cx, 0, flat.width, cy)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        inside = flat.crop((0, 0, cx, flat.height)).transpose(Image.Transpose.FLIP_LEFT_RIGHT).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        for side, actual in (("front", front), ("back", back), ("inside", inside)):
            self.assert_image(actual, render_panel(doc, side, self.store, dpi=40))

    def test_unequal_margins_keep_folded_artwork_at_the_physical_sheet_centre(self):
        for fold in ("side", "top"):
            image = print_sheet(self.marked_card(fold), self.store, "A4", dpi=72, margins=(5, 20, 8, 25))
            difference = ImageChops.difference(image, Image.new("RGB", image.size, "white"))
            left, top, right, bottom = difference.getbbox()
            self.assertAlmostEqual((left + right) / 2, image.width / 2, delta=1)
            self.assertAlmostEqual((top + bottom) / 2, image.height / 2, delta=1)
            self.assertGreaterEqual(left, round(20 / 25.4 * 72) - 1)
            self.assertGreaterEqual(top, round(25 / 25.4 * 72) - 1)

    def test_a4_panels_are_centred_in_their_quarters_and_spreads_stay_joined(self):
        margin = round(5 / 25.4 * 72)
        for fold in ("side", "top"):
            sheet = print_sheet(self.marked_card(fold), self.store, "A4", dpi=72)
            front = sheet.crop((sheet.width // 2, sheet.height // 2, sheet.width, sheet.height))
            box = ImageChops.difference(front, Image.new("RGB", front.size, "white")).getbbox()
            left, top, right, bottom = box[0], box[1], front.width - box[2], front.height - box[3]
            with self.subTest(fold=fold):
                if fold == "side":
                    # Spine on the left stays joined; the top fold and the cut edge share the spare space.
                    self.assertLessEqual(left, 1)
                    self.assertAlmostEqual(top, bottom, delta=2)
                    self.assertGreater(top, margin)
                else:
                    # Hinge at the top stays joined; the left fold and the cut edge share the spare space.
                    self.assertLessEqual(top, 1)
                    self.assertAlmostEqual(left, right, delta=2)
                    self.assertGreater(left, margin)

    def test_full_page_uses_its_asymmetric_printable_area(self):
        layout = paper_layout("full", "A4", (5, 20, 8, 25))
        self.assertEqual(layout.available_box_mm, (5, 8, 190, 272))
        image = print_sheet(self.marked_card("full"), self.store, "A4", dpi=72, margins=(5, 20, 8, 25))
        box = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
        self.assertAlmostEqual((box[0] + box[2]) / 2, 97.5 / 25.4 * 72, delta=1)
        self.assertAlmostEqual((box[1] + box[3]) / 2, 140 / 25.4 * 72, delta=1)

    def test_legal_paper_has_the_expected_finished_card_sizes(self):
        self.assertEqual(paper_layout("side", "Legal").finished_size_mm, (107.95, 177.8))
        self.assertEqual(paper_layout("top", "Legal").finished_size_mm, (177.8, 107.95))
        for fold, size in (("side", (612, 1008)), ("top", (1008, 612))):
            self.assertEqual(print_sheet(self.marked_card(fold), self.store, "Legal", dpi=72).size, size)

    def test_preview_guides_do_not_change_clean_export(self):
        doc = self.marked_card("side")
        clean = print_sheet(doc, self.store, dpi=72)
        preview = print_sheet(doc, self.store, dpi=72, preview_guides=True)
        practice = print_sheet(doc, self.store, dpi=72, guides=True)
        self.assertIsNotNone(ImageChops.difference(clean, preview).getbbox())
        self.assertIsNotNone(ImageChops.difference(clean, practice).getbbox())
        self.assert_image(clean, print_sheet(doc, self.store, dpi=72))

    def test_test_page_contains_four_distinct_faces_without_changing_the_card(self):
        doc = self.marked_card("side")
        snapshot = doc.snapshot()
        test = diagnostic_document("side")
        messages = [obj.text for panel in test.panels.values() for obj in panel]
        for face in ("FRONT", "BACK", "INSIDE LEFT", "INSIDE RIGHT"):
            self.assertTrue(any(face in text for text in messages))
        print_sheet(doc, self.store, dpi=72, test_page=True)
        self.assertEqual(doc, snapshot)

    def test_practice_ruler_is_one_hundred_millimetres(self):
        image = print_sheet(self.marked_card("side"), self.store, "A4", dpi=254, test_page=True)
        y = 120  # 5 mm top margin + 7 mm ruler inset, at exactly 10 px/mm.
        # The ruler's endpoint ticks span exactly 100 mm (1,000 pixels).
        self.assertEqual(image.getpixel((image.width // 2 - 500, y)), (23, 47, 67))
        self.assertEqual(image.getpixel((image.width // 2 + 500, y)), (23, 47, 67))

    def test_print_preferences_round_trip_and_old_documents_keep_defaults(self):
        doc = self.marked_card("side")
        doc.paper, doc.print_margins = "Legal", (3, 7, 9, 11)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "card.occard"
            save_document(doc, path, self.store)
            loaded = load_document(path)
            self.assertEqual((loaded.paper, loaded.print_margins), ("Legal", (3, 7, 9, 11)))
        example = ROOT / "examples/birthday-side-fold.occard"
        if example.is_file():  # shipped with the CardShop Plus asset pack
            old = load_document(example)
            self.assertEqual(old.print_margins, (5, 5, 5, 5))

    def test_invalid_margins_are_rejected(self):
        for values in ((-1, 5, 5, 5), (5, 26, 5, 5), (5, float("nan"), 5, 5), (5, 5), (5, 5, float("inf"), 5)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_margins(values)

    def test_legal_export_is_one_page_in_the_correct_orientation(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("Optional PyMuPDF is not installed for page inspection")
        with TemporaryDirectory() as directory:
            for fold in ("side", "top"):
                path = Path(directory) / (fold + ".pdf")
                export_pdf(self.marked_card(fold), self.store, path, "Legal", dpi=72, test_page=True)
                with fitz.open(path) as pdf:
                    self.assertEqual(len(pdf), 1)
                    self.assertEqual(tuple(pdf[0].rect[2:]), (612, 1008) if fold == "side" else (1008, 612))

    # Two-sided, folded once ------------------------------------------------------
    def test_half_fold_geometry(self):
        side = paper_layout("side", "A4", (5, 8, 5, 10), layout="half")
        self.assertEqual(side.size_mm, (297.0, 210.0))
        self.assertEqual(side.finished_size_mm, (148.5, 210.0))
        self.assertEqual(side.available_box_mm, (8, 10, 289, 200))
        top = paper_layout("top", "Letter", layout="half")
        self.assertEqual(top.size_mm, (215.9, 279.4))
        self.assertEqual(top.finished_size_mm, (215.9, 139.7))
        with self.assertRaises(ValueError):
            paper_layout("side", "A4", layout="booklet")

    def test_half_fold_faces_land_behind_each_other_after_a_short_edge_flip(self):
        from opencardshop.render import half_fold_pages
        colours = {"front": (0x90, 0xdb, 0xdb), "inside": (0xc5, 0xd4, 0xed), "back": (0xe2, 0xbc, 0x99)}

        def close(pixel, colour):
            return all(abs(a - b) <= 3 for a, b in zip(pixel, colour))

        for fold in ("side", "top"):
            with self.subTest(fold=fold):
                outside, inside = half_fold_pages(self.marked_card(fold), self.store, "A4", dpi=60, margins=(5, 8, 5, 10))
                width, height = outside.size
                self.assertEqual(width > height, fold == "side")
                self.assertEqual(inside.size, outside.size)
                for page in (outside, inside):
                    left, top, right, bottom = ImageChops.difference(page, Image.new("RGB", page.size, "white")).getbbox()
                    # The spread is centred, so the fold is the sheet's centre line on both sides.
                    self.assertLessEqual(abs((left + right) - width), 2)
                    self.assertLessEqual(abs((top + bottom) - height), 2)
                if fold == "side":
                    front_at, back_at = (width * 3 // 4, height // 2), (width // 4, height // 2)
                    first_inside, other_inside = (width // 4, height // 2), (width * 3 // 4, height // 2)
                    behind = lambda x, y: (width - 1 - x, y)      # flip on the short edge of a landscape sheet
                else:
                    front_at, back_at = (width // 2, height * 3 // 4), (width // 2, height // 4)
                    first_inside, other_inside = (width // 2, height // 4), (width // 2, height * 3 // 4)
                    behind = lambda x, y: (x, height - 1 - y)     # flip on the short edge of a portrait sheet
                self.assertTrue(close(outside.getpixel(front_at), colours["front"]))
                self.assertTrue(close(outside.getpixel(back_at), colours["back"]))
                self.assertTrue(close(inside.getpixel(first_inside), colours["inside"]))
                self.assertTrue(close(inside.getpixel(other_inside), colours["inside"]))
                # The half of side 2 behind the front is the first inside panel (left, or top):
                # it holds the inside artwork's top-left red mark.
                region = inside.crop((0, 0, width // 2, height) if fold == "side" else (0, 0, width, height // 2))
                self.assertIn((255, 0, 0), {c for _, c in region.getcolors(1 << 20)})
                bx, by = behind(*front_at)
                self.assertEqual((bx < width // 2) if fold == "side" else (by < height // 2), True)
                # The back of a top fold is printed upside down so it reads upright once folded:
                # its top-left red mark is at the lower right of the upper half.
                if fold == "top":
                    upper = outside.crop((0, 0, width, height // 2))
                    reds = [(x, y) for x in range(0, upper.width, 2) for y in range(0, upper.height, 2) if upper.getpixel((x, y)) == (255, 0, 0)]
                    self.assertTrue(reds and min(x for x, _ in reds) > upper.width // 2 and min(y for _, y in reds) > upper.height // 2)
                rotated = half_fold_pages(self.marked_card(fold), self.store, "A4", dpi=60, margins=(5, 8, 5, 10), rotate_second=True)[1]
                self.assert_image(rotated, inside.transpose(Image.Transpose.ROTATE_180))

    def test_half_fold_pdf_has_two_pages_and_the_layout_is_saved(self):
        from opencardshop.render import export_pdf
        with TemporaryDirectory() as folder:
            doc = self.marked_card("side")
            pdf = Path(folder) / "half.pdf"
            export_pdf(doc, self.store, pdf, "A4", dpi=72, layout="half")
            self.assertEqual(pdf.read_bytes().count(b"/Type /Page\n") + pdf.read_bytes().count(b"/Type /Page\r"), 2)
            test = Path(folder) / "test.pdf"
            export_pdf(doc, self.store, test, "A4", dpi=72, layout="half", test_page=True)
            self.assertTrue(test.read_bytes().startswith(b"%PDF"))
            doc.print_layout = "half"
            card = Path(folder) / "card.occard"
            save_document(doc, card, self.store)
            self.assertEqual(load_document(card).print_layout, "half")
            self.assertEqual(CardDocument().print_layout, "quarter")


if __name__ == "__main__":
    unittest.main()
