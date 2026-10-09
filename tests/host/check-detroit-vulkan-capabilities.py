#!/usr/bin/env python3
"""Contract for Detroit-specific Vulkan capability qualification."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = (ROOT / "tests/x64/vulkan_probe.c").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require('#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V4"' in PROBE,
            "Detroit-aware Vulkan probe schema missing")

    # Published Detroit PC requirements explicitly require Vulkan 1.1. Protect
    # both halves: Windows loader/API negotiation and the actual physical device.
    require("loader_version < VK_API_VERSION_1_1" in PROBE,
            "Vulkan 1.1 loader requirement was weakened")
    require('app_info.apiVersion = VK_API_VERSION_1_1' in PROBE,
            "probe no longer requests the same Vulkan 1.1 baseline Detroit requires")
    require("primary_api_version < VK_API_VERSION_1_1" in PROBE,
            "physical-device Vulkan 1.1 requirement was weakened")
    require('printf("DETROIT_VULKAN_1_1_LOADER=PASS' in PROBE,
            "loader Vulkan 1.1 success marker missing")
    require('printf("DETROIT_VULKAN_1_1_DEVICE=PASS' in PROBE,
            "device Vulkan 1.1 success marker missing")

    # Hard requirement backed by Quantic Dream/AMD's public Detroit renderer
    # description: the game relies on descriptor indexing.
    require("VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME" in PROBE,
            "Detroit descriptor-indexing extension is no longer queried")
    require("descriptor_indexing_available" in PROBE,
            "descriptor-indexing availability is not tracked")
    require("HAS_EXT_DESCRIPTOR_INDEXING=%d" in PROBE,
            "descriptor-indexing evidence is not printed")
    require('return fail(32, "detroit-capabilities"' in PROBE,
            "missing VK_EXT_descriptor_indexing no longer hard-fails before Detroit")
    require("enabled_device_exts[enabled_device_ext_count++] = VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME" in PROBE,
            "probe reports descriptor indexing but does not enable it on VkDevice")
    require("vkCreateDevice with Detroit descriptor-indexing capability failed" in PROBE,
            "descriptor-indexing device-creation failure is not explicit")
    require('printf("DETROIT_DESCRIPTOR_INDEXING=PASS' in PROBE,
            "successful Detroit descriptor-indexing negotiation lacks a stable PASS marker")

    # Detroit's published renderer uses compute shaders. Require at least one
    # compute-capable queue, but deliberately do not demand a separate dedicated
    # queue because the source does not establish that as mandatory.
    require("VK_QUEUE_COMPUTE_BIT" in PROBE,
            "compute-capable queue is no longer detected")
    require("compute_queue == UINT32_MAX" in PROBE,
            "missing compute queue no longer blocks Detroit qualification")
    require('return fail(36, "detroit-capabilities"' in PROBE,
            "compute requirement is not classified as a Detroit capability failure")
    require('printf("DETROIT_COMPUTE_QUEUE=PASS' in PROBE,
            "compute capability success marker missing")
    require("DEDICATED_COMPUTE_QUEUE_FAMILY=NONE" in PROBE,
            "dedicated compute queue is no longer evidence-only")

    # Individual feature bits/limits are evidence fields, not invented hard requirements.
    for field in (
        "shaderUniformBufferArrayNonUniformIndexing",
        "shaderSampledImageArrayNonUniformIndexing",
        "shaderStorageBufferArrayNonUniformIndexing",
        "shaderStorageImageArrayNonUniformIndexing",
        "descriptorBindingPartiallyBound",
        "descriptorBindingVariableDescriptorCount",
        "runtimeDescriptorArray",
        "CORE_FEATURE_MULTI_DRAW_INDIRECT",
        "CORE_FEATURE_DRAW_INDIRECT_FIRST_INSTANCE",
        "LIMIT_MAX_PER_STAGE_SAMPLED_IMAGES",
        "LIMIT_MAX_DESCRIPTOR_SET_SAMPLED_IMAGES",
        "LIMIT_MAX_DESCRIPTOR_SET_STORAGE_BUFFERS",
        "LIMIT_MAX_COMPUTE_WORKGROUP_INVOCATIONS",
        "LIMIT_MAX_DRAW_INDIRECT_COUNT",
    ):
        require(field in PROBE, f"Detroit capability evidence field missing: {field}")
    require("get_physical_device_features2" in PROBE,
            "descriptor/core feature evidence no longer uses vkGetPhysicalDeviceFeatures2")

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
        require(needle in PROBE, f"missing {label}: {needle}")

    memory_lines = "\n".join(
        line for line in PROBE.splitlines()
        if "MEMORY_BUDGET" in line or "memory_budget_available" in line
    )
    require("fail(" not in memory_lines,
            "memory-budget telemetry must not become a physical qualification gate")

    require('printf("DETROIT_CAPABILITIES=PASS' in PROBE,
            "aggregate Detroit capability PASS marker missing")

    print("PASS Detroit requires Vulkan 1.1 at loader and physical-device levels")
    print("PASS Detroit VK_EXT_descriptor_indexing is a physical pre-game requirement")
    print("PASS device creation explicitly enables Detroit descriptor indexing")
    print("PASS at least one compute-capable queue is required; dedicated compute remains evidence-only")
    print("PASS descriptor/core limits are recorded without speculative thresholds")
    print("PASS MoltenVK memory-budget data is evidence-only, not a pass/fail requirement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
