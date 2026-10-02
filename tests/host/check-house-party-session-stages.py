#!/usr/bin/env python3
"""Source-level guard for House Party/Madeira device milestone markers."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
src = (root / "app/Madeira/Library.swift").read_text()

required = [
    '[session-stage] stage=',
    'logStage("begin"',
    'logStage("process-running")',
    'logStage("first-surface"',
    'logStage("first-present"',
    'logStage("failed-before-process"',
    'logStage("end"',
    'stageProcessLogged = false',
    'stageSurfaceLogged = false',
    'stagePresentLogged = false',
]
for needle in required:
    assert needle in src, needle

# Never equate first presentation with menu/gameplay in the runtime source.
assert 'logStage("reaches-menu")' not in src
assert 'logStage("gameplay")' not in src
print("PASS: device session-stage markers are single-shot and validation-limited")
