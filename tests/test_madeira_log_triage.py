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

    def test_detroit_moltenvk_shader_signatures_are_classified(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "program_source:773:47: error: automatic variable qualified with an address space",
                    "program_source:298:295: error: 'buffer' attribute parameter is out of bounds: must be between 0 and 30",
                    "Blending is enabled for render target 0; however, the pixelformat MTLPixelFormatR32Uint for this render target is not blendable.",
                    "output of type float4 is not compatible with a MTLPixelFormatR32Uint color attachment.",
                    "[mvk-error] VK_ERROR_DEVICE_LOST: MTLCommandBuffer execution failed",
                    "[mvk-error] VK_ERROR_OUT_OF_DEVICE_MEMORY: kIOGPUCommandBufferCallbackErrorOutOfMemory",
                ]
            )
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertTrue(
            {
                "moltenvk_shader_address_space_compile",
                "metal_buffer_index_limit",
                "detroit_r32uint_blend_validation",
                "detroit_r32uint_output_mismatch",
                "moltenvk_device_lost",
                "moltenvk_gpu_memory_failure",
            }.issubset(codes)
        )
        self.assertGreaterEqual(report["severity_counts"]["HIGH"], 6)

    def test_argument_buffer_limit_guidance_does_not_recommend_bad_workaround(self):
        report = mod.triage_text(
            "error: 'buffer' attribute parameter is out of bounds: must be between 0 and 30\n"
        )
        finding = next(f for f in report["findings"] if f["code"] == "metal_buffer_index_limit")
        self.assertIn("Do not use MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0", finding["guidance"])
        self.assertIn("argument-buffer path", finding["guidance"])

        ordinary = mod.triage_text("binding buffer index 29 succeeded\n")
        self.assertNotIn("metal_buffer_index_limit", {f["code"] for f in ordinary["findings"]})

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
        self.assertFalse(report["detroit_device_gate"]["detected"])

    def test_detroit_device_gate_full_pass_is_strict_positive_proof(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "ARCH=x86_64-windows",
                    "GATE_BEGIN=vulkan-device",
                    "GATE_CHILD_EXIT=vulkan-device:0x00000000",
                    "GATE_RESULT=vulkan-device:PASS",
                    "GATE_BEGIN=win32-surface",
                    "GATE_CHILD_EXIT=win32-surface:0x00000000",
                    "GATE_RESULT=win32-surface:PASS",
                    "GATE_BEGIN=present-120",
                    "FRAME_30",
                    "FRAME_60",
                    "FRAME_90",
                    "FRAME_120",
                    "GATE_CHILD_EXIT=present-120:0x00000000",
                    "GATE_RESULT=present-120:PASS",
                    "VULKAN_DEVICE=PASS",
                    "WIN32_SURFACE=PASS",
                    "PRESENTED_120_FRAMES=PASS",
                    "FOREGROUND_INTEGRITY=PASS",
                    "OVERALL=PASS",
                    "NEXT_GATE=detroit-process-and-shader-compilation",
                ]
            )
        )
        gate = report["detroit_device_gate"]
        self.assertTrue(gate["detected"])
        self.assertEqual(gate["overall"], "PASS")
        self.assertTrue(gate["proof_complete"])
        self.assertEqual(gate["final_markers"]["foreground_integrity"], "PASS")
        self.assertEqual([s["status"] for s in gate["stages"]], ["PASS", "PASS", "PASS"])
        codes = {p["code"] for p in report["positive_signals"]}
        self.assertIn("detroit_device_gate_passed", codes)
        self.assertNotIn("detroit_device_gate_incomplete", {f["code"] for f in report["findings"]})

    def test_detroit_device_gate_pass_without_foreground_marker_is_incomplete(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_RESULT=vulkan-device:PASS",
                    "GATE_RESULT=win32-surface:PASS",
                    "GATE_RESULT=present-120:PASS",
                    "VULKAN_DEVICE=PASS",
                    "WIN32_SURFACE=PASS",
                    "PRESENTED_120_FRAMES=PASS",
                    "OVERALL=PASS",
                ]
            )
        )
        self.assertFalse(report["detroit_device_gate"]["proof_complete"])
        self.assertIn("detroit_device_gate_incomplete", {f["code"] for f in report["findings"]})

    def test_detroit_device_gate_foreground_failure_is_actionable(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_RESULT=vulkan-device:PASS",
                    "GATE_RESULT=win32-surface:PASS",
                    "GATE_RESULT=present-120:PASS",
                    "VULKAN_DEVICE=PASS",
                    "WIN32_SURFACE=PASS",
                    "PRESENTED_120_FRAMES=PASS",
                    "FOREGROUND_INTEGRITY=FAIL",
                    "OVERALL=FAIL",
                    "FAILED_GATE=foreground-integrity",
                    "PROOF_RESULT=NOT_WRITTEN",
                ]
            )
        )
        finding = next(f for f in report["findings"] if f["code"] == "detroit_device_gate_failed")
        self.assertIn("keep Madeira visible", finding["guidance"])
        self.assertEqual(report["detroit_device_gate"]["failed_gate"], "foreground-integrity")

    def test_detroit_device_gate_failure_is_localized(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_BEGIN=vulkan-device",
                    "GATE_CHILD_EXIT=vulkan-device:0x00000000",
                    "GATE_RESULT=vulkan-device:PASS",
                    "GATE_BEGIN=win32-surface",
                    "GATE_ERROR=CreateProcessA:126",
                    "GATE_RESULT=win32-surface:FAIL",
                    "OVERALL=FAIL",
                    "FAILED_GATE=win32-surface",
                    "GATE_RESULT=present-120:SKIP",
                    "NEXT_ACTION=fix-this-gate-before-launching-Detroit",
                ]
            )
        )
        gate = report["detroit_device_gate"]
        self.assertEqual(gate["overall"], "FAIL")
        self.assertFalse(gate["proof_complete"])
        self.assertEqual(gate["failed_gate"], "win32-surface")
        self.assertEqual(gate["stages"][1]["error"], "CreateProcessA:126")
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("detroit_device_gate_failed", codes)
        finding = next(f for f in report["findings"] if f["code"] == "detroit_device_gate_failed")
        self.assertIn("CAMetalLayer", finding["guidance"])

    def test_detroit_device_gate_incomplete_cannot_be_false_pass(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_BEGIN=vulkan-device",
                    "GATE_RESULT=vulkan-device:PASS",
                    "VULKAN_DEVICE=PASS",
                    "OVERALL=PASS",
                ]
            )
        )
        gate = report["detroit_device_gate"]
        self.assertEqual(gate["overall"], "PASS")
        self.assertFalse(gate["proof_complete"])
        self.assertIn("detroit_device_gate_incomplete", {f["code"] for f in report["findings"]})

    def test_newest_detroit_gate_attempt_wins_over_stale_pass(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_RESULT=vulkan-device:PASS",
                    "GATE_RESULT=win32-surface:PASS",
                    "GATE_RESULT=present-120:PASS",
                    "VULKAN_DEVICE=PASS",
                    "WIN32_SURFACE=PASS",
                    "PRESENTED_120_FRAMES=PASS",
                    "FOREGROUND_INTEGRITY=PASS",
                    "OVERALL=PASS",
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_BEGIN=vulkan-device",
                    "GATE_ERROR=TIMEOUT_MS:60000",
                    "GATE_RESULT=vulkan-device:FAIL",
                    "OVERALL=FAIL",
                    "FAILED_GATE=vulkan-device",
                    "GATE_RESULT=win32-surface:SKIP",
                    "GATE_RESULT=present-120:SKIP",
                ]
            )
        )
        gate = report["detroit_device_gate"]
        self.assertEqual(gate["overall"], "FAIL")
        self.assertEqual(gate["failed_gate"], "vulkan-device")
        self.assertFalse(gate["proof_complete"])

    def test_rendered_gate_summary_is_plain_and_actionable(self):
        report = mod.triage_text(
            "\n".join(
                [
                    "SCHEMA=MADEIRA_DETROIT_DEVICE_GATE_V1",
                    "GATE_BEGIN=present-120",
                    "GATE_ERROR=TIMEOUT_MS:180000",
                    "GATE_RESULT=present-120:FAIL",
                    "OVERALL=FAIL",
                    "FAILED_GATE=present-120",
                ]
            )
        )
        rendered = mod.render_text(report, pathlib.Path("madeira-log.txt"))
        self.assertIn("Detroit physical-device Vulkan gate", rendered)
        self.assertIn("Overall: **FAIL**", rendered)
        self.assertIn("present-120: FAIL", rendered)
        self.assertIn("TIMEOUT_MS:180000", rendered)
        self.assertIn("Foreground integrity: NOT_REPORTED", rendered)
        self.assertIn("do not count this as Detroit-ready graphics yet", rendered)


if __name__ == "__main__":
    unittest.main()
