import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_performance", ROOT / "tools" / "huniecam_performance.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_performance"] = mod
SPEC.loader.exec_module(mod)


class HunieCamPerformanceTests(unittest.TestCase):
    def test_clean_samples_are_comparable(self):
        text = "\n".join([
            "fps=60",
            "fps=58",
            "fps=61",
            "frame_ms=16.7",
            "frame_ms=17.2",
            "[device-load] thermal=nominal low-power=0 capture=0",
        ])
        report = mod.analyze(text)
        self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_PERFORMANCE_V2")
        self.assertEqual(report["fps"]["samples"], 3)
        self.assertTrue(report["fps_cap"]["effective"])
        self.assertTrue(report["comparison_clean"])
        self.assertFalse(report["runaway_fps_signal"])

    def test_thermal_pressure_blocks_clean_comparison(self):
        text = "fps=45\nfps=45\nfps=46\n[device-load] thermal=serious low-power=0 capture=0\n"
        report = mod.analyze(text)
        self.assertFalse(report["comparison_clean"])
        self.assertTrue(any("thermal" in w.lower() for w in report["warnings"]))

    def test_low_power_blocks_clean_comparison(self):
        text = "fps=60\nfps=60\nfps=60\n[device-load] thermal=nominal low-power=1 capture=0\n"
        self.assertFalse(mod.analyze(text)["comparison_clean"])

    def test_runaway_fps_is_flagged(self):
        text = "fps=60\nfps=144\nfps=144\n[device-load] thermal=nominal low-power=0 capture=0\n"
        report = mod.analyze(text)
        self.assertTrue(report["runaway_fps_signal"])
        self.assertFalse(report["fps_cap"]["effective"])
        self.assertFalse(report["comparison_clean"])

    def test_sustained_90fps_rejects_claimed_60fps_baseline(self):
        text = "fps=90\nfps=91\nfps=89\n[device-load] thermal=nominal low-power=0 capture=0\n"
        report = mod.analyze(text, expected_fps=60)
        self.assertFalse(report["fps_cap"]["effective"])
        self.assertFalse(report["comparison_clean"])
        self.assertTrue(any("intended 60 FPS cap" in w for w in report["warnings"]))

    def test_intentional_uncapped_diagnostic_does_not_require_cap(self):
        text = "fps=90\n[device-load] thermal=nominal low-power=0 capture=0\n"
        report = mod.analyze(text, expected_fps=None)
        self.assertTrue(report["comparison_clean"])
        self.assertIsNone(report["fps_cap"]["expected"])

    def test_missing_samples_stays_unproven(self):
        report = mod.analyze("Unity started")
        self.assertEqual(report["fps"]["samples"], 0)
        self.assertFalse(report["comparison_clean"])
        self.assertTrue(report["warnings"])


if __name__ == "__main__":
    unittest.main()
