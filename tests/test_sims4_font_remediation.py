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


PLAN = load_module("sims4_font_remediation", "tools/sims4_font_remediation.py")


def canary(*, status="FAIL", arial=False, liberation=True, tahoma=True):
    return {
        "schema": "SIMS4_LAUNCHER_CANARY_RESULT_V1",
        "checks": {
            "dwrite-arial": {
                "status": status,
                "detail": (
                    f"arial={int(arial)} liberation_sans={int(liberation)} tahoma={int(tahoma)}"
                ),
            }
        },
        "dwrite_arial_resolution": {
            "passed": status == "PASS",
            "arial_found": arial,
            "liberation_sans_found": liberation,
            "tahoma_found": tahoma,
        },
    }


class FontRemediationTests(unittest.TestCase):
    def test_missing_arial_with_liberation_proposes_reversible_alias(self):
        result = PLAN.make_plan(canary())
        self.assertTrue(result["approved"])
        self.assertEqual(result["replacement_family"], "Liberation Sans")
        self.assertEqual(result["registry_plan"]["value_name"], "Arial")
        self.assertIn("Wine\\Fonts\\Replacements", result["registry_plan"]["reg_command"])
        self.assertIn("reg delete", result["registry_plan"]["rollback_command"])
        self.assertEqual(result["physical_device_success"], "UNPROVEN")

    def test_existing_arial_blocks_unnecessary_change(self):
        result = PLAN.make_plan(canary(status="PASS", arial=True))
        self.assertFalse(result["approved"])
        self.assertIn("ARIAL_ALREADY_RESOLVES", result["blockers"])
        self.assertIsNone(result["registry_plan"])

    def test_missing_validated_replacement_blocks_change(self):
        result = PLAN.make_plan(canary(liberation=False, tahoma=True))
        self.assertFalse(result["approved"])
        self.assertIn("NO_VALIDATED_ARIAL_REPLACEMENT_FOUND", result["blockers"])
        self.assertIsNone(result["registry_plan"])

    def test_missing_probe_blocks_change(self):
        result = PLAN.make_plan({
            "schema": "SIMS4_LAUNCHER_CANARY_RESULT_V1",
            "checks": {},
            "dwrite_arial_resolution": {},
        })
        self.assertFalse(result["approved"])
        self.assertIn("DWRITE_ARIAL_PROBE_MISSING", result["blockers"])

    def test_wrong_schema_blocks_change(self):
        value = canary()
        value["schema"] = "OLD_CANARY"
        result = PLAN.make_plan(value)
        self.assertFalse(result["approved"])
        self.assertIn("CANARY_SCHEMA_MISMATCH", result["blockers"])

    def test_678_font_planning_passes(self):
        variants = (
            (canary(), True),
            (canary(status="PASS", arial=True), False),
            (canary(liberation=False, tahoma=True), False),
            (canary(liberation=False, tahoma=False), False),
        )
        for iteration in range(678):
            source, expected = variants[iteration % len(variants)]
            result = PLAN.make_plan(source)
            self.assertEqual(result["approved"], expected, f"iteration {iteration}")
            self.assertEqual(result["physical_device_success"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
