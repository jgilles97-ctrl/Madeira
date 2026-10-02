#!/usr/bin/env python3
"""Static safety guard for physical-device House Party data helper."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[2]
p=root/"tools/house-party/device-data.sh"
text=p.read_text()
subprocess.run(["bash","-n",str(p)],check=True)

for needle in [
    "devicectl device copy to",
    "devicectl device copy from",
    "--domain-type appDataContainer",
    "--domain-identifier",
    "Documents/wine/drive_c/Games/HouseParty",
    "Refusing to overwrite existing device destination",
    "tools/madeira_log_triage.py",
]:
    assert needle in text, needle

assert "--remove-existing-content" in text  # documentation says it is forbidden
# It must never actually pass the destructive option as a command argument.
for line in text.splitlines():
    if "xcrun devicectl" in line or line.lstrip().startswith("--"):
        assert "--remove-existing-content" not in line
assert 'rm -rf "$SOURCE"' not in text
assert 'rm -rf "$REMOTE"' not in text
assert "HouseParty.exe" in text

print("PASS: device helper stages/pulls app-container data without source mutation or remote deletion")
