from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CEF = load_module("sims4_ea_cef_roles", "tools/sims4_ea_cef_roles.py")


class EACefRoleTests(unittest.TestCase):
    def test_classifies_gpu_renderer_and_network_service(self):
        report = CEF.classify(
            'EACefSubProcess.exe --type=gpu-process pid=101\n'
            'EACefSubProcess.exe --type=renderer pid=102\n'
            'EACefSubProcess.exe --type=utility --utility-sub-type=network.mojom.NetworkService pid=103\n'
        )
        self.assertEqual(report["role_counts"]["gpu-process"], 1)
        self.assertEqual(report["role_counts"]["renderer"], 1)
        self.assertEqual(report["role_counts"]["utility"], 1)
        self.assertEqual(report["utility_sub_type_counts"]["network.mojom.networkservice"], 1)
        self.assertTrue(report["role_coverage"]["gpu_process_seen"])
        self.assertTrue(report["role_coverage"]["renderer_seen"])
        self.assertTrue(report["role_coverage"]["network_service_seen"])
        self.assertEqual(report["next_gate"], "CORRELATE_EA_CEF_ROLES_WITH_WINDOW_AND_TS4_START")
        self.assertEqual(report["physical_device_success"], "UNPROVEN")

    def test_role_specific_failure_becomes_role_specific_gate(self):
        report = CEF.classify(
            'EACefSubProcess.exe --type=gpu-process pid=201 GPU process failed\n'
        )
        self.assertEqual(report["fatal_by_role"]["gpu-process"], 1)
        self.assertEqual(report["next_gate"], "ISOLATE_EA_CEF_GPU_PROCESS_FAILURE")

    def test_missing_command_lines_asks_for_capture(self):
        report = CEF.classify("EA App started but no helper command lines were logged\n")
        self.assertEqual(report["helper_line_count"], 0)
        self.assertEqual(report["next_gate"], "CAPTURE_EA_CEF_COMMAND_LINES")

    def test_partial_roles_do_not_claim_cef_ready(self):
        report = CEF.classify('EACefSubProcess.exe --type=renderer pid=301\n')
        self.assertEqual(report["next_gate"], "CAPTURE_MISSING_EA_CEF_ROLES")
        self.assertFalse(report["role_coverage"]["gpu_process_seen"])
        self.assertFalse(report["role_coverage"]["network_service_seen"])

    def test_quoted_role_arguments_are_supported(self):
        report = CEF.classify(
            'EACefSubProcess.exe --type="utility" --utility-sub-type="network.mojom.NetworkService"\n'
        )
        self.assertEqual(report["role_counts"]["utility"], 1)
        self.assertTrue(report["role_coverage"]["network_service_seen"])

    def test_678_role_classification_passes(self):
        cases = (
            ('EACefSubProcess.exe --type=gpu-process GPU process failed\n', "ISOLATE_EA_CEF_GPU_PROCESS_FAILURE"),
            ('EACefSubProcess.exe --type=renderer access violation c0000005\n', "ISOLATE_EA_CEF_RENDERER_FAILURE"),
            ('EACefSubProcess.exe --type=utility --utility-sub-type=network.mojom.NetworkService fatal\n', "ISOLATE_EA_CEF_UTILITY_FAILURE"),
            ('EACefSubProcess.exe --type=renderer\n', "CAPTURE_MISSING_EA_CEF_ROLES"),
            ('no cef command line\n', "CAPTURE_EA_CEF_COMMAND_LINES"),
        )
        for iteration in range(678):
            text, expected = cases[iteration % len(cases)]
            report = CEF.classify(f"iteration={iteration}\n{text}")
            self.assertEqual(report["next_gate"], expected, f"iteration {iteration}")
            self.assertEqual(report["physical_device_success"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
