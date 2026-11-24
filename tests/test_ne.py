"""Check independently useful evidence from the supplied original executable."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import struct
import unittest

from opencardshop.formats import FormatError
from opencardshop.ne import inspect_ne

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets/original/CARDSHOP.EXE"


@unittest.skipUnless(EXE.is_file(), "Needs CARDSHOP.EXE from the asset pack or your CD in assets/original")
class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = inspect_ne(EXE)

    def test_actual_executable_identity_and_runtime_dependencies(self):
        report = self.report
        self.assertEqual(report["size_bytes"], 247472)
        self.assertEqual(report["sha256"], "2570a011ab396be084927c71e67d49bb8b38515e0ed9466fcbca5b81945205e0")
        self.assertEqual(report["target_os"], 2)
        self.assertEqual(report["expected_windows_version"], "3.10")
        self.assertEqual(report["imports"], ["LZEXPAND", "KERNEL", "GDI", "USER", "KEYBOARD", "WIN87EM", "COMMDLG", "SHELL"])
        self.assertEqual(len(report["segments"]), 7)
        self.assertEqual(len(report["imported_functions"]), 290)
        self.assertIn({"module": "GDI", "ordinal": 123}, report["imported_functions"])
        self.assertIn({"module": "LZEXPAND", "name": "LZREAD"}, report["imported_functions"])

    def test_all_original_dialogs_menu_and_strings_decode(self):
        self.assertEqual(self.report["resource_errors"], [])
        self.assertEqual(len(self.report["resources"]), 61)
        self.assertEqual(self.report["resource_counts"]["dialog"], 19)
        self.assertEqual(self.report["resource_counts"]["string_table"], 19)
        menu = next(item["menu"] for item in self.report["resources"] if "menu" in item)
        self.assertEqual(menu["item_count"], 45)
        strings = {key: value for item in self.report["resources"] for key, value in item.get("strings", {}).items()}
        self.assertEqual(len(strings), 119)
        self.assertEqual(strings["61216"], "<sender>")
        self.assertEqual(strings["61217"], "<receiver>")

    def test_two_fold_guides_and_original_full_save_are_present(self):
        dialogs = {item["id"]: item["dialog"] for item in self.report["resources"] if "dialog" in item}
        for identifier in (194, 196):
            labels = " ".join(str(control["text"]) for control in dialogs[identifier]["controls"])
            self.assertIn("first", labels)
            self.assertIn("second", labels)
        self.assertIn("&Full Save", [c["text"] for c in dialogs[205]["controls"]])
        self.assertIn("THREED.VBX;SSCommand;", [c["text"] for c in dialogs[101]["controls"]])

    def test_conflicting_version_identifiers_are_retained(self):
        version = next(item["version"] for item in self.report["resources"] if "version" in item)
        self.assertEqual(version["file_version"], [1, 2, 0, 1])
        def values(node):
            if "value" in node:
                yield node["key"], node["value"]
            for child in node["children"]:
                yield from values(child)
        self.assertEqual(dict(values(version))["FileVersion"], "1.2.001")
        about = next(i["dialog"] for i in self.report["resources"] if i["type"] == 5 and i["id"] == 100)
        self.assertIn("CardShop Plus! Version 1.5", [c["text"] for c in about["controls"]])

    def test_resource_extraction_matches_source_bytes_and_does_not_modify_exe(self):
        before = EXE.read_bytes()
        with TemporaryDirectory() as folder:
            report = inspect_ne(EXE, folder)
            for n, resource in enumerate(report["resources"], 1):
                extracted = (Path(folder) / f"resource_{n:03d}.bin").read_bytes()
                self.assertEqual(hashlib.sha256(extracted).hexdigest(), resource["sha256"])
                start = resource["file_offset"]
                self.assertEqual(extracted, before[start:start + resource["size"]])
        self.assertEqual(EXE.read_bytes(), before)

    def test_truncation_and_corrupt_offsets_fail_without_execution(self):
        original = EXE.read_bytes()
        shifted = bytearray(original)
        struct.pack_into("<I", shifted, 0x3C, len(original) - 2)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "bad.exe"
            for contents in (b"MZ", original[:130], original[:500], bytes(shifted)):
                with self.subTest(length=len(contents)):
                    path.write_bytes(contents)
                    with self.assertRaises(FormatError):
                        inspect_ne(path)


if __name__ == "__main__":
    unittest.main()
