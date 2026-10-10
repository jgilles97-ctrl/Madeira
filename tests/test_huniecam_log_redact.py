import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_log_redact", ROOT / "tools" / "huniecam_log_redact.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_log_redact"] = mod
SPEC.loader.exec_module(mod)


class HunieCamLogRedactTests(unittest.TestCase):
    def test_credentials_and_user_paths_are_redacted(self):
        text = "/Users/joey/Library/foo access_token=SECRET person@example.com C:\\users\\joey\\save\n"
        out, report = mod.redact(text)
        self.assertNotIn("SECRET", out)
        self.assertNotIn("person@example.com", out)
        self.assertNotIn("/Users/joey/", out)
        self.assertNotIn("C:\\users\\joey", out)
        self.assertGreaterEqual(report["total_replacements"], 4)

    def test_runtime_evidence_is_preserved(self):
        text = "[store-undecoded] insn=0xd4200000 pc=0x1480d4408 status=c0000005 ntdll.dll+0x28408\n"
        out, report = mod.redact(text)
        self.assertEqual(out, text)
        self.assertEqual(report["total_replacements"], 0)

    def test_bearer_and_pairing_values_are_redacted(self):
        text = "Authorization: Bearer abc.def.ghi pairing_secret=xyz123\n"
        out, _ = mod.redact(text)
        self.assertNotIn("abc.def.ghi", out)
        self.assertNotIn("xyz123", out)


if __name__ == "__main__":
    unittest.main()
