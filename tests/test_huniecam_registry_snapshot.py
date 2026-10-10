import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_registry_snapshot", ROOT / "tools" / "huniecam_registry_snapshot.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_registry_snapshot"] = mod
SPEC.loader.exec_module(mod)


REG = r'''
WINE REGISTRY Version 2

[Software\\HuniePot\\HunieCam Studio]
"Screenmanager Resolution Width_h182942802"=dword:00000500
"Screenmanager Resolution Height_h2627697771"=dword:000002d0
"Screenmanager Fullscreen mode_h3630240806"=dword:00000001

[Software\\OtherGame]
"secret"="not part of huniecam"
'''


class HunieCamRegistrySnapshotTests(unittest.TestCase):
    def test_extracts_only_title_section_and_hashes_values(self):
        report = mod.snapshot(REG)
        self.assertTrue(report["found"])
        self.assertEqual(report["value_count"], 3)
        self.assertFalse(report["raw_values_exposed"])
        self.assertIn("Screenmanager Resolution Width_h182942802", report["values"])
        rendered = str(report)
        self.assertNotIn("not part of huniecam", rendered)
        self.assertNotIn("00000500", rendered)

    def test_missing_section_is_clean_unknown(self):
        report = mod.snapshot('[Software\\Other]\n"x"="y"\n')
        self.assertFalse(report["found"])
        self.assertTrue(report["warnings"])

    def test_compare_reports_changed_value_name_without_value(self):
        before = mod.snapshot(REG)
        after = mod.snapshot(REG.replace("00000500", "00000640"))
        report = mod.compare(before, after)
        self.assertFalse(report["same_configuration"])
        self.assertEqual(report["changed_value_names"], ["Screenmanager Resolution Width_h182942802"])
        self.assertNotIn("00000640", str(report))

    def test_identical_snapshots_compare_equal(self):
        a = mod.snapshot(REG)
        b = mod.snapshot(REG)
        self.assertTrue(mod.compare(a, b)["same_configuration"])


if __name__ == "__main__":
    unittest.main()
