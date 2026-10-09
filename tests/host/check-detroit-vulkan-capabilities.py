#!/usr/bin/env python3
"""Contract for Detroit-specific Vulkan capability qualification."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/x64/vulkan_probe.c"
PATCHER = ROOT / "tests/x64/patch-detroit-descriptor-features.py"
BUILDER = ROOT / "tests/x64/build-vulkan-probe.sh"
PROFILE = ROOT / "docs/detroit-m4-8gb.cfg"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def patched_probe() -> str:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "vulkan_probe_patched.c"
        subprocess.run(
            ["python3", str(PATCHER), str(SOURCE), str(out)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.read_text(encoding="utf-8")


def main() -> int:
    probe = patched_probe()
    patcher = PATCHER.read_text(encoding="utf-8")
    builder = BUILDER.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    require('#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V5"' in probe,
            "descriptor-hardened Detroit Vulkan probe schema missing")
    require("patch-detroit-descriptor-features.py" in builder,
            "Vulkan probe builder bypasses the fail-closed Detroit descriptor patch")
    require('env.MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS = 1' in profile,
            "Detroit M4 profile does not explicitly keep Metal argument buffers enabled")
    require("compute write/readback integrity canary" in profile,
            "argument-buffer profile no longer documents its compute-integrity qualification dependency")

    # Published Detroit PC requirements explicitly require Vulkan 1.1. Protect
    # both halves: Windows loader/API negotiation and the actual physical device.
    require("loader_version < VK_API_VERSION_1_1" in probe,
            "Vulkan 1.1 loader requirement was weakened")
    require('app_info.apiVersion = VK_API_VERSION_1_1' in probe,
            "probe no longer requests the same Vulkan 1.1 baseline Detroit requires")
    require("primary_api_version < VK_API_VERSION_1_1" in probe,
            "physical-device Vulkan 1.1 requirement was weakened")
    require('printf("DETROIT_VULKAN_1_1_LOADER=PASS' in probe,
            "loader Vulkan 1.1 success marker missing")
    require('printf("DETROIT_VULKAN_1_1_DEVICE=PASS' in probe,
            "device Vulkan 1.1 success marker missing")

    # Detroit relies on descriptor indexing, not merely extension advertisement.
    require("VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME" in probe,
            "Detroit descriptor-indexing extension is no longer queried")
    require("descriptor_indexing_available" in probe,
            "descriptor-indexing availability is not tracked")
    require("HAS_EXT_DESCRIPTOR_INDEXING=%d" in probe,
            "descriptor-indexing evidence is not printed")
    require('return fail(32, "detroit-capabilities"' in probe,
            "missing VK_EXT_descriptor_indexing no longer hard-fails before Detroit")

    # Quantic Dream documents non-uniform texture-array access, update-after-bind
    # descriptor updates, and partially specified large arrays. These are hard
    # renderer requirements. runtimeDescriptorArray protects the bindless array
    # path used to expose those resources to shaders.
    required_bits = (
        ("shaderSampledImageArrayNonUniformIndexing", "non-uniform sampled-image indexing"),
        ("descriptorBindingSampledImageUpdateAfterBind", "sampled-image update-after-bind"),
        ("descriptorBindingPartiallyBound", "partially-bound descriptors"),
        ("runtimeDescriptorArray", "runtime descriptor arrays"),
    )
    for bit, label in required_bits:
        require(bit in probe, f"Detroit descriptor feature missing: {label}")
        require(f"enabled_descriptor_features.{bit} = VK_TRUE" in probe,
                f"VkDevice does not explicitly enable Detroit descriptor feature: {label}")

    for marker in (
        "DETROIT_DESCRIPTOR_NONUNIFORM_SAMPLED_IMAGE=PASS",
        "DETROIT_DESCRIPTOR_SAMPLED_IMAGE_UPDATE_AFTER_BIND=PASS",
        "DETROIT_DESCRIPTOR_PARTIALLY_BOUND=PASS",
        "DETROIT_DESCRIPTOR_RUNTIME_ARRAY=PASS",
        "DETROIT_DESCRIPTOR_INDEXING=PASS",
    ):
        require(marker in probe, f"stable Detroit descriptor PASS marker missing: {marker}")

    require("device_info.pNext = &enabled_descriptor_features" in probe,
            "descriptor feature proof is not connected to VkDevice creation")
    require("vkCreateDevice with Detroit descriptor-indexing capability failed" in probe,
            "descriptor-indexing device-creation failure is not explicit")

    # Record the update-after-bind limits that are most relevant to Detroit's
    # published 4,000+ visible-texture workload. A 4096 comparison is a risk
    # signal, not a hard pass/fail threshold.
    for field in (
        "maxPerStageDescriptorUpdateAfterBindSampledImages",
        "maxDescriptorSetUpdateAfterBindSampledImages",
        "maxUpdateAfterBindDescriptorsInAllPools",
        "maxDescriptorSetUpdateAfterBindStorageBuffers",
        "maxDescriptorSetUpdateAfterBindStorageImages",
        "LIMIT_UPDATE_AFTER_BIND_PER_STAGE_SAMPLED_IMAGES",
        "LIMIT_UPDATE_AFTER_BIND_SET_SAMPLED_IMAGES",
        "LIMIT_UPDATE_AFTER_BIND_ALL_POOLS",
        "DETROIT_DESCRIPTOR_LIMIT_RISK=HIGH:SAMPLED_IMAGE_UPDATE_AFTER_BIND_LT_4096",
    ):
        require(field in probe, f"Detroit update-after-bind capacity evidence missing: {field}")
    risk_lines = "\n".join(line for line in probe.splitlines() if "DETROIT_DESCRIPTOR_LIMIT_RISK" in line)
    require("fail(" not in risk_lines,
            "published 4,000+ texture workload comparison must remain a risk signal, not an invented hard threshold")

    # Detroit's published renderer uses compute shaders. Require at least one
    # compute-capable queue, but deliberately do not demand a separate dedicated
    # queue because the source does not establish that as mandatory.
    require("VK_QUEUE_COMPUTE_BIT" in probe,
            "compute-capable queue is no longer detected")
    require("compute_queue == UINT32_MAX" in probe,
            "missing compute queue no longer blocks Detroit qualification")
    require('return fail(36, "detroit-capabilities"' in probe,
            "compute requirement is not classified as a Detroit capability failure")
    require('printf("DETROIT_COMPUTE_QUEUE=PASS' in probe,
            "compute capability success marker missing")
    require("DEDICATED_COMPUTE_QUEUE_FAMILY=NONE" in probe,
            "dedicated compute queue is no longer evidence-only")

    # Additional feature bits/limits remain evidence fields unless Detroit's
    # public renderer documentation establishes them as required.
    for field in (
        "shaderUniformBufferArrayNonUniformIndexing",
        "shaderStorageBufferArrayNonUniformIndexing",
        "shaderStorageImageArrayNonUniformIndexing",
        "descriptorBindingStorageBufferUpdateAfterBind",
        "descriptorBindingStorageImageUpdateAfterBind",
        "descriptorBindingVariableDescriptorCount",
        "CORE_FEATURE_MULTI_DRAW_INDIRECT",
        "CORE_FEATURE_DRAW_INDIRECT_FIRST_INSTANCE",
        "LIMIT_MAX_PER_STAGE_SAMPLED_IMAGES",
        "LIMIT_MAX_DESCRIPTOR_SET_SAMPLED_IMAGES",
        "LIMIT_MAX_DESCRIPTOR_SET_STORAGE_BUFFERS",
        "LIMIT_MAX_COMPUTE_WORKGROUP_INVOCATIONS",
        "LIMIT_MAX_DRAW_INDIRECT_COUNT",
    ):
        require(field in probe, f"Detroit capability evidence field missing: {field}")
    require("get_physical_device_features2" in probe,
            "descriptor/core feature evidence no longer uses vkGetPhysicalDeviceFeatures2")
    require("get_physical_device_properties2" in probe,
            "descriptor limit evidence no longer uses vkGetPhysicalDeviceProperties2")

    # VK_EXT_memory_budget is useful on an 8 GB unified-memory iPad, but current
    # MoltenVK/iOS semantics have an open upstream discussion. Protect the design:
    # collect raw budget, raw usage, and budget+usage, but NEVER use the extension
    # as a hard qualification gate.
    for needle, label in (
        ("VK_EXT_MEMORY_BUDGET_EXTENSION_NAME", "memory-budget extension query"),
        ("vkGetPhysicalDeviceMemoryProperties2", "memory-properties2 query"),
        ("VkPhysicalDeviceMemoryBudgetPropertiesEXT", "memory-budget properties struct"),
        ("MEMORY_BUDGET_HEAP_%u_BUDGET_BYTES", "raw heap budget evidence"),
        ("MEMORY_BUDGET_HEAP_%u_USAGE_BYTES", "raw heap usage evidence"),
        ("MEMORY_BUDGET_HEAP_%u_BUDGET_PLUS_USAGE_BYTES", "iOS comparison evidence"),
        ("MEMORY_BUDGET_SEMANTICS=TELEMETRY_ONLY_MOLTENVK_IOS", "explicit telemetry-only semantics"),
        ("MEMORY_BUDGET_TELEMETRY=PASS", "memory-budget telemetry marker"),
        ("MEMORY_BUDGET_TELEMETRY=EXTENSION_UNAVAILABLE", "non-fatal missing-extension marker"),
        ("MEMORY_BUDGET_TELEMETRY=QUERY_ENTRYPOINT_UNAVAILABLE", "non-fatal missing-entrypoint marker"),
    ):
        require(needle in probe, f"missing {label}: {needle}")

    memory_lines = "\n".join(
        line for line in probe.splitlines()
        if "MEMORY_BUDGET" in line or "memory_budget_available" in line
    )
    require("fail(" not in memory_lines,
            "memory-budget telemetry must not become a physical qualification gate")

    require('printf("DETROIT_CAPABILITIES=PASS' in probe,
            "aggregate Detroit capability PASS marker missing")

    # The patcher itself must fail closed rather than silently skipping a drifted
    # source file.
    require("expected exactly one anchor" in patcher,
            "descriptor patcher no longer rejects source drift")

    print("PASS Detroit requires Vulkan 1.1 at loader and physical-device levels")
    print("PASS Detroit descriptor extension plus renderer-specific feature bits are required")
    print("PASS VkDevice explicitly enables the proven Detroit descriptor features")
    print("PASS update-after-bind descriptor capacity is recorded with a non-blocking 4096 risk signal")
    print("PASS Metal argument buffers are explicit in the M4 Detroit profile")
    print("PASS at least one compute-capable queue is required; dedicated compute remains evidence-only")
    print("PASS MoltenVK memory-budget data is evidence-only, not a pass/fail requirement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
