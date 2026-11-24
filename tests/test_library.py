"""Starter pack, installed fonts, My library and per-user settings. None of these need the CardShop CD."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import json
import os
import shutil
import subprocess
import unittest

from PIL import Image

from opencardshop import paths, sysfonts
from opencardshop.assets import AssetStore, MINE_KEY, STARTER_KEY
from opencardshop.model import CardDocument, CardObject, load_document
from opencardshop.mylibrary import MyLibrary
from opencardshop.render import render_panel
from opencardshop.starter import StarterLibrary

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "assets/starter"
FALLBACK = ROOT / "assets/fallback_fonts/LiberationSans-Regular.ttf"


class StarterPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = TemporaryDirectory()
        cls.store = AssetStore(Path(cls.folder.name) / "no-cd", None, personal=Path(cls.folder.name) / "mine")

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_every_occasion_has_cards_pictures_and_messages(self):
        library = self.store.starter
        self.assertGreaterEqual(len(library.occasions), 14)
        self.assertEqual(self.store.library_occasions, 0)
        for key, occasion in library.occasions.items():
            with self.subTest(occasion=key):
                self.assertTrue(occasion.art)
                self.assertTrue(occasion.messages)
                self.assertTrue(occasion.cards)
                self.assertEqual(len(self.store.templates(STARTER_KEY + key)), len(occasion.cards))
                self.assertEqual(self.store.messages(STARTER_KEY + key), occasion.messages)

    def test_every_starter_card_opens_and_renders_every_side_without_errors(self):
        for occasion in self.store.starter.occasions.values():
            for card in occasion.cards:
                doc = load_document(card.path)
                self.assertEqual(doc.fold, card.fold)
                for side in ("front", "inside", "back") if doc.fold != "full" else ("front",):
                    with self.subTest(card=card.path.name, side=side):
                        errors = []
                        render_panel(doc, side, self.store, dpi=20, errors=errors)
                        self.assertEqual(errors, [])

    def test_every_picture_loads_and_the_open_fonts_are_offered(self):
        for name in self.store.starter.art:
            with self.subTest(picture=name):
                self.assertGreaterEqual(min(self.store.image(name).size), 500)
        for family in ("Pacifico", "Great Vibes", "Playfair Display", "Baloo 2", "Dancing Script", "Lobster", "Caveat"):
            self.assertIn(family, self.store.fonts)

    def test_every_bundled_file_is_attributed_and_licensed(self):
        attribution = (STARTER / "ATTRIBUTION.md").read_text(encoding="utf-8")
        for picture in (STARTER / "art").iterdir():
            if not picture.name.startswith("bg-"):
                self.assertIn(f"art/{picture.name}", attribution)
        fonts = [p for p in (STARTER / "fonts").iterdir() if p.suffix == ".ttf"]
        self.assertEqual(len(fonts), len(list((STARTER / "fonts").glob("OFL-*.txt"))))
        for font in fonts:
            self.assertIn(font.name, attribution)
        self.assertIn("MIT License", (STARTER / "LICENSE-FluentEmoji.txt").read_text(encoding="utf-8"))

    def test_library_index_ignores_unsafe_or_missing_entries(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "art").mkdir()
            (root / "cards").mkdir()
            Image.new("RGBA", (8, 8)).save(root / "art" / "ok.png")
            (root / "library.json").write_text(json.dumps({"format": "OpenCardShop starter library", "version": 1, "occasions": [
                {"id": "test", "label": "Test", "art": ["ok.png", "../escape.png", "missing.png"],
                 "cards": [{"file": "../../evil.occard", "fold": "side"}, {"file": "missing.occard", "fold": "side"}],
                 "messages": [{"front": "Hello"}, {"nothing": 1}, "bad"]},
                {"id": "../bad", "label": "Bad"}]}), encoding="utf-8")
            library = StarterLibrary(root)
            self.assertEqual(list(library.occasions), ["test"])
            occasion = library.occasions["test"]
            self.assertEqual(occasion.art, ["starter/ok.png"])
            self.assertEqual(occasion.cards, [])
            self.assertEqual([m.front for m in occasion.messages], ["Hello"])


class SystemFontTests(unittest.TestCase):
    def test_fontconfig_listing_keeps_only_addressable_faces(self):
        listing = ("/x/a.ttf\tAlpha\tRegular\t0\n/x/b.ttc\tBeta\tBold\t2\n/x/c.otf\tGamma\tItalic\t0\n"
                   "/x/v.ttf\tAlpha\tBold\t65536\n/x/t.pfb\tDelta\tRegular\t0\nbroken line\n")
        with patch.dict(os.environ, {"OPENCARDSHOP_NO_SYSTEM_FONTS": ""}), patch.object(sysfonts.sys, "platform", "linux"), \
                patch("opencardshop.sysfonts.subprocess.run", return_value=subprocess.CompletedProcess([], 0, listing, "")):
            fonts = sysfonts.installed_fonts()
        self.assertEqual(fonts, {"Alpha": [(Path("/x/a.ttf"), "Regular")], "Gamma": [(Path("/x/c.otf"), "Italic")]})

    def test_font_folders_are_read_once_and_cached(self):
        with TemporaryDirectory() as folder:
            fonts = Path(folder) / "fonts"
            fonts.mkdir()
            shutil.copy(FALLBACK, fonts / "Sample.ttf")
            environment = {"OPENCARDSHOP_NO_SYSTEM_FONTS": "", "OPENCARDSHOP_HOME": str(Path(folder) / "home")}
            with patch.dict(os.environ, environment), patch.object(sysfonts.sys, "platform", "win32"), \
                    patch("opencardshop.sysfonts.font_folders", return_value=[fonts]):
                first = sysfonts.installed_fonts()
                self.assertTrue((Path(folder) / "home/cache/system-fonts.json").is_file())
                with patch("opencardshop.sysfonts.ImageFont.truetype", side_effect=OSError("must use the cache")):
                    second = sysfonts.installed_fonts()
        self.assertEqual(first, {"Liberation Sans": [(fonts / "Sample.ttf", "Regular")]})
        self.assertEqual(second, first)

    def test_installed_fonts_are_added_without_replacing_card_fonts(self):
        installed = {"Pacifico": [(FALLBACK, "Regular")], "Test Sans": [(FALLBACK, "Regular")]}
        with TemporaryDirectory() as folder, patch("opencardshop.assets.installed_fonts", return_value=installed):
            store = AssetStore(Path(folder) / "no-cd", None, personal=False)
        self.assertEqual(store.fonts["Test Sans"], [(FALLBACK, "Regular")])
        self.assertTrue(str(store.fonts["Pacifico"][0][0]).startswith(str(STARTER)))

    def test_system_fonts_can_be_switched_off(self):
        with patch.dict(os.environ, {"OPENCARDSHOP_NO_SYSTEM_FONTS": "1"}):
            self.assertEqual(sysfonts.installed_fonts(), {})


class MyLibraryTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = Path(self.folder.name) / "my-library"
        self.no_cd = Path(self.folder.name) / "no-cd"

    def tearDown(self):
        self.folder.cleanup()

    def test_pictures_messages_and_designs_are_reused_in_a_new_session(self):
        library = MyLibrary(self.root)
        name = library.add_picture(Image.new("RGBA", (300, 200), "#d04a2b"), "My Logo.png")
        self.assertEqual(name, "mine/my-logo.png")
        self.assertTrue(library.add_message("Hello <receiver>", "See you soon"))
        self.assertFalse(library.add_message("Hello <receiver>", "See you soon"))
        store = AssetStore(self.no_cd, None, personal=self.root)
        doc = CardDocument(title="Logo card")
        doc.panels["front"].append(CardObject("art", 500, 500, 2000, 1333, art=name))
        library.add_card(doc, store, "Logo card")

        fresh = AssetStore(self.no_cd, None, personal=self.root)  # another session, another card
        self.assertEqual(fresh.occasions[MINE_KEY], "My library")
        self.assertEqual(fresh.occasion_art(MINE_KEY), [name])
        self.assertEqual([m.front for m in fresh.messages(MINE_KEY)], ["Hello <receiver>"])
        template = fresh.templates(MINE_KEY)[0]
        self.assertEqual((template.fold, template.path.with_suffix(".png").is_file()), ("side", True))
        card = load_document(template.path)
        self.assertIn(name, card.embedded_art)

        library.remove_picture(name)
        fresh.library_changed()
        self.assertEqual(fresh.occasion_art(MINE_KEY), [])
        errors = []
        render_panel(card, "front", fresh, dpi=20, errors=errors)
        self.assertEqual(errors, [], "a saved design keeps its own copy of the picture")
        library.remove_message(library.messages[0])
        library.remove_card(template.path)
        self.assertTrue(MyLibrary(self.root).is_empty())

    def test_pictures_copied_into_the_folder_appear(self):
        (self.root / "art").mkdir(parents=True)
        Image.new("RGB", (64, 64), "navy").save(self.root / "art" / "Holiday photo.jpg")
        (self.root / "art" / "notes.txt").write_text("not a picture")
        store = AssetStore(self.no_cd, None, personal=self.root)
        self.assertEqual(store.occasion_art(MINE_KEY), ["mine/Holiday photo.jpg"])
        self.assertEqual(store.image("mine/Holiday photo.jpg").size, (64, 64))

    def test_export_and_import_merge_into_another_library(self):
        source = MyLibrary(self.root)
        source.add_picture(Image.new("RGBA", (40, 40), "gold"), "star")
        source.add_message(inside="Thank you for visiting!")
        store = AssetStore(self.no_cd, None, personal=self.root)
        source.add_card(CardDocument(title="Plain"), store, "Plain")
        archive = Path(self.folder.name) / "my-library.zip"
        self.assertEqual(source.export_zip(archive), 3)  # picture, design and its thumbnail

        target = MyLibrary(Path(self.folder.name) / "kiosk")
        target.add_picture(Image.new("RGBA", (40, 40), "red"), "star")
        added = target.import_zip(archive)
        self.assertEqual(added, {"pictures": 1, "cards": 1, "messages": 1})
        self.assertEqual(sorted(target.art), ["mine/star-2.png", "mine/star.png"])
        self.assertEqual(target.import_zip(archive)["messages"], 0, "messages are not duplicated")

    def test_import_ignores_unsafe_and_invalid_entries(self):
        archive = Path(self.folder.name) / "bad.zip"
        with ZipFile(archive, "w") as bad:
            bad.writestr("my-library/art/../../escape.png", b"x")
            bad.writestr("elsewhere/art/picture.png", b"x")
            bad.writestr("my-library/art/fake.png", b"not an image")
            bad.writestr("my-library/cards/broken.occard", b"not a card")
            bad.writestr("my-library/messages.json", b"{not json")
        library = MyLibrary(self.root)
        self.assertEqual(library.import_zip(archive), {"pictures": 0, "cards": 0, "messages": 0})
        self.assertFalse((Path(self.folder.name) / "escape.png").exists())
        self.assertTrue(library.is_empty())


class SettingsTests(unittest.TestCase):
    def test_remembered_library_is_used_until_it_disappears(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"OPENCARDSHOP_HOME": folder}):
            cd = Path(folder) / "cd"
            cd.mkdir()
            (cd / "CARDSHOP.INI").write_text("[OCCASIONS]\n")
            program = Path(folder) / "program"
            with patch.object(paths, "ROOT", program):
                paths.save_settings(library=str(cd))
                self.assertEqual(paths.default_library(), (cd, None))
                (cd / "CARDSHOP.INI").unlink()
                self.assertEqual(paths.default_library(), (program / "assets/original", program / "assets/rendered"))

    def test_corrupt_settings_are_ignored_and_replaced(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"OPENCARDSHOP_HOME": folder}):
            (Path(folder) / "config").mkdir()
            (Path(folder) / "config/settings.json").write_text("{broken")
            self.assertEqual(paths.load_settings(), {})
            paths.save_settings(paper="A4")
            self.assertEqual(paths.load_settings(), {"paper": "A4"})


if __name__ == "__main__":
    unittest.main()
