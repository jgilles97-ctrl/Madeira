from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


AUDIT = load_module("sims4_ea_prefix_audit", "tools/sims4_ea_prefix_audit.py")


class EAPrefixAuditTests(unittest.TestCase):
    def build_prefix(self, root: pathlib.Path, *, service=True, nlm=True, background_ini=True):
        prefix = root / "prefix"
        drive_c = prefix / "drive_c"
        base = drive_c / "Program Files/Electronic Arts/EA Desktop/EA Desktop"
        base.mkdir(parents=True)
        for name in AUDIT.EA_RELATIVE:
            (base / name).write_bytes((name + "\n").encode())

        system = []
        if service:
            system.append(r"[System\\CurrentControlSet\\Services\\EABackgroundService]")
        if nlm:
            system.append(r"[Software\\Classes\\CLSID\\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}\\InprocServer32]")
            system.append(r'@="C:\\windows\\system32\\netprofm.dll"')
        prefix.mkdir(parents=True, exist_ok=True)
        (prefix / "system.reg").write_text("\n".join(system), encoding="utf-8")
        (prefix / "user.reg").write_text("", encoding="utf-8")
        if background_ini:
            ini = drive_c / "ProgramData/EA Desktop/backgroundservice.ini"
            ini.parent.mkdir(parents=True)
            ini.write_text("pid=4242\n", encoding="utf-8")
        return prefix

    def test_ready_prefix_requires_device_canary_next(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = self.build_prefix(pathlib.Path(td))
            report = AUDIT.audit(prefix)
            self.assertTrue(report["static_ready"])
            self.assertEqual(report["next_gate"], "RUN_SIM4_LAUNCHER_CANARY_ON_IPAD")
            self.assertTrue(report["registry"]["ea_background_service_registered"])
            self.assertTrue(report["registry"]["network_list_manager_registered"])
            self.assertEqual(report["physical_device_success"], "UNPROVEN")

    def test_background_ini_is_not_declared_stale_from_static_presence(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = self.build_prefix(pathlib.Path(td), background_ini=True)
            report = AUDIT.audit(prefix)
            ini = report["backgroundservice_ini"]
            self.assertTrue(ini["present"])
            self.assertEqual(ini["pid_candidates"], [4242])
            self.assertEqual(ini["stale_state"], "UNKNOWN_UNTIL_SERVICE_STATUS_IS_QUERIED_ON_DEVICE")

    def test_missing_ea_component_blocks_static_gate(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = self.build_prefix(pathlib.Path(td))
            target = prefix / "drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EACefSubProcess.exe"
            target.unlink()
            report = AUDIT.audit(prefix)
            self.assertFalse(report["static_ready"])
            self.assertIn("EACefSubProcess.exe", report["missing_components"])
            self.assertIn("EA_COMPONENTS_MISSING", report["blockers"])

    def test_missing_service_registration_blocks_when_system_reg_exists(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = self.build_prefix(pathlib.Path(td), service=False)
            report = AUDIT.audit(prefix)
            self.assertFalse(report["static_ready"])
            self.assertIn("EA_BACKGROUND_SERVICE_NOT_REGISTERED", report["blockers"])


if __name__ == "__main__":
    unittest.main()
