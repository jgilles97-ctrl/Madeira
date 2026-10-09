#!/usr/bin/env python3
"""Guard Detroit-specific capabilities in the durable physical-iPad proof."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = (ROOT / "tests/x64/vulkan_device_gate.c").read_text(encoding="utf-8")
APP = (ROOT / "app/Madeira/MadeiraApp.swift").read_text(encoding="utf-8")
PROBE = (ROOT / "tests/x64/vulkan_probe.c").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    for needle in (
        "DETROIT_VULKAN_1_1_LOADER=PASS",
        "DETROIT_VULKAN_1_1_DEVICE=PASS",
        "DETROIT_COMPUTE_QUEUE=PASS",
        "DETROIT_DESCRIPTOR_INDEXING=PASS",
        "DETROIT_CAPABILITIES=PASS",
    ):
        require(needle in PROBE, f"Detroit device canary lost capability marker: {needle}")

    require('printf("DETROIT_CAPABILITIES=PASS\\n")' in GATE,
            "physical gate output no longer exposes Detroit capability PASS")
    require('"DETROIT_CAPABILITIES=PASS\\r\\n"' in GATE,
            "durable physical proof no longer records Detroit capability PASS")
    require(GATE.index('printf("DETROIT_CAPABILITIES=PASS') > GATE.index("run_stage(&stages[i])"),
            "controller claims Detroit capabilities before the child capability canary runs")
    require(GATE.index('"DETROIT_CAPABILITIES=PASS\\r\\n"') < GATE.index('"VULKAN_DEVICE=PASS\\r\\n"'),
            "proof should state Detroit capability baseline before generic device PASS")

    require('values["DETROIT_CAPABILITIES"] == "PASS"' in APP,
            "iPad proof reader accepts proof without explicit Detroit capabilities")
    require("Vulkan 1.1, compute, and descriptor-indexing baseline" in APP,
            "passed-state explanation no longer tells the user what was proved")
    require("Detroit capability/Vulkan device test failed" in APP,
            "failed first stage no longer explains that Detroit capabilities are included")

    print("PASS Detroit capability canary remains evidence-backed")
    print("PASS physical proof explicitly records DETROIT_CAPABILITIES=PASS")
    print("PASS iPad rejects generic/old proof without Detroit capability PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
