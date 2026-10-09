#!/usr/bin/env python3
"""Contract for Detroit's argument-buffer compute write/readback qualification."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tests/x64/vulkan_probe.c"
PATCHER = ROOT / "tests/x64/patch-detroit-descriptor-features.py"
COMPUTE = ROOT / "tests/x64/vulkan_compute_writeback_probe.c"
BUILDER = ROOT / "tests/x64/build-vulkan-probe.sh"
STANDALONE_BUILDER = ROOT / "tests/x64/build-vulkan-compute-writeback-probe.sh"
ORCHESTRATOR = ROOT / "build/detroit-vulkan/build.sh"
PROFILE = ROOT / "docs/detroit-m4-8gb.cfg"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def transformed_probe() -> str:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "probe.c"
        subprocess.run(
            ["python3", str(PATCHER), str(BASE), str(out)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.read_text(encoding="utf-8")


def main() -> int:
    compute = COMPUTE.read_text(encoding="utf-8")
    probe = transformed_probe()
    builder = BUILDER.read_text(encoding="utf-8")
    standalone = STANDALONE_BUILDER.read_text(encoding="utf-8")
    orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    # The canary must exercise the exact risky configuration: argument buffers
    # enabled plus a real compute storage-buffer write that is read back by CPU.
    for needle, label in (
        ('SetEnvironmentVariableA("MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS", "1")', "explicit argument-buffer enable"),
        ("EXPECTED_VALUE", "known compute input value"),
        ("OUTPUT_SENTINEL", "distinct untouched-output sentinel"),
        ("VK_BUFFER_USAGE_STORAGE_BUFFER_BIT", "storage-buffer path"),
        ("vkCreateComputePipelines", "real compute pipeline creation"),
        ("vkCmdDispatch", "real compute dispatch"),
        ("vkQueueSubmit", "GPU queue submission"),
        ("vkQueueWaitIdle", "GPU completion wait"),
        ("read_u32", "CPU readback"),
        ("observed != EXPECTED_VALUE", "exact data-integrity comparison"),
        ("compute dispatch completed but storage write was lost", "silent-store-loss diagnosis"),
        ("MOLTENVK_ARGUMENT_BUFFER_COMPUTE_INTEGRITY=PASS", "stable compute-integrity PASS marker"),
        ("https://gist.github.com/sheredom/523f02bbad2ae397d7ed255f3f3b5a7f", "public-domain shader provenance"),
    ):
        require(needle in compute, f"compute canary missing {label}: {needle}")

    # Pipeline/submit success alone must never qualify the canary. Exact CPU
    # readback comparison must occur before the stable PASS marker.
    require(compute.index("observed != EXPECTED_VALUE") <
            compute.index('printf("MOLTENVK_ARGUMENT_BUFFER_COMPUTE_INTEGRITY=PASS'),
            "compute-integrity PASS can be printed before exact readback validation")

    # Keep Detroit's trusted physical launch payload narrow: the compute source
    # is linked into the existing vulkan_probe.exe instead of adding a fifth EXE.
    require("-Dmain=madeira_compute_writeback_main" in builder,
            "compute canary is no longer linked into the existing capability EXE")
    require("vulkan_compute_writeback_probe.c" in builder,
            "capability builder no longer compiles compute integrity source")
    require("madeira_compute_writeback_main" in probe,
            "patched capability probe no longer calls linked compute integrity code")
    require("DETROIT_COMPUTE_WRITEBACK=PASS" in probe,
            "aggregate capability probe lacks explicit compute-writeback marker")
    require(probe.index("madeira_compute_writeback_main()") <
            probe.index('printf("DETROIT_CAPABILITIES=PASS'),
            "DETROIT_CAPABILITIES can be published before compute integrity passes")

    require("four fixed x64 test executables" in orchestrator,
            "physical payload documentation no longer preserves the narrow four-EXE route")
    require('need_file "$FARM/vulkan_compute_writeback_probe.exe"' not in orchestrator,
            "standalone compute debugger was accidentally added to the trusted iPad payload")
    require("build-vulkan-compute-writeback-probe.sh" not in orchestrator,
            "orchestrator should rely on integrated compute qualification, not a fifth payload EXE")

    # Standalone builder is retained for isolated CI/debugging only.
    require("VULKAN_COMPUTE_WRITEBACK_PROBE_OUT" in standalone,
            "standalone compute debugger output override missing")
    require("vulkan_compute_writeback_probe.c" in standalone,
            "standalone compute debugger no longer compiles the integrity source")

    require('env.MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS = 1' in profile,
            "Detroit game profile can silently test a different descriptor path than compute qualification")

    print("PASS compute qualification forces Metal argument buffers on")
    print("PASS GPU submission is not enough; exact storage-buffer CPU readback is required")
    print("PASS silent compute-store loss has a dedicated failure diagnosis")
    print("PASS compute integrity runs before DETROIT_CAPABILITIES=PASS")
    print("PASS trusted physical payload remains four fixed x64 executables")
    print("PASS standalone compute executable remains debug-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
