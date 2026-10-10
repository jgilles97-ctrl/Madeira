import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "madeira_log_triage", ROOT / "tools" / "madeira_log_triage.py"
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["madeira_log_triage"] = mod
SPEC.loader.exec_module(mod)


class MadeiraLogTriageTests(unittest.TestCase):
    def codes(self, text):
        return {f["code"] for f in mod.triage_text(text)["findings"]}

    def test_high_signal_markers_are_classified(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "[jit-debugger] attached=0 at the pool request",
                    "0068: NtTerminateProcess(... c0000005)",
                    "slot275=0x0 while teb_key_val=0xfbffd0000",
                    'UnexpectedResponse ("expected integer PID in launch app response")',
                    "Steam launch refusal 29 (invalid platform)",
                ]
            )
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertEqual(
            codes,
            {
                "jit_debugger_missing_at_pool_request",
                "windows_access_violation",
                "teb_tsd_regression",
                "stikdebug_pid_protocol_error",
                "steam_invalid_platform_29",
            },
        )
        self.assertEqual(report["severity_counts"]["CRITICAL"], 2)

    def test_huniecam_relevant_runtime_markers(self):
        codes = self.codes(
            "\n".join(
                [
                    "[store-undecoded] #1 insn=0x880cfd0b pc=0x123 addr=0x456 rw_addr=0x789",
                    "[wow-window] refused: map too small",
                    'err: Failed to create internal command library: This library is using language version 4.1 which is not supported on this OS.',
                    '0024:err:module:import_dll Library VCRUNTIME140.dll (which is needed by L"Z:\\game.exe") not found',
                ]
            )
        )
        self.assertEqual(
            codes,
            {
                "store_undecoded",
                "wow_window_refused_small_map",
                "metal_language_version_unsupported",
                "missing_import_dll",
            },
        )

    def test_positive_signals_do_not_create_failures(self):
        report = mod.triage_text(
            "[jit-debugger] attached=1 at the pool request\n"
            "cube-x64 clean\n"
            "[WineProc] Target exe: HunieCamStudio.exe (bundle=i386-windows)\n"
        )
        self.assertEqual(report["finding_count"], 0)
        codes = {p["code"] for p in report["positive_signals"]}
        self.assertIn("jit_debugger_attached_at_pool_request", codes)
        self.assertIn("clean_x64_probe", codes)
        self.assertIn("wine_process_started", codes)

    def test_samples_redact_local_paths_and_tokens(self):
        report = mod.triage_text(
            "c0000005 path=/var/mobile/Containers/Data/Application/ABCDEF12-3456-7890-ABCD-EF1234567890/Documents "
            "token=supersecret /Users/joey/project\n"
        )
        sample = report["findings"][0]["samples"][0]["text"]
        self.assertNotIn("supersecret", sample)
        self.assertNotIn("/Users/joey", sample)
        self.assertIn("[REDACTED]", sample)

    def test_duplicate_lines_count_but_samples_are_bounded(self):
        report = mod.triage_text("\n".join(["c0000005"] * 8))
        finding = next(f for f in report["findings"] if f["code"] == "windows_access_violation")
        self.assertEqual(finding["count"], 8)
        self.assertEqual(len(finding["samples"]), 3)

    def test_no_known_marker(self):
        report = mod.triage_text("ordinary startup line\nanother ordinary line\n")
        self.assertEqual(report["finding_count"], 0)
        self.assertEqual(report["line_count"], 2)


if __name__ == "__main__":
    unittest.main()
