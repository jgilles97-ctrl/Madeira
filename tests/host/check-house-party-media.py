#!/usr/bin/env python3
"""Source-level guard for the opt-in 64-bit Madeira media path."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
script = root / "build/wine-pe/build-winegstreamer.sh"
text = script.read_text()
media = (root / "docs/MEDIA.md").read_text()
pbx = (root / "app/Madeira.xcodeproj/project.pbxproj").read_text()
library = (root / "app/Madeira/Library.swift").read_text()

subprocess.run(["bash", "-n", str(script)], check=True)
assert "--enable-winegstreamer" in text
assert "dlls/winegstreamer/arm64ec-windows/winegstreamer.dll" in text
assert 'app/Madeira/arm64ec-windows/winegstreamer.dll' in text
assert "MADEIRA_WG_64BIT = 1" in text
assert "build/wine-pe/build-winegstreamer.sh" in media
assert "MADEIRA_WG_64BIT" in media
assert "arm64ec-windows in Resources" in pbx
assert "var media64Bit: Bool?" in library
assert 'setenv("MADEIRA_WG_64BIT", (media64Bit ?? configuredMedia64) ? "1" : "0", 1)' in library
assert 'Toggle("64-bit media bridge (experimental)"' in library
assert "if entry.bits == 64" in library

print("PASS: 64-bit winegstreamer build/package path is guarded and exposed as an x64 per-game opt-in")
