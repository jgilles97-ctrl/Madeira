import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("huniecam_failure_capsule", TOOLS / "huniecam_failure_capsule.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_failure_capsule"] = mod
SPEC.loader.exec_module(mod)


class HunieCamFailureCapsuleTests(unittest.TestCase):
    def test_jit_prerequisite_wins_priority(self):
        text = "\n".join([
            "start",
            "c0000005 later-looking crash",
            "[jit-debugger] attached=0 at the pool request",
            "end",
        ])
        report = mod.extract(text, before=1, after=1)
        self.assertTrue(report["found"])
        self.assertEqual(report["signature"], "jit_missing")
        self.assertTrue(report["source_log_sha256"])

    def test_breakpoint_is_separate_from_generic_store(self):
        text = "[store-undecoded] #1 insn=0xd4200000 pc=0x123 addr=0x456\n"
        report = mod.extract(text)
        self.assertEqual(report["signature"], "guest_breakpoint")

    def test_excerpt_redacts_user_path_but_preserves_instruction(self):
        text = "before /Users/joey/secret/file\n[store-undecoded] insn=0xa9882149 pc=0x123\nafter\n"
        report = mod.extract(text, before=1, after=1)
        joined = "\n".join(report["excerpt"])
        self.assertNotIn("/Users/joey/", joined)
        self.assertIn("0xa9882149", joined)
        self.assertIn("0x123", joined)

    def test_no_known_failure_stays_unknown(self):
        report = mod.extract("normal startup\nscene loaded\n")
        self.assertFalse(report["found"])
        self.assertIsNone(report["signature"])


if __name__ == "__main__":
    unittest.main()
