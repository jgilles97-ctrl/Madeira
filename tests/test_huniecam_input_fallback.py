import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_input_fallback", ROOT / "tools" / "huniecam_input_fallback.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_input_fallback"] = mod
SPEC.loader.exec_module(mod)


def evidence(pointer=True):
    return {
        "schema": "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3",
        "pointer_grid": [{"point": f"p{i}", "passed": pointer} for i in range(9)],
        "drag_release_trials": [],
    }


def add_mode(data, mode, result=True, release=None):
    for i in range(3):
        rel = result if release is None else release
        data["drag_release_trials"].append({
            "trial": len(data["drag_release_trials"]) + 1,
            "input_mode": mode,
            "press_registered": True if result or rel is False else result,
            "movement_registered": True if result or rel is False else result,
            "release_registered": rel,
            "game_response_registered": result if rel is not False else False,
        })
    return data


class HunieCamInputFallbackTests(unittest.TestCase):
    def test_pointer_failure_stops_drag_tuning(self):
        report = mod.analyze(evidence(pointer=False))
        self.assertEqual(report["status"], "POINTER_MAPPING_BLOCKER")
        self.assertIsNone(report["experiment"])

    def test_direct_finger_success_keeps_clean_input(self):
        report = mod.analyze(add_mode(evidence(), "direct_finger", True))
        self.assertEqual(report["status"], "DIRECT_FINGER_DRAG_PROVEN")
        self.assertIsNone(report["experiment"])

    def test_failed_direct_finger_recommends_only_touch_pointer_next(self):
        report = mod.analyze(add_mode(evidence(), "direct_finger", False))
        self.assertEqual(report["status"], "TRY_TOUCH_POINTER_ONE_VARIABLE")
        self.assertEqual(report["experiment"]["one_variable"], "input mode")
        self.assertEqual(report["experiment"]["to"], "touch_pointer")

    def test_touch_pointer_success_becomes_touch_route(self):
        data = add_mode(evidence(), "direct_finger", False)
        add_mode(data, "touch_pointer", True)
        report = mod.analyze(data)
        self.assertEqual(report["status"], "TOUCH_POINTER_DRAG_PROVEN")

    def test_both_touch_modes_fail_then_hardware_is_diagnostic(self):
        data = add_mode(evidence(), "direct_finger", False)
        add_mode(data, "touch_pointer", False)
        report = mod.analyze(data)
        self.assertEqual(report["status"], "COMPARE_HARDWARE_POINTER")
        self.assertTrue(report["experiment"]["diagnostic_only"])

    def test_hardware_success_after_both_touch_failures_is_touch_translation_blocker(self):
        data = add_mode(evidence(), "direct_finger", False)
        add_mode(data, "touch_pointer", False)
        add_mode(data, "hardware_mouse", True)
        report = mod.analyze(data)
        self.assertEqual(report["status"], "TOUCH_TRANSLATION_BLOCKER")

    def test_hardware_failure_moves_away_from_touch_specific_patching(self):
        data = add_mode(evidence(), "direct_finger", False)
        add_mode(data, "touch_pointer", False)
        add_mode(data, "hardware_mouse", False)
        add_mode(data, "hardware_trackpad", False)
        report = mod.analyze(data)
        self.assertEqual(report["status"], "NOT_TOUCH_SPECIFIC")

    def test_release_specific_failure_with_source_path_warns_to_capture_logs_first(self):
        data = add_mode(evidence(), "direct_finger", False, release=False)
        source = {"passed": True, "proven_by_source": {"touch_lift_posts_left_button_up": True}}
        report = mod.analyze(data, source)
        self.assertTrue(report["release_specific_failure_seen"])
        self.assertTrue(report["source_release_path_proven"])
        self.assertTrue(any("post_touch_up" in x for x in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
