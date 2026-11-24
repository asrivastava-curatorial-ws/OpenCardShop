"""Corpus and behavioral regression tests, using the actual supplied files."""
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import json
import struct
import unittest

from PIL import Image, ImageChops
from opencardshop.assets import AssetStore
from opencardshop.formats import FormatError, expand_szdd, read_cmk, read_messages, read_wmf
from opencardshop.model import CardDocument, CardObject, save_document, load_document
from opencardshop.render import render_panel, compose_flat_sheet, export_pdf
from opencardshop.wmf import render_wmf

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "assets/original"
LIBRARY_PRESENT = (ORIGINAL / "CARDSHOP.INI").is_file() and (ROOT / "assets/rendered/asset_report.json").is_file()
NO_LIBRARY = "Needs the CardShop Plus asset pack (or your CD in assets/original plus tools/rebuild_assets.py --inkscape)"


@unittest.skipUnless(LIBRARY_PRESENT, NO_LIBRARY)
class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The CardShop content only: the starter pack and My library are tested in test_library.
        cls.store = AssetStore(ORIGINAL, ROOT / "assets/rendered", starter=None, personal=False)

    def card(self, name="BDAY/BDAY1.CMK"):
        return CardDocument.from_legacy(read_cmk(ORIGINAL / name), Path(name).stem)

    def assert_same_image(self, first, second):
        self.assertEqual(first.size, second.size)
        self.assertIsNone(ImageChops.difference(first.convert("RGB"), second.convert("RGB")).getbbox())

    def test_every_original_card_parses_without_trailing_bytes(self):
        paths = list(ORIGINAL.rglob("*.CMK"))
        self.assertEqual(len(paths), 315)
        for path in paths:
            with self.subTest(path=path.name):
                card = read_cmk(path)
                self.assertIn(card.fold, ("side", "top", "full"))
        self.assertEqual(sum(len(self.store.templates(o)) for o in self.store.occasions), 231)

    def test_old_card_has_real_panel_counts_color_and_font(self):
        card = read_cmk(ORIGINAL / "BDAY/BDAY1.CMK")
        self.assertEqual(card.fold, "side")
        self.assertEqual([len(card.panels[s]) for s in ("front", "inside", "back")], [3, 3, 2])
        self.assertEqual(card.panels["front"][1].text, "Hey <receiver>")
        self.assertEqual(card.panels["front"][1].font, "PixieFont")
        self.assertEqual(card.panels["front"][1].color, "#0000ff")
        self.assertEqual(card.panels["front"][1].height, 560)

    def test_version_120_has_extra_header_word_before_fold(self):
        card = read_cmk(ORIGINAL / "BDAY/BRTHD.CMK")
        self.assertEqual(card.header_flags, 0)
        self.assertEqual(card.fold, "side")
        self.assertEqual([len(card.panels[s]) for s in ("front", "inside", "back")], [2, 6, 2])

    def test_every_prepared_vector_is_a_valid_standard_wmf(self):
        report = json.loads((ROOT / "assets/rendered/asset_report.json").read_text())
        self.assertEqual(report["summary"]["vector"], 611)
        for entry in report["artwork"]:
            if entry["status"] != "vector":
                continue
            with self.subTest(art=entry["name"]):
                mf = read_wmf(self.store.art_files[entry["name"]].read_bytes())
                self.assertEqual(mf.records[-1][0], 0)
                self.assertGreater(mf.inch, 0)

    def test_szdd_damage_is_reported(self):
        original = (ORIGINAL / "ART/BDAY1.CMF").read_bytes()
        with self.assertRaises(FormatError):
            expand_szdd(original[:30])
        changed = bytearray(original)
        struct.pack_into("<I", changed, 10, 100_000_000)
        with self.assertRaises(FormatError):
            expand_szdd(bytes(changed))
        raw = expand_szdd(original)
        self.assertEqual(raw[:4], b"\xd7\xcd\xc6\x9a")

    def test_bitmap_fallbacks_and_missing_source_remain_explicit(self):
        for name in ("BONV31.CMF", "BORDER2.CMF", "REL86.CMF"):
            with self.subTest(name=name):
                image = self.store.image(name)
                self.assertGreater(image.width, 1)
                self.assertIn(name, self.store.issues)
        for name in ("BUS72.CMF", "HAL32.CMF"):
            with self.subTest(name=name), self.assertRaises(FormatError):
                self.store.image(name)

    def test_known_good_vector_renders_with_python_and_is_upright(self):
        p = ORIGINAL / "ART/BDAY1.CMF"
        pure_rgba = render_wmf(p.read_bytes(), (384, 223), self.store.font)
        reference_rgba = self.store.image("BDAY1.CMF").resize(pure_rgba.size)
        pure = Image.new("RGBA", pure_rgba.size, "white")
        reference = Image.new("RGBA", pure_rgba.size, "white")
        pure.alpha_composite(pure_rgba)
        reference.alpha_composite(reference_rgba)
        pure, reference = pure.convert("RGB"), reference.convert("RGB")
        # Broad color regions must agree; antialiasing and cosmetic pen widths can differ.
        sample_points = [(0.2, 0.2), (0.18, 0.47), (0.6, 0.43), (0.45, 0.4), (0.45, 0.48), (0.85, 0.65)]
        for x, y in sample_points:
            point = (int(x * pure.width), int(y * pure.height))
            a, b = pure.getpixel(point), reference.getpixel(point)
            self.assertLess(sum(abs(v - w) for v, w in zip(a, b)), 25)

    def test_messages_and_name_substitution(self):
        messages = read_messages(ORIGINAL / "BDAY/MESSAGE.DAT")
        pair = next(m for m in messages if m.front == "Make a birthday wish, <receiver>!")
        self.assertIn("<sender>", pair.inside)
        doc = self.card()
        doc.recipient, doc.sender = "Aditi", "Ravi"
        self.assertEqual(doc.substitute("For <receiver>, from <sender>"), "For Aditi, from Ravi")

    def test_portable_save_reopens_without_original_content(self):
        doc = self.card()
        doc.recipient, doc.sender = "Aditi", "Ravi"
        with TemporaryDirectory() as folder:
            target = Path(folder) / "saved.occard"
            save_document(doc, target, self.store)
            restored = load_document(target)
            empty = Path(folder) / "empty"
            empty.mkdir()
            detached_store = AssetStore(empty)
            for side in ("front", "inside", "back"):
                self.assert_same_image(render_panel(doc, side, self.store, width=500),
                                       render_panel(restored, side, detached_store, width=500))

    def test_save_preserves_independent_font_variants_and_custom_image(self):
        doc = CardDocument()
        for i, (bold, italic) in enumerate(((False, False), (True, False), (False, True))):
            doc.panels["front"].append(CardObject("text", 100, 100 + i * 500, 3500, 400,
                                                text="Portable font", font="Arial", bold=bold, italic=italic))
        image = Image.new("RGBA", (100, 150), (15, 200, 60, 255))
        data = io.BytesIO()
        image.save(data, "PNG")
        doc.embedded_art["custom.png"] = data.getvalue()
        doc.panels["front"].append(CardObject("art", 500, 2000, 1000, 1500, art="custom.png"))
        with TemporaryDirectory() as folder:
            target = Path(folder) / "custom.occard"
            save_document(doc, target, self.store)
            restored = load_document(target)
            self.assertEqual(len(restored.embedded_fonts), 3)
            self.assert_same_image(render_panel(doc, "front", self.store, width=500),
                                   render_panel(restored, "front", self.store, width=500))

    def test_failed_save_preserves_existing_file(self):
        doc = self.card()
        doc.panels["front"].append(CardObject("art", 0, 0, 100, 100, art="MISSING.CMF"))
        with TemporaryDirectory() as folder:
            target = Path(folder) / "existing.occard"
            target.write_bytes(b"existing content")
            with self.assertRaises(FormatError):
                save_document(doc, target, self.store)
            self.assertEqual(target.read_bytes(), b"existing content")

    def colored_card(self, fold):
        doc = CardDocument(fold=fold)
        for side, color in (("front", "#f00000"), ("inside", "#00c000"), ("back", "#0000e0")):
            w, h = doc.dimensions(side)
            image = Image.new("RGBA", (100, 100), color)
            data = io.BytesIO()
            image.save(data, "PNG")
            doc.embedded_art[side] = data.getvalue()
            doc.panels[side].append(CardObject("art", 0, 0, w, h, art=side))
        return doc

    def test_side_fold_print_has_all_panels_on_one_sheet(self):
        sheet = compose_flat_sheet(self.colored_card("side"), self.store, dpi=40)
        self.assertEqual(sheet.size, (340, 440))
        self.assertEqual(sheet.getpixel((85, 110))[:3], (0, 192, 0))
        self.assertEqual(sheet.getpixel((255, 110))[:3], (0, 192, 0))
        self.assertEqual(sheet.getpixel((85, 330))[:3], (0, 0, 224))
        self.assertEqual(sheet.getpixel((255, 330))[:3], (240, 0, 0))

    def test_top_fold_print_has_vertical_inside_spread(self):
        sheet = compose_flat_sheet(self.colored_card("top"), self.store, dpi=40)
        self.assertEqual(sheet.size, (440, 340))
        self.assertEqual(sheet.getpixel((110, 85))[:3], (0, 192, 0))
        self.assertEqual(sheet.getpixel((110, 255))[:3], (0, 192, 0))
        self.assertEqual(sheet.getpixel((330, 85))[:3], (0, 0, 224))
        self.assertEqual(sheet.getpixel((330, 255))[:3], (240, 0, 0))

    def test_pdf_is_one_page_and_matches_selected_paper(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("Optional PyMuPDF is not installed for PDF inspection")
        with TemporaryDirectory() as folder:
            for fold in ("side", "top", "full"):
                path = Path(folder) / (fold + ".pdf")
                export_pdf(self.colored_card(fold), self.store, path, "A4", dpi=72)
                with pymupdf.open(path) as pdf:
                    self.assertEqual(len(pdf), 1)
                    expected = (842, 595) if fold == "top" else (595, 842)
                    self.assertAlmostEqual(pdf[0].rect.width, expected[0], delta=1)
                    self.assertAlmostEqual(pdf[0].rect.height, expected[1], delta=1)

    def test_full_page_design_has_no_fold_panels(self):
        doc = self.colored_card("full")
        self.assert_same_image(compose_flat_sheet(doc, self.store, dpi=40), render_panel(doc, "front", self.store, dpi=40))


if __name__ == "__main__":
    unittest.main()
