#!/usr/bin/env python3
"""Contract for Detroit-specific Vulkan capability qualification."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = (ROOT / "tests/x64/vulkan_probe.c").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require('#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V2"' in PROBE,
            "Detroit-aware Vulkan probe schema missing")
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

    # These are evidence fields, not invented hard requirements. The first M4
    # run should record what MoltenVK exposes so later feature gating can be
    # based on real Detroit behavior instead of guesses.
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

    print("PASS Detroit VK_EXT_descriptor_indexing is a physical pre-game requirement")
    print("PASS device creation explicitly enables Detroit descriptor indexing")
    print("PASS descriptor-indexing feature bits are recorded without speculative hard-fails")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
