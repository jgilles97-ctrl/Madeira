#!/usr/bin/env python3
"""Static guard for the one-command House Party Mac cycle."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
p = root / "tools/house-party/run-local-cycle.sh"
text = p.read_text()

subprocess.run(["bash", "-n", str(p)], check=True)

required = [
    "tools/house-party/fingerprint.py",
    "tools/house-party/check-gptk4.sh",
    "tools/house-party/mac-crossover-smoke.sh",
    "compatibility-manifest.json",
    "gptk4-environment.txt",
    "reconstruction-feasibility.json",
    "cycle-summary.json",
    "House-Party-AnkerGames.zip",
    "source_policy",
]
for needle in required:
    assert needle in text, needle

# Sources/archives can be read and hashed, but destructive operations must target derived paths only.
assert 'rm -rf "$SOURCE"' not in text
assert 'rm -f "$ARCHIVE"' not in text
assert 'mv "$SOURCE"' not in text
assert 'mv "$ARCHIVE"' not in text
assert 'ditto -x -k "$ARCHIVE" "$DEST.tmp"' in text
assert 'BASE="${HOUSE_PARTY_PORT_ROOT:-$HOME/Library/Application Support/Cenluma/HousePartyPort}"' in text

print("PASS: local advance cycle is syntax-valid, auto-discovers known owned inputs, and preserves sources")
