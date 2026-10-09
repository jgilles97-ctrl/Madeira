/*
 * vulkan_probe.c - Windows x64 Vulkan/Detroit capability canary for Madeira.
 *
 * This program deliberately does not link to vulkan-1.lib. It loads the
 * Windows Vulkan loader exactly the way a real game can, so a PASS proves
 * vulkan-1.dll is present and can reach Wine's Vulkan implementation.
 *
 * Detroit relies on VK_EXT_descriptor_indexing for its resource-array/bindless
 * renderer. This probe therefore treats that extension as a hard pre-game
 * capability: it must be advertised and successfully enabled on VkDevice.
 * Individual descriptor-indexing feature bits are printed for device evidence;
 * we do not invent stricter per-bit requirements without game evidence.
 */

#define WIN32_LEAN_AND_MEAN
#define VK_USE_PLATFORM_WIN32_KHR 1
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define PROBE_SCHEMA "MADEIRA_VK_PROBE_V2"

static int has_extension(const VkExtensionProperties *exts, uint32_t count,
                         const char *name)
{
    uint32_t i;
    for (i = 0; i < count; ++i)
        if (!strcmp(exts[i].extensionName, name)) return 1;
    return 0;
}

static void print_version(uint32_t version)
{
    printf("%u.%u.%u", VK_VERSION_MAJOR(version), VK_VERSION_MINOR(version),
           VK_VERSION_PATCH(version));
}

static int fail(int code, const char *stage, const char *message)
{
    fprintf(stderr, "RESULT=FAIL\nSTAGE=%s\nERROR=%s\nEXIT_CODE=%d\n",
            stage, message, code);
    return code;
}

int main(void)
{
    HMODULE loader = NULL;
    PFN_vkGetInstanceProcAddr get_instance_proc_addr = NULL;
    PFN_vkEnumerateInstanceVersion enumerate_instance_version = NULL;
    PFN_vkEnumerateInstanceExtensionProperties enumerate_instance_extensions = NULL;
    PFN_vkCreateInstance create_instance = NULL;
    PFN_vkDestroyInstance destroy_instance = NULL;
    PFN_vkEnumeratePhysicalDevices enumerate_physical_devices = NULL;
    PFN_vkGetPhysicalDeviceProperties get_physical_device_properties = NULL;
    PFN_vkGetPhysicalDeviceMemoryProperties get_memory_properties = NULL;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_properties = NULL;
    PFN_vkEnumerateDeviceExtensionProperties enumerate_device_extensions = NULL;
    PFN_vkGetPhysicalDeviceFeatures2 get_physical_device_features2 = NULL;
    PFN_vkCreateDevice create_device = NULL;
    PFN_vkDestroyDevice destroy_device = NULL;
    VkExtensionProperties *instance_exts = NULL;
    VkExtensionProperties *device_exts = NULL;
    VkPhysicalDevice *physical_devices = NULL;
    VkQueueFamilyProperties *queues = NULL;
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    uint32_t loader_version = VK_API_VERSION_1_0;
    uint32_t instance_ext_count = 0;
    uint32_t physical_count = 0;
    uint32_t queue_count = 0;
    uint32_t device_ext_count = 0;
    uint32_t graphics_queue = UINT32_MAX;
    uint32_t i;
    int descriptor_indexing_available = 0;
    VkResult vr;

    printf("SCHEMA=%s\n", PROBE_SCHEMA);
    printf("ARCH=x86_64-windows\n");

    loader = LoadLibraryA("vulkan-1.dll");
    if (!loader)
        return fail(10, "load-vulkan-loader",
                    "LoadLibraryA(vulkan-1.dll) failed; guest Vulkan loader is missing");
    printf("LOADER=vulkan-1.dll\n");

    get_instance_proc_addr = (PFN_vkGetInstanceProcAddr)GetProcAddress(loader, "vkGetInstanceProcAddr");
    if (!get_instance_proc_addr)
        return fail(11, "resolve-vulkan-loader",
                    "vkGetInstanceProcAddr is not exported by vulkan-1.dll");

    enumerate_instance_version =
        (PFN_vkEnumerateInstanceVersion)get_instance_proc_addr(VK_NULL_HANDLE, "vkEnumerateInstanceVersion");
    enumerate_instance_extensions =
        (PFN_vkEnumerateInstanceExtensionProperties)get_instance_proc_addr(
            VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
    create_instance =
        (PFN_vkCreateInstance)get_instance_proc_addr(VK_NULL_HANDLE, "vkCreateInstance");
    if (!enumerate_instance_extensions || !create_instance)
        return fail(12, "resolve-global-functions",
                    "required Vulkan global entry points are unavailable");

    if (enumerate_instance_version) {
        vr = enumerate_instance_version(&loader_version);
        if (vr != VK_SUCCESS)
            return fail(13, "enumerate-instance-version",
                        "vkEnumerateInstanceVersion returned an error");
    }
    printf("LOADER_API=");
    print_version(loader_version);
    printf("\n");

    vr = enumerate_instance_extensions(NULL, &instance_ext_count, NULL);
    if (vr != VK_SUCCESS || !instance_ext_count)
        return fail(14, "enumerate-instance-extensions",
                    "no Vulkan instance extensions were reported");
    instance_exts = (VkExtensionProperties *)calloc(instance_ext_count, sizeof(*instance_exts));
    if (!instance_exts) return fail(15, "allocate", "instance extension allocation failed");
    vr = enumerate_instance_extensions(NULL, &instance_ext_count, instance_exts);
    if (vr != VK_SUCCESS)
        return fail(16, "enumerate-instance-extensions",
                    "could not read Vulkan instance extensions");

    printf("INSTANCE_EXTENSION_COUNT=%u\n", instance_ext_count);
    printf("HAS_KHR_SURFACE=%d\n",
           has_extension(instance_exts, instance_ext_count, VK_KHR_SURFACE_EXTENSION_NAME));
    printf("HAS_KHR_WIN32_SURFACE=%d\n",
           has_extension(instance_exts, instance_ext_count, VK_KHR_WIN32_SURFACE_EXTENSION_NAME));
#ifdef VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME
    printf("HAS_KHR_PORTABILITY_ENUMERATION=%d\n",
           has_extension(instance_exts, instance_ext_count,
                         VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME));
#endif
#ifdef VK_EXT_METAL_SURFACE_EXTENSION_NAME
    /* A healthy Wine guest normally sees Win32 surface semantics, not the
     * host-only Metal surface extension. Print this to catch accidental host
     * API leakage, but do not fail headless probing on it. */
    printf("GUEST_SEES_EXT_METAL_SURFACE=%d\n",
           has_extension(instance_exts, instance_ext_count,
                         VK_EXT_METAL_SURFACE_EXTENSION_NAME));
#endif

    {
        VkApplicationInfo app_info;
        VkInstanceCreateInfo create_info;
        const char *enabled[1];
        uint32_t enabled_count = 0;
        VkInstanceCreateFlags flags = 0;

        memset(&app_info, 0, sizeof(app_info));
        app_info.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app_info.pApplicationName = "Madeira Detroit Vulkan Probe";
        app_info.applicationVersion = VK_MAKE_VERSION(2, 0, 0);
        app_info.pEngineName = "Madeira";
        app_info.engineVersion = VK_MAKE_VERSION(1, 0, 0);
        app_info.apiVersion = loader_version >= VK_API_VERSION_1_1
                                  ? VK_API_VERSION_1_1
                                  : VK_API_VERSION_1_0;

#ifdef VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME
        if (has_extension(instance_exts, instance_ext_count,
                          VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME)) {
            enabled[enabled_count++] = VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME;
#ifdef VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR
            flags |= VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
#endif
        }
#endif

        memset(&create_info, 0, sizeof(create_info));
        create_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        create_info.flags = flags;
        create_info.pApplicationInfo = &app_info;
        create_info.enabledExtensionCount = enabled_count;
        create_info.ppEnabledExtensionNames = enabled_count ? enabled : NULL;

        vr = create_instance(&create_info, NULL, &instance);
        if (vr != VK_SUCCESS || instance == VK_NULL_HANDLE) {
            char msg[128];
            snprintf(msg, sizeof(msg), "vkCreateInstance failed (%d)", (int)vr);
            return fail(20, "create-instance", msg);
        }
    }
    printf("INSTANCE=PASS\n");

    destroy_instance = (PFN_vkDestroyInstance)get_instance_proc_addr(instance, "vkDestroyInstance");
    enumerate_physical_devices =
        (PFN_vkEnumeratePhysicalDevices)get_instance_proc_addr(instance, "vkEnumeratePhysicalDevices");
    get_physical_device_properties =
        (PFN_vkGetPhysicalDeviceProperties)get_instance_proc_addr(instance, "vkGetPhysicalDeviceProperties");
    get_memory_properties =
        (PFN_vkGetPhysicalDeviceMemoryProperties)get_instance_proc_addr(
            instance, "vkGetPhysicalDeviceMemoryProperties");
    get_queue_properties =
        (PFN_vkGetPhysicalDeviceQueueFamilyProperties)get_instance_proc_addr(
            instance, "vkGetPhysicalDeviceQueueFamilyProperties");
    enumerate_device_extensions =
        (PFN_vkEnumerateDeviceExtensionProperties)get_instance_proc_addr(
            instance, "vkEnumerateDeviceExtensionProperties");
    get_physical_device_features2 =
        (PFN_vkGetPhysicalDeviceFeatures2)get_instance_proc_addr(
            instance, "vkGetPhysicalDeviceFeatures2");
    create_device = (PFN_vkCreateDevice)get_instance_proc_addr(instance, "vkCreateDevice");
    if (!destroy_instance || !enumerate_physical_devices || !get_physical_device_properties ||
        !get_memory_properties || !get_queue_properties || !enumerate_device_extensions || !create_device)
        return fail(22, "resolve-instance-functions",
                    "one or more required instance/device entry points are missing");

    vr = enumerate_physical_devices(instance, &physical_count, NULL);
    if (vr != VK_SUCCESS || !physical_count)
        return fail(23, "enumerate-physical-devices",
                    "no Vulkan physical device reached the Windows guest");
    physical_devices = (VkPhysicalDevice *)calloc(physical_count, sizeof(*physical_devices));
    if (!physical_devices) return fail(24, "allocate", "physical-device allocation failed");
    vr = enumerate_physical_devices(instance, &physical_count, physical_devices);
    if (vr != VK_SUCCESS)
        return fail(25, "enumerate-physical-devices", "physical-device enumeration failed");

    printf("PHYSICAL_DEVICE_COUNT=%u\n", physical_count);
    for (i = 0; i < physical_count; ++i) {
        VkPhysicalDeviceProperties props;
        memset(&props, 0, sizeof(props));
        get_physical_device_properties(physical_devices[i], &props);
        printf("GPU_%u_NAME=%s\n", i, props.deviceName);
        printf("GPU_%u_VENDOR_ID=0x%04x\n", i, props.vendorID);
        printf("GPU_%u_DEVICE_ID=0x%04x\n", i, props.deviceID);
        printf("GPU_%u_API=", i);
        print_version(props.apiVersion);
        printf("\n");
    }

    {
        VkPhysicalDeviceMemoryProperties mem;
        uint64_t heap_total = 0;
        memset(&mem, 0, sizeof(mem));
        get_memory_properties(physical_devices[0], &mem);
        printf("MEMORY_HEAP_COUNT=%u\n", mem.memoryHeapCount);
        for (i = 0; i < mem.memoryHeapCount; ++i) {
            printf("MEMORY_HEAP_%u_BYTES=%llu\n", i,
                   (unsigned long long)mem.memoryHeaps[i].size);
            printf("MEMORY_HEAP_%u_FLAGS=0x%x\n", i, mem.memoryHeaps[i].flags);
            heap_total += (uint64_t)mem.memoryHeaps[i].size;
        }
        printf("MEMORY_HEAP_TOTAL_BYTES=%llu\n", (unsigned long long)heap_total);
    }

    get_queue_properties(physical_devices[0], &queue_count, NULL);
    if (!queue_count) return fail(26, "queue-families", "no Vulkan queue families were reported");
    queues = (VkQueueFamilyProperties *)calloc(queue_count, sizeof(*queues));
    if (!queues) return fail(27, "allocate", "queue-family allocation failed");
    get_queue_properties(physical_devices[0], &queue_count, queues);
    printf("QUEUE_FAMILY_COUNT=%u\n", queue_count);
    for (i = 0; i < queue_count; ++i) {
        printf("QUEUE_%u_FLAGS=0x%x\n", i, queues[i].queueFlags);
        printf("QUEUE_%u_COUNT=%u\n", i, queues[i].queueCount);
        if (graphics_queue == UINT32_MAX && queues[i].queueCount &&
            (queues[i].queueFlags & VK_QUEUE_GRAPHICS_BIT))
            graphics_queue = i;
    }
    if (graphics_queue == UINT32_MAX)
        return fail(28, "queue-families", "no graphics-capable Vulkan queue exists");
    printf("GRAPHICS_QUEUE_FAMILY=%u\n", graphics_queue);

    vr = enumerate_device_extensions(physical_devices[0], NULL, &device_ext_count, NULL);
    if (vr != VK_SUCCESS)
        return fail(29, "device-extensions", "could not count Vulkan device extensions");
    if (device_ext_count) {
        device_exts = (VkExtensionProperties *)calloc(device_ext_count, sizeof(*device_exts));
        if (!device_exts) return fail(30, "allocate", "device-extension allocation failed");
        vr = enumerate_device_extensions(physical_devices[0], NULL, &device_ext_count, device_exts);
        if (vr != VK_SUCCESS)
            return fail(31, "device-extensions", "could not read Vulkan device extensions");
    }
    printf("DEVICE_EXTENSION_COUNT=%u\n", device_ext_count);
    printf("HAS_KHR_SWAPCHAIN=%d\n",
           has_extension(device_exts, device_ext_count, VK_KHR_SWAPCHAIN_EXTENSION_NAME));
#ifdef VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME
    descriptor_indexing_available =
        has_extension(device_exts, device_ext_count, VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME);
    printf("HAS_EXT_DESCRIPTOR_INDEXING=%d\n", descriptor_indexing_available);
#else
    printf("HAS_EXT_DESCRIPTOR_INDEXING=0\n");
#endif
#ifdef VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME
    printf("HAS_KHR_PORTABILITY_SUBSET=%d\n",
           has_extension(device_exts, device_ext_count, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME));
#endif

    if (!descriptor_indexing_available)
        return fail(32, "detroit-capabilities",
                    "VK_EXT_descriptor_indexing is required by Detroit's renderer but is unavailable");

#ifdef VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME
    if (get_physical_device_features2) {
        VkPhysicalDeviceFeatures2 features2;
        VkPhysicalDeviceDescriptorIndexingFeatures descriptor_features;
        memset(&features2, 0, sizeof(features2));
        memset(&descriptor_features, 0, sizeof(descriptor_features));
        features2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
        descriptor_features.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES;
        features2.pNext = &descriptor_features;
        get_physical_device_features2(physical_devices[0], &features2);
        printf("DESCRIPTOR_INDEXING_SHADER_UNIFORM_BUFFER_NONUNIFORM=%u\n",
               descriptor_features.shaderUniformBufferArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_SAMPLED_IMAGE_NONUNIFORM=%u\n",
               descriptor_features.shaderSampledImageArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_STORAGE_BUFFER_NONUNIFORM=%u\n",
               descriptor_features.shaderStorageBufferArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_SHADER_STORAGE_IMAGE_NONUNIFORM=%u\n",
               descriptor_features.shaderStorageImageArrayNonUniformIndexing);
        printf("DESCRIPTOR_INDEXING_PARTIALLY_BOUND=%u\n",
               descriptor_features.descriptorBindingPartiallyBound);
        printf("DESCRIPTOR_INDEXING_VARIABLE_COUNT=%u\n",
               descriptor_features.descriptorBindingVariableDescriptorCount);
        printf("DESCRIPTOR_INDEXING_RUNTIME_ARRAY=%u\n",
               descriptor_features.runtimeDescriptorArray);
    } else {
        printf("DESCRIPTOR_INDEXING_FEATURE_QUERY=UNAVAILABLE\n");
    }
#endif

    {
        float priority = 1.0f;
        VkDeviceQueueCreateInfo queue_info;
        VkDeviceCreateInfo device_info;
        const char *enabled_device_exts[2];
        uint32_t enabled_device_ext_count = 0;

        enabled_device_exts[enabled_device_ext_count++] = VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME;
#ifdef VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME
        if (has_extension(device_exts, device_ext_count,
                          VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME))
            enabled_device_exts[enabled_device_ext_count++] =
                VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME;
#endif

        memset(&queue_info, 0, sizeof(queue_info));
        queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_info.queueFamilyIndex = graphics_queue;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        memset(&device_info, 0, sizeof(device_info));
        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        device_info.enabledExtensionCount = enabled_device_ext_count;
        device_info.ppEnabledExtensionNames = enabled_device_exts;
        vr = create_device(physical_devices[0], &device_info, NULL, &device);
        if (vr != VK_SUCCESS || device == VK_NULL_HANDLE) {
            char msg[160];
            snprintf(msg, sizeof(msg),
                     "vkCreateDevice with Detroit descriptor-indexing capability failed (%d)", (int)vr);
            return fail(33, "detroit-capabilities", msg);
        }
    }
    printf("LOGICAL_DEVICE=PASS\n");
    printf("DETROIT_DESCRIPTOR_INDEXING=PASS\n");

    destroy_device = (PFN_vkDestroyDevice)get_instance_proc_addr(instance, "vkDestroyDevice");
    if (!destroy_device)
        return fail(34, "destroy-device", "vkDestroyDevice could not be resolved");
    destroy_device(device, NULL);
    device = VK_NULL_HANDLE;
    destroy_instance(instance, NULL);
    instance = VK_NULL_HANDLE;

    free(queues);
    free(device_exts);
    free(physical_devices);
    free(instance_exts);
    FreeLibrary(loader);

    printf("RESULT=PASS\n");
    printf("NEXT_GATE=win32-surface-and-swapchain\n");
    return 0;
}