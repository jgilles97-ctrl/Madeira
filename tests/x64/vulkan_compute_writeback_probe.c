/*
 * vulkan_compute_writeback_probe.c
 *
 * Detroit/MoltenVK compute integrity canary for the physical iPad gate.
 *
 * Why this exists:
 *   Detroit uses compute shaders, while current MoltenVK has an open Apple-
 *   Silicon report where some compute dispatches can complete successfully yet
 *   lose storage-buffer writes when Metal argument buffers are enabled. Detroit
 *   also needs argument buffers for its very large bindless descriptor sets, so
 *   "turn argument buffers off" is not an acceptable qualification shortcut.
 *
 * This x86-64 Windows program therefore uses the guest vulkan-1.dll through the
 * same Wine/FEX/MoltenVK path as the game. It copies one known uint32_t from an
 * input storage buffer to an output storage buffer in a compute shader, waits for
 * completion, maps the output, and compares the exact value. Pipeline creation,
 * successful queue submission, or a signaled wait are NOT enough to pass.
 *
 * The compact SPIR-V program is adapted from Sheredom's public-domain
 * VkComputeSample (Unlicense/public domain), reduced to a one-element copy.
 * Source reference: https://gist.github.com/sheredom/523f02bbad2ae397d7ed255f3f3b5a7f
 */

#define WIN32_LEAN_AND_MEAN
#define VK_USE_PLATFORM_WIN32_KHR 1
#define VK_NO_PROTOTYPES 1
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define PROBE_SCHEMA "MADEIRA_VK_COMPUTE_WRITEBACK_V1"
#define EXPECTED_VALUE UINT32_C(0x13579bdf)
#define OUTPUT_SENTINEL UINT32_C(0xa5a5a5a5)

static PFN_vkGetInstanceProcAddr p_vkGetInstanceProcAddr;
static PFN_vkCreateInstance p_vkCreateInstance;
static PFN_vkDestroyInstance p_vkDestroyInstance;
static PFN_vkEnumeratePhysicalDevices p_vkEnumeratePhysicalDevices;
static PFN_vkGetPhysicalDeviceQueueFamilyProperties p_vkGetPhysicalDeviceQueueFamilyProperties;
static PFN_vkGetPhysicalDeviceMemoryProperties p_vkGetPhysicalDeviceMemoryProperties;
static PFN_vkEnumerateDeviceExtensionProperties p_vkEnumerateDeviceExtensionProperties;
static PFN_vkCreateDevice p_vkCreateDevice;
static PFN_vkGetDeviceProcAddr p_vkGetDeviceProcAddr;
static PFN_vkDestroyDevice p_vkDestroyDevice;
static PFN_vkGetDeviceQueue p_vkGetDeviceQueue;
static PFN_vkCreateBuffer p_vkCreateBuffer;
static PFN_vkDestroyBuffer p_vkDestroyBuffer;
static PFN_vkGetBufferMemoryRequirements p_vkGetBufferMemoryRequirements;
static PFN_vkAllocateMemory p_vkAllocateMemory;
static PFN_vkFreeMemory p_vkFreeMemory;
static PFN_vkBindBufferMemory p_vkBindBufferMemory;
static PFN_vkMapMemory p_vkMapMemory;
static PFN_vkUnmapMemory p_vkUnmapMemory;
static PFN_vkCreateShaderModule p_vkCreateShaderModule;
static PFN_vkDestroyShaderModule p_vkDestroyShaderModule;
static PFN_vkCreateDescriptorSetLayout p_vkCreateDescriptorSetLayout;
static PFN_vkDestroyDescriptorSetLayout p_vkDestroyDescriptorSetLayout;
static PFN_vkCreatePipelineLayout p_vkCreatePipelineLayout;
static PFN_vkDestroyPipelineLayout p_vkDestroyPipelineLayout;
static PFN_vkCreateComputePipelines p_vkCreateComputePipelines;
static PFN_vkDestroyPipeline p_vkDestroyPipeline;
static PFN_vkCreateDescriptorPool p_vkCreateDescriptorPool;
static PFN_vkDestroyDescriptorPool p_vkDestroyDescriptorPool;
static PFN_vkAllocateDescriptorSets p_vkAllocateDescriptorSets;
static PFN_vkUpdateDescriptorSets p_vkUpdateDescriptorSets;
static PFN_vkCreateCommandPool p_vkCreateCommandPool;
static PFN_vkDestroyCommandPool p_vkDestroyCommandPool;
static PFN_vkAllocateCommandBuffers p_vkAllocateCommandBuffers;
static PFN_vkBeginCommandBuffer p_vkBeginCommandBuffer;
static PFN_vkEndCommandBuffer p_vkEndCommandBuffer;
static PFN_vkCmdBindPipeline p_vkCmdBindPipeline;
static PFN_vkCmdBindDescriptorSets p_vkCmdBindDescriptorSets;
static PFN_vkCmdDispatch p_vkCmdDispatch;
static PFN_vkQueueSubmit p_vkQueueSubmit;
static PFN_vkQueueWaitIdle p_vkQueueWaitIdle;

static int fail(int code, const char *stage, const char *message)
{
    fprintf(stderr, "RESULT=FAIL\nSTAGE=%s\nERROR=%s\nEXIT_CODE=%d\n",
            stage, message, code);
    return code;
}

static int has_extension(const VkExtensionProperties *exts, uint32_t count,
                         const char *name)
{
    uint32_t i;
    for (i = 0; i < count; ++i)
        if (!strcmp(exts[i].extensionName, name)) return 1;
    return 0;
}

static int load_from_farproc(void *dst, size_t dst_size, FARPROC raw)
{
    if (!raw || dst_size != sizeof(raw)) return 0;
    memcpy(dst, &raw, dst_size);
    return 1;
}

static int load_global(HMODULE loader)
{
    FARPROC raw = GetProcAddress(loader, "vkGetInstanceProcAddr");
    if (!load_from_farproc(&p_vkGetInstanceProcAddr, sizeof(p_vkGetInstanceProcAddr), raw)) return 0;
    p_vkCreateInstance = (PFN_vkCreateInstance)p_vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance");
    return p_vkCreateInstance != NULL;
}

#define LOAD_INSTANCE(name) do { \
    p_##name = (PFN_##name)p_vkGetInstanceProcAddr(instance, #name); \
    if (!p_##name) return fail(20, "resolve-instance-functions", #name " unavailable"); \
} while (0)

#define LOAD_DEVICE(name) do { \
    p_##name = (PFN_##name)p_vkGetDeviceProcAddr(device, #name); \
    if (!p_##name) return fail(30, "resolve-device-functions", #name " unavailable"); \
} while (0)

typedef struct BufferAllocation {
    VkBuffer buffer;
    VkDeviceMemory memory;
} BufferAllocation;

static int choose_host_memory(VkPhysicalDevice physical, uint32_t type_bits,
                              uint32_t *type_index)
{
    VkPhysicalDeviceMemoryProperties props;
    uint32_t i;
    p_vkGetPhysicalDeviceMemoryProperties(physical, &props);
    for (i = 0; i < props.memoryTypeCount; ++i) {
        VkMemoryPropertyFlags flags = props.memoryTypes[i].propertyFlags;
        if ((type_bits & (1u << i)) &&
            (flags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) &&
            (flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) {
            *type_index = i;
            return 1;
        }
    }
    return 0;
}

static int create_host_storage_buffer(VkPhysicalDevice physical, VkDevice device,
                                      BufferAllocation *out)
{
    VkBufferCreateInfo bci;
    VkMemoryRequirements req;
    VkMemoryAllocateInfo mai;
    uint32_t type_index;
    VkResult vr;

    memset(out, 0, sizeof(*out));
    memset(&bci, 0, sizeof(bci));
    bci.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    bci.size = sizeof(uint32_t);
    bci.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
    bci.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    vr = p_vkCreateBuffer(device, &bci, NULL, &out->buffer);
    if (vr != VK_SUCCESS) return 0;

    p_vkGetBufferMemoryRequirements(device, out->buffer, &req);
    if (!choose_host_memory(physical, req.memoryTypeBits, &type_index)) return 0;

    memset(&mai, 0, sizeof(mai));
    mai.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    mai.allocationSize = req.size;
    mai.memoryTypeIndex = type_index;
    vr = p_vkAllocateMemory(device, &mai, NULL, &out->memory);
    if (vr != VK_SUCCESS) return 0;
    vr = p_vkBindBufferMemory(device, out->buffer, out->memory, 0);
    return vr == VK_SUCCESS;
}

static int write_u32(VkDevice device, VkDeviceMemory memory, uint32_t value)
{
    void *mapped = NULL;
    VkResult vr = p_vkMapMemory(device, memory, 0, sizeof(value), 0, &mapped);
    if (vr != VK_SUCCESS || !mapped) return 0;
    memcpy(mapped, &value, sizeof(value));
    p_vkUnmapMemory(device, memory);
    return 1;
}

static int read_u32(VkDevice device, VkDeviceMemory memory, uint32_t *value)
{
    void *mapped = NULL;
    VkResult vr = p_vkMapMemory(device, memory, 0, sizeof(*value), 0, &mapped);
    if (vr != VK_SUCCESS || !mapped) return 0;
    memcpy(value, mapped, sizeof(*value));
    p_vkUnmapMemory(device, memory);
    return 1;
}

/* Public-domain SPIR-V construction adapted from VkComputeSample. The shader
 * performs out[globalInvocationID.x] = in[globalInvocationID.x]. We dispatch
 * exactly one invocation and both buffers contain exactly one int32 element. */
static uint32_t *build_copy_shader(size_t *byte_size)
{
    enum {
        RESERVED_ID = 0,
        FUNC_ID,
        IN_ID,
        OUT_ID,
        GLOBAL_INVOCATION_ID,
        VOID_TYPE_ID,
        FUNC_TYPE_ID,
        INT_TYPE_ID,
        INT_ARRAY_TYPE_ID,
        STRUCT_ID,
        POINTER_TYPE_ID,
        ELEMENT_POINTER_TYPE_ID,
        INT_VECTOR_TYPE_ID,
        INT_VECTOR_POINTER_TYPE_ID,
        INT_POINTER_TYPE_ID,
        CONSTANT_ZERO_ID,
        CONSTANT_ARRAY_LENGTH_ID,
        LABEL_ID,
        IN_ELEMENT_ID,
        OUT_ELEMENT_ID,
        GLOBAL_INVOCATION_X_ID,
        GLOBAL_INVOCATION_X_PTR_ID,
        TEMP_LOADED_ID,
        BOUND
    };
    enum {
        INPUT = 1,
        UNIFORM = 2,
        BUFFER_BLOCK = 3,
        ARRAY_STRIDE = 6,
        BUILTIN = 11,
        BINDING = 33,
        DESCRIPTOR_SET = 34,
        OFFSET = 35,
        GLOBAL_INVOCATION = 28,
        OP_TYPE_VOID = 19,
        OP_TYPE_FUNCTION = 33,
        OP_TYPE_INT = 21,
        OP_TYPE_VECTOR = 23,
        OP_TYPE_ARRAY = 28,
        OP_TYPE_STRUCT = 30,
        OP_TYPE_POINTER = 32,
        OP_VARIABLE = 59,
        OP_DECORATE = 71,
        OP_MEMBER_DECORATE = 72,
        OP_FUNCTION = 54,
        OP_LABEL = 248,
        OP_ACCESS_CHAIN = 65,
        OP_CONSTANT = 43,
        OP_LOAD = 61,
        OP_STORE = 62,
        OP_RETURN = 253,
        OP_FUNCTION_END = 56,
        OP_CAPABILITY = 17,
        OP_MEMORY_MODEL = 14,
        OP_ENTRY_POINT = 15,
        OP_EXECUTION_MODE = 16,
    };
    static uint32_t shader[] = {
        0x07230203, 0x00010000, 0, BOUND, 0,
        (2u << 16) | OP_CAPABILITY, 1,
        (3u << 16) | OP_MEMORY_MODEL, 0, 0,
        (4u << 16) | OP_ENTRY_POINT, 5, FUNC_ID, 0x00000066,
        (6u << 16) | OP_EXECUTION_MODE, FUNC_ID, 17, 1, 1, 1,
        (3u << 16) | OP_DECORATE, STRUCT_ID, BUFFER_BLOCK,
        (4u << 16) | OP_DECORATE, GLOBAL_INVOCATION_ID, BUILTIN, GLOBAL_INVOCATION,
        (4u << 16) | OP_DECORATE, IN_ID, DESCRIPTOR_SET, 0,
        (4u << 16) | OP_DECORATE, IN_ID, BINDING, 0,
        (4u << 16) | OP_DECORATE, OUT_ID, DESCRIPTOR_SET, 0,
        (4u << 16) | OP_DECORATE, OUT_ID, BINDING, 1,
        (4u << 16) | OP_DECORATE, INT_ARRAY_TYPE_ID, ARRAY_STRIDE, 4,
        (5u << 16) | OP_MEMBER_DECORATE, STRUCT_ID, 0, OFFSET, 0,
        (2u << 16) | OP_TYPE_VOID, VOID_TYPE_ID,
        (3u << 16) | OP_TYPE_FUNCTION, FUNC_TYPE_ID, VOID_TYPE_ID,
        (4u << 16) | OP_TYPE_INT, INT_TYPE_ID, 32, 1,
        (4u << 16) | OP_CONSTANT, INT_TYPE_ID, CONSTANT_ARRAY_LENGTH_ID, 1,
        (4u << 16) | OP_TYPE_ARRAY, INT_ARRAY_TYPE_ID, INT_TYPE_ID, CONSTANT_ARRAY_LENGTH_ID,
        (3u << 16) | OP_TYPE_STRUCT, STRUCT_ID, INT_ARRAY_TYPE_ID,
        (4u << 16) | OP_TYPE_POINTER, POINTER_TYPE_ID, UNIFORM, STRUCT_ID,
        (4u << 16) | OP_TYPE_POINTER, ELEMENT_POINTER_TYPE_ID, UNIFORM, INT_TYPE_ID,
        (4u << 16) | OP_TYPE_VECTOR, INT_VECTOR_TYPE_ID, INT_TYPE_ID, 3,
        (4u << 16) | OP_TYPE_POINTER, INT_VECTOR_POINTER_TYPE_ID, INPUT, INT_VECTOR_TYPE_ID,
        (4u << 16) | OP_TYPE_POINTER, INT_POINTER_TYPE_ID, INPUT, INT_TYPE_ID,
        (4u << 16) | OP_CONSTANT, INT_TYPE_ID, CONSTANT_ZERO_ID, 0,
        (4u << 16) | OP_VARIABLE, POINTER_TYPE_ID, IN_ID, UNIFORM,
        (4u << 16) | OP_VARIABLE, POINTER_TYPE_ID, OUT_ID, UNIFORM,
        (4u << 16) | OP_VARIABLE, INT_VECTOR_POINTER_TYPE_ID, GLOBAL_INVOCATION_ID, INPUT,
        (5u << 16) | OP_FUNCTION, VOID_TYPE_ID, FUNC_ID, 0, FUNC_TYPE_ID,
        (2u << 16) | OP_LABEL, LABEL_ID,
        (5u << 16) | OP_ACCESS_CHAIN, INT_POINTER_TYPE_ID, GLOBAL_INVOCATION_X_PTR_ID,
            GLOBAL_INVOCATION_ID, CONSTANT_ZERO_ID,
        (4u << 16) | OP_LOAD, INT_TYPE_ID, GLOBAL_INVOCATION_X_ID, GLOBAL_INVOCATION_X_PTR_ID,
        (6u << 16) | OP_ACCESS_CHAIN, ELEMENT_POINTER_TYPE_ID, IN_ELEMENT_ID,
            IN_ID, CONSTANT_ZERO_ID, GLOBAL_INVOCATION_X_ID,
        (4u << 16) | OP_LOAD, INT_TYPE_ID, TEMP_LOADED_ID, IN_ELEMENT_ID,
        (6u << 16) | OP_ACCESS_CHAIN, ELEMENT_POINTER_TYPE_ID, OUT_ELEMENT_ID,
            OUT_ID, CONSTANT_ZERO_ID, GLOBAL_INVOCATION_X_ID,
        (3u << 16) | OP_STORE, OUT_ELEMENT_ID, TEMP_LOADED_ID,
        (1u << 16) | OP_RETURN,
        (1u << 16) | OP_FUNCTION_END,
    };
    *byte_size = sizeof(shader);
    return shader;
}

int main(void)
{
    HMODULE loader = NULL;
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    VkShaderModule shader_module = VK_NULL_HANDLE;
    VkDescriptorSetLayout set_layout = VK_NULL_HANDLE;
    VkPipelineLayout pipeline_layout = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkDescriptorPool descriptor_pool = VK_NULL_HANDLE;
    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;
    VkCommandPool command_pool = VK_NULL_HANDLE;
    VkCommandBuffer command_buffer = VK_NULL_HANDLE;
    BufferAllocation input = {0}, output = {0};
    VkExtensionProperties *device_exts = NULL;
    uint32_t physical_count = 0, queue_count = 0, queue_family = UINT32_MAX;
    uint32_t device_ext_count = 0, i;
    VkResult vr;
    uint32_t observed = OUTPUT_SENTINEL;
    int rc = 0;

    printf("SCHEMA=%s\n", PROBE_SCHEMA);
    printf("ARCH=x86_64-windows\n");
    printf("PURPOSE=prove-compute-device-stores-survive-MoltenVK-argument-buffer-path\n");
    printf("EXPECTED_VALUE=0x%08x\n", EXPECTED_VALUE);
    printf("OUTPUT_SENTINEL=0x%08x\n", OUTPUT_SENTINEL);

    /* This is intentionally explicit even though MoltenVK currently defaults to
     * argument buffers when supported. It prevents the canary from accidentally
     * testing the legacy descriptor path after a default/config change. */
    if (!SetEnvironmentVariableA("MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS", "1"))
        return fail(10, "argument-buffer-config", "could not force Metal argument buffers on for the canary");
    printf("MOLTENVK_ARGUMENT_BUFFERS_REQUESTED=1\n");

    loader = LoadLibraryA("vulkan-1.dll");
    if (!loader) return fail(11, "load-vulkan-loader", "LoadLibraryA(vulkan-1.dll) failed");
    if (!load_global(loader)) return fail(12, "resolve-vulkan-loader", "Vulkan global entry points unavailable");

    {
        VkApplicationInfo ai;
        VkInstanceCreateInfo ici;
        memset(&ai, 0, sizeof(ai));
        memset(&ici, 0, sizeof(ici));
        ai.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        ai.pApplicationName = "Madeira Detroit Compute Writeback";
        ai.apiVersion = VK_API_VERSION_1_1;
        ici.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        ici.pApplicationInfo = &ai;
        vr = p_vkCreateInstance(&ici, NULL, &instance);
        if (vr != VK_SUCCESS) return fail(13, "create-instance", "vkCreateInstance failed");
    }

    LOAD_INSTANCE(vkDestroyInstance);
    LOAD_INSTANCE(vkEnumeratePhysicalDevices);
    LOAD_INSTANCE(vkGetPhysicalDeviceQueueFamilyProperties);
    LOAD_INSTANCE(vkGetPhysicalDeviceMemoryProperties);
    LOAD_INSTANCE(vkEnumerateDeviceExtensionProperties);
    LOAD_INSTANCE(vkCreateDevice);
    LOAD_INSTANCE(vkGetDeviceProcAddr);

    vr = p_vkEnumeratePhysicalDevices(instance, &physical_count, NULL);
    if (vr != VK_SUCCESS || !physical_count)
        return fail(21, "physical-device", "no Vulkan physical device available");
    {
        VkPhysicalDevice *devices = calloc(physical_count, sizeof(*devices));
        if (!devices) return fail(22, "allocate", "physical device list allocation failed");
        vr = p_vkEnumeratePhysicalDevices(instance, &physical_count, devices);
        if (vr != VK_SUCCESS) { free(devices); return fail(23, "physical-device", "physical device enumeration failed"); }
        physical = devices[0];
        free(devices);
    }

    p_vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, NULL);
    if (!queue_count) return fail(24, "compute-queue", "no queue families reported");
    {
        VkQueueFamilyProperties *queues = calloc(queue_count, sizeof(*queues));
        if (!queues) return fail(25, "allocate", "queue list allocation failed");
        p_vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, queues);
        for (i = 0; i < queue_count; ++i) {
            if (queues[i].queueCount && (queues[i].queueFlags & VK_QUEUE_COMPUTE_BIT)) {
                queue_family = i;
                break;
            }
        }
        free(queues);
    }
    if (queue_family == UINT32_MAX)
        return fail(26, "compute-queue", "no compute-capable queue exists");
    printf("COMPUTE_QUEUE_FAMILY=%u\n", queue_family);

    vr = p_vkEnumerateDeviceExtensionProperties(physical, NULL, &device_ext_count, NULL);
    if (vr != VK_SUCCESS) return fail(27, "device-extensions", "could not count device extensions");
    if (device_ext_count) {
        device_exts = calloc(device_ext_count, sizeof(*device_exts));
        if (!device_exts) return fail(28, "allocate", "device extension list allocation failed");
        vr = p_vkEnumerateDeviceExtensionProperties(physical, NULL, &device_ext_count, device_exts);
        if (vr != VK_SUCCESS) return fail(29, "device-extensions", "could not read device extensions");
    }

    {
        float priority = 1.0f;
        VkDeviceQueueCreateInfo qci;
        VkDeviceCreateInfo dci;
        const char *extensions[1];
        uint32_t extension_count = 0;
        memset(&qci, 0, sizeof(qci));
        memset(&dci, 0, sizeof(dci));
#ifdef VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME
        if (has_extension(device_exts, device_ext_count, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME))
            extensions[extension_count++] = VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME;
#endif
        qci.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        qci.queueFamilyIndex = queue_family;
        qci.queueCount = 1;
        qci.pQueuePriorities = &priority;
        dci.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        dci.queueCreateInfoCount = 1;
        dci.pQueueCreateInfos = &qci;
        dci.enabledExtensionCount = extension_count;
        dci.ppEnabledExtensionNames = extension_count ? extensions : NULL;
        vr = p_vkCreateDevice(physical, &dci, NULL, &device);
        if (vr != VK_SUCCESS) return fail(31, "create-device", "vkCreateDevice failed");
    }
    free(device_exts);
    device_exts = NULL;

    LOAD_DEVICE(vkDestroyDevice);
    LOAD_DEVICE(vkGetDeviceQueue);
    LOAD_DEVICE(vkCreateBuffer);
    LOAD_DEVICE(vkDestroyBuffer);
    LOAD_DEVICE(vkGetBufferMemoryRequirements);
    LOAD_DEVICE(vkAllocateMemory);
    LOAD_DEVICE(vkFreeMemory);
    LOAD_DEVICE(vkBindBufferMemory);
    LOAD_DEVICE(vkMapMemory);
    LOAD_DEVICE(vkUnmapMemory);
    LOAD_DEVICE(vkCreateShaderModule);
    LOAD_DEVICE(vkDestroyShaderModule);
    LOAD_DEVICE(vkCreateDescriptorSetLayout);
    LOAD_DEVICE(vkDestroyDescriptorSetLayout);
    LOAD_DEVICE(vkCreatePipelineLayout);
    LOAD_DEVICE(vkDestroyPipelineLayout);
    LOAD_DEVICE(vkCreateComputePipelines);
    LOAD_DEVICE(vkDestroyPipeline);
    LOAD_DEVICE(vkCreateDescriptorPool);
    LOAD_DEVICE(vkDestroyDescriptorPool);
    LOAD_DEVICE(vkAllocateDescriptorSets);
    LOAD_DEVICE(vkUpdateDescriptorSets);
    LOAD_DEVICE(vkCreateCommandPool);
    LOAD_DEVICE(vkDestroyCommandPool);
    LOAD_DEVICE(vkAllocateCommandBuffers);
    LOAD_DEVICE(vkBeginCommandBuffer);
    LOAD_DEVICE(vkEndCommandBuffer);
    LOAD_DEVICE(vkCmdBindPipeline);
    LOAD_DEVICE(vkCmdBindDescriptorSets);
    LOAD_DEVICE(vkCmdDispatch);
    LOAD_DEVICE(vkQueueSubmit);
    LOAD_DEVICE(vkQueueWaitIdle);

    p_vkGetDeviceQueue(device, queue_family, 0, &queue);
    if (!queue) return fail(32, "compute-queue", "vkGetDeviceQueue returned NULL");

    if (!create_host_storage_buffer(physical, device, &input) ||
        !create_host_storage_buffer(physical, device, &output))
        return fail(33, "storage-buffer", "host-visible coherent storage buffer creation failed");
    if (!write_u32(device, input.memory, EXPECTED_VALUE) ||
        !write_u32(device, output.memory, OUTPUT_SENTINEL))
        return fail(34, "storage-buffer", "could not initialize compute canary buffers");

    {
        size_t shader_bytes;
        uint32_t *shader = build_copy_shader(&shader_bytes);
        VkShaderModuleCreateInfo smci;
        memset(&smci, 0, sizeof(smci));
        smci.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        smci.codeSize = shader_bytes;
        smci.pCode = shader;
        vr = p_vkCreateShaderModule(device, &smci, NULL, &shader_module);
        if (vr != VK_SUCCESS) return fail(35, "compute-shader", "vkCreateShaderModule failed");
    }

    {
        VkDescriptorSetLayoutBinding bindings[2];
        VkDescriptorSetLayoutCreateInfo slci;
        VkPipelineLayoutCreateInfo plci;
        VkComputePipelineCreateInfo cpci;
        memset(bindings, 0, sizeof(bindings));
        bindings[0].binding = 0;
        bindings[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        bindings[0].descriptorCount = 1;
        bindings[0].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
        bindings[1].binding = 1;
        bindings[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        bindings[1].descriptorCount = 1;
        bindings[1].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
        memset(&slci, 0, sizeof(slci));
        slci.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        slci.bindingCount = 2;
        slci.pBindings = bindings;
        vr = p_vkCreateDescriptorSetLayout(device, &slci, NULL, &set_layout);
        if (vr != VK_SUCCESS) return fail(36, "compute-pipeline", "descriptor set layout creation failed");

        memset(&plci, 0, sizeof(plci));
        plci.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        plci.setLayoutCount = 1;
        plci.pSetLayouts = &set_layout;
        vr = p_vkCreatePipelineLayout(device, &plci, NULL, &pipeline_layout);
        if (vr != VK_SUCCESS) return fail(37, "compute-pipeline", "pipeline layout creation failed");

        memset(&cpci, 0, sizeof(cpci));
        cpci.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
        cpci.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        cpci.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        cpci.stage.module = shader_module;
        cpci.stage.pName = "f";
        cpci.layout = pipeline_layout;
        vr = p_vkCreateComputePipelines(device, VK_NULL_HANDLE, 1, &cpci, NULL, &pipeline);
        if (vr != VK_SUCCESS) return fail(38, "compute-pipeline", "vkCreateComputePipelines failed");
    }
    printf("COMPUTE_PIPELINE=PASS\n");

    {
        VkDescriptorPoolSize pool_size;
        VkDescriptorPoolCreateInfo dpci;
        VkDescriptorSetAllocateInfo dsai;
        VkDescriptorBufferInfo infos[2];
        VkWriteDescriptorSet writes[2];
        memset(&pool_size, 0, sizeof(pool_size));
        pool_size.type = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        pool_size.descriptorCount = 2;
        memset(&dpci, 0, sizeof(dpci));
        dpci.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
        dpci.maxSets = 1;
        dpci.poolSizeCount = 1;
        dpci.pPoolSizes = &pool_size;
        vr = p_vkCreateDescriptorPool(device, &dpci, NULL, &descriptor_pool);
        if (vr != VK_SUCCESS) return fail(39, "compute-descriptors", "descriptor pool creation failed");

        memset(&dsai, 0, sizeof(dsai));
        dsai.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        dsai.descriptorPool = descriptor_pool;
        dsai.descriptorSetCount = 1;
        dsai.pSetLayouts = &set_layout;
        vr = p_vkAllocateDescriptorSets(device, &dsai, &descriptor_set);
        if (vr != VK_SUCCESS) return fail(40, "compute-descriptors", "descriptor set allocation failed");

        memset(infos, 0, sizeof(infos));
        infos[0].buffer = input.buffer;
        infos[0].range = sizeof(uint32_t);
        infos[1].buffer = output.buffer;
        infos[1].range = sizeof(uint32_t);
        memset(writes, 0, sizeof(writes));
        for (i = 0; i < 2; ++i) {
            writes[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
            writes[i].dstSet = descriptor_set;
            writes[i].dstBinding = i;
            writes[i].descriptorCount = 1;
            writes[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
            writes[i].pBufferInfo = &infos[i];
        }
        p_vkUpdateDescriptorSets(device, 2, writes, 0, NULL);
    }

    {
        VkCommandPoolCreateInfo cpci;
        VkCommandBufferAllocateInfo cbai;
        VkCommandBufferBeginInfo cbbi;
        VkSubmitInfo submit;
        memset(&cpci, 0, sizeof(cpci));
        cpci.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        cpci.queueFamilyIndex = queue_family;
        vr = p_vkCreateCommandPool(device, &cpci, NULL, &command_pool);
        if (vr != VK_SUCCESS) return fail(41, "compute-command", "command pool creation failed");

        memset(&cbai, 0, sizeof(cbai));
        cbai.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        cbai.commandPool = command_pool;
        cbai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        cbai.commandBufferCount = 1;
        vr = p_vkAllocateCommandBuffers(device, &cbai, &command_buffer);
        if (vr != VK_SUCCESS) return fail(42, "compute-command", "command buffer allocation failed");

        memset(&cbbi, 0, sizeof(cbbi));
        cbbi.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        cbbi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        vr = p_vkBeginCommandBuffer(command_buffer, &cbbi);
        if (vr != VK_SUCCESS) return fail(43, "compute-command", "vkBeginCommandBuffer failed");
        p_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        p_vkCmdBindDescriptorSets(command_buffer, VK_PIPELINE_BIND_POINT_COMPUTE,
                                  pipeline_layout, 0, 1, &descriptor_set, 0, NULL);
        p_vkCmdDispatch(command_buffer, 1, 1, 1);
        vr = p_vkEndCommandBuffer(command_buffer);
        if (vr != VK_SUCCESS) return fail(44, "compute-command", "vkEndCommandBuffer failed");

        memset(&submit, 0, sizeof(submit));
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &command_buffer;
        vr = p_vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE);
        if (vr != VK_SUCCESS) return fail(45, "compute-dispatch", "vkQueueSubmit failed");
        vr = p_vkQueueWaitIdle(queue);
        if (vr != VK_SUCCESS) return fail(46, "compute-dispatch", "vkQueueWaitIdle failed");
    }
    printf("COMPUTE_DISPATCH=PASS\n");

    if (!read_u32(device, output.memory, &observed))
        return fail(47, "compute-readback", "could not map output buffer after compute dispatch");
    printf("OBSERVED_VALUE=0x%08x\n", observed);
    if (observed != EXPECTED_VALUE) {
        char message[192];
        snprintf(message, sizeof(message),
                 "compute dispatch completed but storage write was lost: expected=0x%08x observed=0x%08x",
                 EXPECTED_VALUE, observed);
        return fail(48, "compute-writeback-integrity", message);
    }

    printf("COMPUTE_WRITEBACK_VALUE=PASS\n");
    printf("MOLTENVK_ARGUMENT_BUFFER_COMPUTE_INTEGRITY=PASS\n");
    printf("RESULT=PASS\n");
    printf("NEXT_GATE=win32-surface\n");

    /* Best-effort cleanup after the result has been proven. */
    if (command_pool) p_vkDestroyCommandPool(device, command_pool, NULL);
    if (descriptor_pool) p_vkDestroyDescriptorPool(device, descriptor_pool, NULL);
    if (pipeline) p_vkDestroyPipeline(device, pipeline, NULL);
    if (pipeline_layout) p_vkDestroyPipelineLayout(device, pipeline_layout, NULL);
    if (set_layout) p_vkDestroyDescriptorSetLayout(device, set_layout, NULL);
    if (shader_module) p_vkDestroyShaderModule(device, shader_module, NULL);
    if (input.buffer) p_vkDestroyBuffer(device, input.buffer, NULL);
    if (input.memory) p_vkFreeMemory(device, input.memory, NULL);
    if (output.buffer) p_vkDestroyBuffer(device, output.buffer, NULL);
    if (output.memory) p_vkFreeMemory(device, output.memory, NULL);
    if (device) p_vkDestroyDevice(device, NULL);
    if (instance) p_vkDestroyInstance(instance, NULL);
    if (loader) FreeLibrary(loader);
    return rc;
}
