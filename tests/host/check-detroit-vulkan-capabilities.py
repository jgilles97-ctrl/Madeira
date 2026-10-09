#!/usr/bin/env python3
"""Contract for Detroit-specific Vulkan capability qualification."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = (ROOT / "tests/x64/vulkan_probe.c").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require('#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V3"' in PROBE,
            "Detroit-aware Vulkan probe schema missing")

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

    # Individual feature bits are evidence fields, not invented hard requirements.
    for field in (
        "shaderUniformBufferArrayNonUniformIndexing",
        "shaderSampledImageArrayNonUniformIndexing",
        "shaderStorageBufferArrayNonUniformIndexing",
        "shaderStorageImageArrayNonUniformIndexing",
        "descriptorBindingPartiallyBound",
        "descriptorBindingVariableDescriptorCount",
        "runtimeDescriptorArray",
    ):
        require(field in PROBE, f"descriptor-indexing evidence field missing: {field}")
    require("get_physical_device_features2" in PROBE,
            "descriptor-indexing feature evidence no longer uses vkGetPhysicalDeviceFeatures2")

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

    # No fail() call may be attached to the memory-budget extension or telemetry.
    require('fail(' not in "\n".join(
        line for line in PROBE.splitlines()
        if "MEMORY_BUDGET" in line or "memory_budget_available" in line
    ), "memory-budget telemetry must not become a physical qualification gate")

    print("PASS Detroit VK_EXT_descriptor_indexing is a physical pre-game requirement")
    print("PASS device creation explicitly enables Detroit descriptor indexing")
    print("PASS descriptor-indexing feature bits are recorded without speculative hard-fails")
    print("PASS MoltenVK memory-budget data is evidence-only, not a pass/fail requirement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
