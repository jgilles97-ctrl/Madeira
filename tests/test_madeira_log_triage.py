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
        self.assertEqual(report["severity_counts"]["HIGH"], 2)
        self.assertEqual(report["severity_counts"]["MEDIUM"], 1)

    def test_positive_jit_signal_does_not_create_failure(self):
        report = mod.triage_text("[jit-debugger] attached=1 at the pool request\ncube-x64 clean\n")
        self.assertEqual(report["finding_count"], 0)
        codes = {p["code"] for p in report["positive_signals"]}
        self.assertIn("jit_debugger_attached_at_pool_request", codes)
        self.assertIn("clean_x64_probe", codes)

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
        finding = report["findings"][0]
        self.assertEqual(finding["count"], 8)
        self.assertEqual(len(finding["samples"]), 3)

    def test_no_known_marker(self):
        report = mod.triage_text("ordinary startup line\nanother ordinary line\n")
        self.assertEqual(report["finding_count"], 0)
        self.assertEqual(report["line_count"], 2)


    def test_foreign_mapping_access_violation_is_correlated(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "guest RIP=0x71fc88cc85",
                    "process terminated with c0000005",
                    "Wine doesn't own this addr (FEX/foreign mmap)",
                    "fault=0x785623f160",
                ]
            )
        )
        correlations = report["crash_correlations"]
        self.assertEqual(len(correlations), 1)
        self.assertEqual(correlations[0]["guest_rip"], "0x71fc88cc85")
        self.assertEqual(correlations[0]["fault_address"], "0x785623f160")
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("windows_access_violation", codes)
        self.assertIn("foreign_mapping_access_violation", codes)

    def test_curly_apostrophe_foreign_mapping_boundary_is_matched(self):
        report = mod.triage_text("c0000005\nWine doesn’t own this addr\n")
        self.assertEqual(len(report["crash_correlations"]), 1)

    def test_isolated_or_distant_access_violation_is_not_correlated(self):
        isolated = mod.triage_text("c0000005\nordinary line\n")
        self.assertEqual(isolated["crash_correlations"], [])

        distant = mod.triage_text("c0000005\n" + "\n".join(["ordinary"] * 13) + "\nforeign mmap\n")
        self.assertEqual(distant["crash_correlations"], [])

    def test_unity_text_failures_are_narrowly_classified(self):
        report = mod.triage_text(
            "TMP_FontAsset missing fallback font asset\n"
            "Shader Hidden/InternalErrorShader is not supported\n"
        )
        finding = next(f for f in report["findings"] if f["code"] == "unity_text_rendering_failure")
        self.assertEqual(finding["count"], 2)

        ordinary = mod.triage_text("UI text is invisible after pressing Start\n")
        self.assertNotIn(
            "unity_text_rendering_failure", {f["code"] for f in ordinary["findings"]}
        )

    def test_correlated_context_is_redacted(self):
        report = mod.triage_text(
            "guest RIP=0x1 path=/Users/joey/private token=topsecret\n"
            "c0000005\n"
            "Wine doesn't own this addr\n"
            "fault=0x2\n"
        )
        context = "\n".join(item["text"] for item in report["crash_correlations"][0]["context"])
        self.assertNotIn("/Users/joey", context)
        self.assertNotIn("topsecret", context)
        self.assertIn("[REDACTED]", context)


if __name__ == "__main__":
    unittest.main()
