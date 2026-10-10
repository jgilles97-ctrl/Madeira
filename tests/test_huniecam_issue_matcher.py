import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_issue_matcher", ROOT / "tools" / "huniecam_issue_matcher.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_issue_matcher"] = mod
SPEC.loader.exec_module(mod)


class HunieCamIssueMatcherTests(unittest.TestCase):
    def test_issue_123_requires_store_and_mono_signal(self):
        text = "HunieCamStudio_Data\\Mono\\mono.dll\n[store-undecoded] insn=0xa9882149\n"
        r = mod.match(text)
        self.assertEqual(r["best_match"]["issue"], 123)

    def test_breakpoint_writecopy_prefers_issue_173(self):
        text = "[wr-strip-declined] SEC_IMAGE WRITECOPY\n[store-undecoded] insn=0xd4200000\n"
        r = mod.match(text)
        self.assertEqual(r["best_match"]["issue"], 173)

    def test_metal_language_matches_issue_121(self):
        r = mod.match("Metal library language version 4.1 is not supported")
        self.assertEqual(r["best_match"]["issue"], 121)

    def test_sse2_message_matches_issue_116(self):
        r = mod.match("CPU Error: SSE2 is not supported")
        self.assertEqual(r["best_match"]["issue"], 116)

    def test_mono_preflight_excludes_il2cpp_workarounds(self):
        preflight = {"runtime_signals": {"mono_runtime_found": True, "gameassembly_found": False}}
        r = mod.match("", preflight)
        nums = {e["issue"] for e in r["explicit_nonmatches"]}
        self.assertEqual(nums, {230, 232})

    def test_controller_issue_is_low_relevance(self):
        r = mod.match('RoGetActivationFactory "Windows.Gaming.Input.Gamepad"')
        self.assertEqual(r["best_match"]["issue"], 90)
        self.assertEqual(r["best_match"]["relevance"], "low")


if __name__ == "__main__":
    unittest.main()
