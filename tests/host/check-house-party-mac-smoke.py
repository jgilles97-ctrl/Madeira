#!/usr/bin/env python3
"""Static guard for the House Party CrossOver matrix."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
p = root / "tools/house-party/mac-crossover-smoke.sh"
text = p.read_text()

subprocess.run(["bash", "-n", str(p)], check=True)

required = [
    'rsync -a "$SOURCE/" "$GAME/"',
    '"dxmt"',
    '"d3dmetal"',
    '"dxvk"',
    '"wined3d"',
    'CX_GRAPHICS_BACKEND',
    'WINEMSYNC',
    'WINEDXVK',
    'DXMT_LOG_PATH',
    'backend_requested',
    'backend_observed',
    'backend_match',
    'backend_evidence',
    'compatibility-manifest.json',
    'matrix.json',
    'Process survival/backend selection is diagnostic only; it does not prove render/menu/gameplay.',
]
for needle in required:
    assert needle in text, needle

assert 'rm -rf "$SOURCE"' not in text
assert 'mv "$SOURCE"' not in text
assert 'cp -R "$GAME" "$SOURCE"' not in text
assert 'PREFIX="HouseParty-Port"' in text
assert '.derived-house-party-copy' in text
print("PASS: CrossOver matrix is syntax-valid, source-copy based, isolated and validation-limited")
