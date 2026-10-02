#!/usr/bin/env python3
"""Static/safety guard for the local Madeira release-overlay packager."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
p = root / "tools/house-party/prepare-release-ipa.sh"
text = p.read_text()

subprocess.run(["bash", "-n", str(p)], check=True)

required = [
    "Madeira-0.1.1.ipa",
    "045aeb8fd4c71c2e6a78fb4511f94c56f8ed7af14c47a3b0ea2937a4fc8bfcee",
    "https://aka.ms/vc14/vc_redist.x64.exe",
    "house-party-winegstreamer-arm64ec",
    "x86_64-vcruntime",
    "arm64ec-windows/winegstreamer.dll",
    '"contains_house_party_game_files": False',
    '"enabled_by_default": False',
]
for needle in required:
    assert needle in text, needle

# Packaging must never discover/copy Joey's owned game tree. It only operates
# on the official Madeira IPA, Microsoft redist, and open-source media bridge.
for forbidden in [
    "House-Party-AnkerGames.zip",
    "$HOME/Games/HouseParty",
    "HouseParty.exe",
    "rsync -a "$SOURCE",
]:
    assert forbidden not in text, forbidden

# The output must be a derived package under Cenluma by default, never overwrite
# the downloaded official release asset in place.
assert "Cenluma/HousePartyPort" in text
assert 'rm -f "$OUTPUT"' in text
assert 'rm -f "$IPA"' not in text
print("PASS: release-overlay packager is syntax-valid and never embeds owned game files")
