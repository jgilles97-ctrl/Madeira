import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "huniecam_runtime_bundle_audit", ROOT / "tools" / "huniecam_runtime_bundle_audit.py"
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_runtime_bundle_audit"] = mod
SPEC.loader.exec_module(mod)


def populate(root: pathlib.Path, *, omit: set[str] | None = None) -> None:
    omit = omit or set()
    for relative in set(mod.WOW64_REQUIRED) | set(mod.GRAPHICS_REQUIRED):
        if relative in omit:
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((relative + "\n").encode("utf-8"))


class HunieCamRuntimeBundleAuditTests(unittest.TestCase):
    def test_complete_payload_app_is_launch_ready_and_fingerprinted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            app = base / "Payload" / "Madeira.app"
            populate(app)
            report = mod.audit(base)
            self.assertTrue(report["runtime_root_found"])
            self.assertEqual(report["layout"], "payload_app")
            self.assertTrue(report["wow64_ready"])
            self.assertTrue(report["renderer_neutral_ready"])
            self.assertTrue(report["launch_ready"])
            self.assertGreater(report["i386_file_count"], 0)
            self.assertEqual(report["missing_wow64"], [])
            self.assertEqual(report["missing_graphics"], [])
            self.assertRegex(report["runtime_set_sha256"], r"^[0-9a-f]{64}$")
            for item in report["files"].values():
                self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")

    def test_runtime_fingerprint_is_deterministic_and_changes_with_xtajit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            populate(root)
            first = mod.audit(root)
            second = mod.audit(root)
            self.assertEqual(first["runtime_set_sha256"], second["runtime_set_sha256"])
            (root / "aarch64-windows" / "xtajit.dll").write_bytes(b"different-fex-build\n")
            third = mod.audit(root)
            self.assertNotEqual(first["runtime_set_sha256"], third["runtime_set_sha256"])

    def test_missing_i386_ntdll_is_hard_wow64_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = pathlib.Path(tmp) / "Madeira.app"
            populate(app, omit={"i386-windows/ntdll.dll"})
            report = mod.audit(pathlib.Path(tmp))
            self.assertFalse(report["wow64_ready"])
            self.assertFalse(report["launch_ready"])
            self.assertIsNone(report["runtime_set_sha256"])
            self.assertIn("i386-windows/ntdll.dll", report["missing_wow64"])
            self.assertTrue(any("cannot identify/run HunieCam" in e for e in report["errors"]))

    def test_missing_d3d9_fallback_keeps_wow64_ready_but_blocks_renderer_neutral_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            populate(root, omit={"i386-windows/d3d9-emulated.dll"})
            report = mod.audit(root)
            self.assertTrue(report["wow64_ready"])
            self.assertFalse(report["renderer_neutral_ready"])
            self.assertFalse(report["launch_ready"])
            self.assertIsNone(report["runtime_set_sha256"])
            self.assertIn("i386-windows/d3d9-emulated.dll", report["missing_graphics"])

    def test_source_tree_layout_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = pathlib.Path(tmp)
            populate(checkout / "app" / "Madeira")
            report = mod.audit(checkout)
            self.assertEqual(report["layout"], "source_tree")
            self.assertTrue(report["launch_ready"])
            self.assertIsNotNone(report["runtime_set_sha256"])

    def test_missing_runtime_root_fails_without_absolute_path_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = mod.audit(pathlib.Path(tmp))
            self.assertFalse(report["runtime_root_found"])
            self.assertFalse(report["launch_ready"])
            self.assertIsNone(report["runtime_set_sha256"])
            rendered = str(report)
            self.assertNotIn(tmp, rendered)
            self.assertIn("i386-windows/ntdll.dll", report["missing_wow64"])


if __name__ == "__main__":
    unittest.main()
