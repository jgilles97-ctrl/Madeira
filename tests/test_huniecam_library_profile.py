import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_library_profile", ROOT / "tools" / "huniecam_library_profile.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_library_profile"] = mod
SPEC.loader.exec_module(mod)


class HunieCamLibraryProfileTests(unittest.TestCase):
    def test_baseline_profile_matches_project_rules(self):
        r = mod.build("Games/HunieCam Studio/HunieCamStudio.exe")
        e = r["entry_fragment"]
        self.assertEqual(e["bits"], 32)
        self.assertEqual(e["resolution"], "1280x720")
        self.assertEqual(e["display"], "fit")
        self.assertEqual(e["fpsMode"], 1)
        self.assertEqual(e["arguments"], "")
        self.assertEqual(e["config"], "")
        self.assertEqual(e["launchMode"], "direct")
        self.assertFalse(e["touchControls"])

    def test_backslashes_are_normalized(self):
        r = mod.build(r"Games\HunieCam Studio\HunieCamStudio.exe")
        self.assertEqual(r["entry_fragment"]["relativePath"], "Games/HunieCam Studio/HunieCamStudio.exe")

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.build("C:/Games/HunieCam Studio/HunieCamStudio.exe")

    def test_parent_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.build("Games/../HunieCamStudio.exe")

    def test_wrong_executable_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.build("Games/HunieCam Studio/Other.exe")


if __name__ == "__main__":
    unittest.main()
