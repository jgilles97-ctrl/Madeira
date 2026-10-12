from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class LauncherCoverageTests(unittest.TestCase):
    def test_validated_launcher_modules_are_in_default_arm64ec_build(self):
        text = (ROOT / "build/wine-pe/build-modules.sh").read_text(encoding="utf-8")
        match = re.search(r'\[ \$# -gt 0 \] \|\| set -- \\\n(?P<body>.*?)(?:\n\[ -x "\$STRIP")', text, re.S)
        self.assertIsNotNone(match, "default module list not found")
        body = match.group("body")
        for module in ("netprofm", "sensapi", "avifil32", "msvfw32"):
            self.assertRegex(body, rf"\b{re.escape(module)}\b")

    def test_launcher_canary_covers_required_boundaries(self):
        text = (ROOT / "tests/x64/sims4-launcher-canary.c").read_text(encoding="utf-8")
        required = (
            "CreateProcessA",
            "OpenSCManagerW",
            "OpenServiceW",
            "EABackgroundService",
            "QueryServiceStatusEx",
            "SERVICE_STOPPED",
            "SERVICE_STOP_PENDING",
            "DWriteCreateFactory",
            "IDWriteFactory_GetSystemFontCollection",
            "IDWriteFontCollection_FindFamilyName",
            'L"Arial"',
            'L"Liberation Sans"',
            "IsNetworkAlive",
            "CLSID_NetworkListManager",
            "connect(",
            "WinHttpOpen",
            "WinHttpSendRequest",
        )
        for symbol in required:
            self.assertIn(symbol, text)

    def test_service_state_is_observed_without_blind_cleanup(self):
        text = (ROOT / "tests/x64/sims4-launcher-canary.c").read_text(encoding="utf-8")
        self.assertIn('observe("ea-service-stale-check"', text)
        self.assertNotIn("DeleteFile", text)
        self.assertNotIn("backgroundservice.ini", text)

    def test_canary_avoids_known_crashing_probe(self):
        text = (ROOT / "tests/x64/sims4-launcher-canary.c").read_text(encoding="utf-8")
        code_only = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith(("/*", "*", "//"))
        )
        self.assertNotRegex(code_only, r"\bInternetCheckConnection[AW]?\s*\(")

    def test_x64_builder_is_repo_relative_and_links_dwrite(self):
        text = (ROOT / "tests/x64/build.sh").read_text(encoding="utf-8")
        self.assertIn('REPO_ROOT="$(cd "$DIR/../.." && pwd)"', text)
        self.assertNotIn("/Users/willfaust/", text)
        self.assertIn("sims4-launcher-canary", text)
        for lib in ("-lole32", "-luuid", "-ldwrite", "-lws2_32", "-lwinhttp", "-ladvapi32"):
            self.assertIn(lib, text)


if __name__ == "__main__":
    unittest.main()
