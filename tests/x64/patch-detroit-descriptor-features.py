#!/usr/bin/env python3
"""Strengthen the Detroit Vulkan canary with renderer-specific descriptor checks.

The base probe stays readable and portable. This build-time patch is deliberately
fail-closed: every anchor must match exactly once, otherwise the Windows canary
is not built. The output requires the descriptor-indexing feature bits documented
by Quantic Dream's Detroit renderer and enables those exact bits on VkDevice.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"error: {label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch(text: str) -> str:
    text = replace_once(
        text,
        '#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V4"',
        '#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V5"',
        "probe schema",
    )

    text = replace_once(
        text,
        '    PFN_vkGetPhysicalDeviceProperties get_physical_device_properties = NULL;\n',
        '    PFN_vkGetPhysicalDeviceProperties get_physical_device_properties = NULL;\n'
        '    PFN_vkGetPhysicalDeviceProperties2 get_physical_device_properties2 = NULL;\n',
        "properties2 declaration",
    )

    text = replace_once(
        text,
        '    int descriptor_indexing_available = 0;\n    VkResult vr;\n',
        '    int descriptor_indexing_available = 0;\n'
        '    VkPhysicalDeviceDescriptorIndexingFeatures descriptor_features;\n'
        '    int descriptor_features_valid = 0;\n'
        '    VkResult vr;\n',
        "descriptor feature storage",
    )

    text = replace_once(
        text,
        '    get_physical_device_properties =\n'
        '        (PFN_vkGetPhysicalDeviceProperties)get_instance_proc_addr(instance, "vkGetPhysicalDeviceProperties");\n',
        '    get_physical_device_properties =\n'
        '        (PFN_vkGetPhysicalDeviceProperties)get_instance_proc_addr(instance, "vkGetPhysicalDeviceProperties");\n'
        '    get_physical_device_properties2 =\n'
        '        (PFN_vkGetPhysicalDeviceProperties2)get_instance_proc_addr(instance, "vkGetPhysicalDeviceProperties2");\n',
        "properties2 resolver",
    )

    text = replace_once(
        text,
        '    if (!destroy_instance || !enumerate_physical_devices || !get_physical_device_properties ||\n'
        '        !get_memory_properties || !get_queue_properties || !enumerate_device_extensions || !create_device)\n',
        '    if (!destroy_instance || !enumerate_physical_devices || !get_physical_device_properties ||\n'
        '        !get_physical_device_properties2 || !get_memory_properties || !get_queue_properties ||\n'
        '        !enumerate_device_extensions || !create_device)\n',
        "required properties2 entrypoint",
    )

    text = replace_once(
        text,
        '    printf("DETROIT_VULKAN_1_1_DEVICE=PASS\\n");\n\n    {\n        VkPhysicalDeviceMemoryProperties mem;\n',
        '    printf("DETROIT_VULKAN_1_1_DEVICE=PASS\\n");\n\n'
        '#ifdef VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME\n'
        '    {\n'
        '        VkPhysicalDeviceProperties2 props2;\n'
        '        VkPhysicalDeviceDescriptorIndexingProperties descriptor_props;\n'
        '        memset(&props2, 0, sizeof(props2));\n'
        '        memset(&descriptor_props, 0, sizeof(descriptor_props));\n'
        '        props2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;\n'
        '        descriptor_props.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_PROPERTIES;\n'
        '        props2.pNext = &descriptor_props;\n'
        '        get_physical_device_properties2(physical_devices[0], &props2);\n'
        '        printf("LIMIT_UPDATE_AFTER_BIND_PER_STAGE_SAMPLED_IMAGES=%u\\n",\n'
        '               descriptor_props.maxPerStageDescriptorUpdateAfterBindSampledImages);\n'
        '        printf("LIMIT_UPDATE_AFTER_BIND_SET_SAMPLED_IMAGES=%u\\n",\n'
        '               descriptor_props.maxDescriptorSetUpdateAfterBindSampledImages);\n'
        '        printf("LIMIT_UPDATE_AFTER_BIND_ALL_POOLS=%u\\n",\n'
        '               descriptor_props.maxUpdateAfterBindDescriptorsInAllPools);\n'
        '        printf("LIMIT_UPDATE_AFTER_BIND_SET_STORAGE_BUFFERS=%u\\n",\n'
        '               descriptor_props.maxDescriptorSetUpdateAfterBindStorageBuffers);\n'
        '        printf("LIMIT_UPDATE_AFTER_BIND_SET_STORAGE_IMAGES=%u\\n",\n'
        '               descriptor_props.maxDescriptorSetUpdateAfterBindStorageImages);\n'
        '        if (descriptor_props.maxDescriptorSetUpdateAfterBindSampledImages < 4096u)\n'
        '            printf("DETROIT_DESCRIPTOR_LIMIT_RISK=HIGH:SAMPLED_IMAGE_UPDATE_AFTER_BIND_LT_4096\\n");\n'
        '        else\n'
        '            printf("DETROIT_DESCRIPTOR_LIMIT_RISK=LOW_FOR_PUBLISHED_4000_PLUS_TEXTURE_WORKLOAD\\n");\n'
        '    }\n'
        '#endif\n\n'
        '    {\n        VkPhysicalDeviceMemoryProperties mem;\n',
        "descriptor update-after-bind limit telemetry",
    )

    old_features = '''#ifdef VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME
    if (get_physical_device_features2) {
        VkPhysicalDeviceFeatures2 features2;
        VkPhysicalDeviceDescriptorIndexingFeatures descriptor_features;
        memset(&features2, 0, sizeof(features2));
        memset(&descriptor_features, 0, sizeof(descriptor_features));
        features2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
        descriptor_features.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES;
        features2.pNext = &descriptor_features;
        get_physical_device_features2(physical_devices[0], &features2);
        printf("CORE_FEATURE_MULTI_DRAW_INDIRECT=%u\\n", features2.features.multiDrawIndirect);
        printf("CORE_FEATURE_DRAW_INDIRECT_FIRST_INSTANCE=%u\\n",
               features2.features.drawIndirectFirstInstance);
        printf("CORE_FEATURE_SHADER_INT64=%u\\n", features2.features.shaderInt64);
        printf("DESCRIPTOR_INDEXING_SHADER_UNIFORM_BUFFER_NONUNIFORM=%u\\n",
               descriptor_features.shaderUniformBufferArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_SAMPLED_IMAGE_NONUNIFORM=%u\\n",
               descriptor_features.shaderSampledImageArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_STORAGE_BUFFER_NONUNIFORM=%u\\n",
               descriptor_features.shaderStorageBufferArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_STORAGE_IMAGE_NONUNIFORM=%u\\n",
               descriptor_features.shaderStorageImageArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_PARTIALLY_BOUND=%u\\n",
               descriptor_features.descriptorBindingPartiallyBound);
        printf("DESCRIPTOR_INDEXING_VARIABLE_COUNT=%u\\n",
               descriptor_features.descriptorBindingVariableDescriptorCount);
        printf("DESCRIPTOR_INDEXING_RUNTIME_ARRAY=%u\\n",
               descriptor_features.runtimeDescriptorArray);
    } else {
        printf("DESCRIPTOR_INDEXING_FEATURE_QUERY=UNAVAILABLE\\n");
    }
#endif
'''

    new_features = '''#ifdef VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME
    if (!get_physical_device_features2)
        return fail(37, "detroit-capabilities",
                    "vkGetPhysicalDeviceFeatures2 is unavailable, so Detroit descriptor features cannot be proven");
    {
        VkPhysicalDeviceFeatures2 features2;
        memset(&features2, 0, sizeof(features2));
        memset(&descriptor_features, 0, sizeof(descriptor_features));
        features2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
        descriptor_features.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES;
        features2.pNext = &descriptor_features;
        get_physical_device_features2(physical_devices[0], &features2);
        descriptor_features_valid = 1;
        printf("CORE_FEATURE_MULTI_DRAW_INDIRECT=%u\\n", features2.features.multiDrawIndirect);
        printf("CORE_FEATURE_DRAW_INDIRECT_FIRST_INSTANCE=%u\\n",
               features2.features.drawIndirectFirstInstance);
        printf("CORE_FEATURE_SHADER_INT64=%u\\n", features2.features.shaderInt64);
        printf("DESCRIPTOR_INDEXING_SHADER_UNIFORM_BUFFER_NONUNIFORM=%u\\n",
               descriptor_features.shaderUniformBufferArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_SAMPLED_IMAGE_NONUNIFORM=%u\\n",
               descriptor_features.shaderSampledImageArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_STORAGE_BUFFER_NONUNIFORM=%u\\n",
               descriptor_features.shaderStorageBufferArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_STORAGE_IMAGE_NONUNIFORM=%u\\n",
               descriptor_features.shaderStorageImageArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SAMPLED_IMAGE_UPDATE_AFTER_BIND=%u\\n",
               descriptor_features.descriptorBindingSampledImageUpdateAfterBind);
        printf("DESCRIPTOR_INDEXING_STORAGE_BUFFER_UPDATE_AFTER_BIND=%u\\n",
               descriptor_features.descriptorBindingStorageBufferUpdateAfterBind);
        printf("DESCRIPTOR_INDEXING_STORAGE_IMAGE_UPDATE_AFTER_BIND=%u\\n",
               descriptor_features.descriptorBindingStorageImageUpdateAfterBind);
        printf("DESCRIPTOR_INDEXING_PARTIALLY_BOUND=%u\\n",
               descriptor_features.descriptorBindingPartiallyBound);
        printf("DESCRIPTOR_INDEXING_VARIABLE_COUNT=%u\\n",
               descriptor_features.descriptorBindingVariableDescriptorCount);
        printf("DESCRIPTOR_INDEXING_RUNTIME_ARRAY=%u\\n",
               descriptor_features.runtimeDescriptorArray);

        if (!descriptor_features.shaderSampledImageArrayNonUniformIndexing)
            return fail(38, "detroit-capabilities",
                        "Detroit requires non-uniform indexing of sampled-image descriptor arrays");
        if (!descriptor_features.descriptorBindingSampledImageUpdateAfterBind)
            return fail(39, "detroit-capabilities",
                        "Detroit requires sampled-image descriptors that can update after bind");
        if (!descriptor_features.descriptorBindingPartiallyBound)
            return fail(40, "detroit-capabilities",
                        "Detroit requires partially-bound descriptor arrays");
        if (!descriptor_features.runtimeDescriptorArray)
            return fail(41, "detroit-capabilities",
                        "Detroit requires runtime descriptor arrays for its bindless resource path");

        printf("DETROIT_DESCRIPTOR_NONUNIFORM_SAMPLED_IMAGE=PASS\\n");
        printf("DETROIT_DESCRIPTOR_SAMPLED_IMAGE_UPDATE_AFTER_BIND=PASS\\n");
        printf("DETROIT_DESCRIPTOR_PARTIALLY_BOUND=PASS\\n");
        printf("DETROIT_DESCRIPTOR_RUNTIME_ARRAY=PASS\\n");
    }
#endif
'''
    text = replace_once(text, old_features, new_features, "descriptor feature gate")

    text = replace_once(
        text,
        '        VkDeviceCreateInfo device_info;\n        const char *enabled_device_exts[2];\n',
        '        VkDeviceCreateInfo device_info;\n'
        '        VkPhysicalDeviceDescriptorIndexingFeatures enabled_descriptor_features;\n'
        '        const char *enabled_device_exts[2];\n',
        "enabled descriptor features declaration",
    )

    text = replace_once(
        text,
        '        memset(&device_info, 0, sizeof(device_info));\n'
        '        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;\n',
        '        memset(&enabled_descriptor_features, 0, sizeof(enabled_descriptor_features));\n'
        '        enabled_descriptor_features.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES;\n'
        '        if (!descriptor_features_valid)\n'
        '            return fail(42, "detroit-capabilities", "descriptor feature proof was not completed");\n'
        '        enabled_descriptor_features.shaderSampledImageArrayNonUniformIndexing = VK_TRUE;\n'
        '        enabled_descriptor_features.descriptorBindingSampledImageUpdateAfterBind = VK_TRUE;\n'
        '        enabled_descriptor_features.descriptorBindingPartiallyBound = VK_TRUE;\n'
        '        enabled_descriptor_features.runtimeDescriptorArray = VK_TRUE;\n'
        '        memset(&device_info, 0, sizeof(device_info));\n'
        '        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;\n'
        '        device_info.pNext = &enabled_descriptor_features;\n',
        "explicit descriptor feature enablement",
    )

    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.input.read_text(encoding="utf-8")
    transformed = patch(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(transformed, encoding="utf-8")
    print(f"PASS: wrote Detroit descriptor-hardened probe to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
