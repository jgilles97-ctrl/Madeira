import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_input_path_audit", ROOT / "tools" / "huniecam_input_path_audit.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_input_path_audit"] = mod
SPEC.loader.exec_module(mod)


class HunieCamInputPathAuditTests(unittest.TestCase):
    def test_real_branch_source_has_complete_drag_release_transport(self):
        report = mod.audit(ROOT)
        self.assertTrue(report["passed"], report["errors"])
        self.assertTrue(report["proven_by_source"]["touch_drag_posts_button_down"])
        self.assertTrue(report["proven_by_source"]["touch_drag_posts_motion"])
        self.assertTrue(report["proven_by_source"]["touch_lift_posts_left_button_up"])
        self.assertIn("physical iPad", report["not_proven"])

    def test_missing_windows_leftup_is_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in mod.FILES.values():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / mod.FILES["swift"]).write_text("""
                func tmCommitDrag() { winios_post_touch_down(1,2) }
                func touchModeMoved() { winios_post_touch_move(1,2) }
                func touchModeEnded() { winios_post_touch_up(1,2) }
                func touchModeCancelled() { winios_post_touch_up(1,2) }
            """)
            # Deliberately wrong: move only, no MOUSEEVENTF_LEFTUP.
            (root / mod.FILES["bridge"]).write_text("""
                void winios_post_touch_up(int x, int y) {
                    winios_q_push_ev(WINIOS_EV_MOUSE, x, y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0);
                }
                void drain(void) { winios_drv_post_mouse(e.x, e.y, e.flags, e.data, NULL); }
            """)
            (root / mod.FILES["driver"]).write_text("""
                void post(void) { input.mi.dwFlags = flags; send_hardware_message(NULL, 0, &input, 0); }
            """)
            report = mod.audit(root)
            self.assertFalse(report["passed"])
            self.assertFalse(report["proven_by_source"]["touch_lift_posts_left_button_up"])
            self.assertTrue(any("bridge_up_is_leftup_absolute" in x for x in report["errors"]))

    def test_missing_source_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = mod.audit(pathlib.Path(tmp))
            self.assertFalse(report["passed"])
            self.assertTrue(any("source is missing" in x for x in report["errors"]))


if __name__ == "__main__":
    unittest.main()
