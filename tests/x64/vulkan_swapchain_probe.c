/*
 * vulkan_swapchain_probe.c - prove the full Madeira Vulkan presentation path.
 *
 * This Windows x86-64 canary deliberately uses LoadLibrary(vulkan-1.dll) and
 * VK_KHR_win32_surface, then creates a real swapchain, clears its images with a
 * render pass (no shaders needed), and presents 120 frames. A PASS therefore
 * proves much more than extension enumeration: guest Win32 window -> Wine WSI
 * -> iOS CAMetalLayer -> MoltenVK -> Metal presentation is alive.
 */

#define WIN32_LEAN_AND_MEAN
#define VK_USE_PLATFORM_WIN32_KHR 1
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define PROBE_SCHEMA "MADEIRA_VK_SWAPCHAIN_PROBE_V1"
#define WINDOW_CLASS "MadeiraVulkanSwapchainProbe"
#define TARGET_FRAMES 120u

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

/* MinGW GCC diagnoses a direct FARPROC -> Vulkan-function cast under
 * -Wcast-function-type. Function pointers have the same representation on the
 * Windows ABI here, so copy the representation instead of casting it. */
static PFN_vkGetInstanceProcAddr resolve_gip(HMODULE module)
{
    FARPROC raw = GetProcAddress(module, "vkGetInstanceProcAddr");
    PFN_vkGetInstanceProcAddr out = NULL;
    if (!raw) return NULL;
    if (sizeof(out) != sizeof(raw)) return NULL;
    memcpy(&out, &raw, sizeof(out));
    return out;
}

static LRESULT CALLBACK wnd_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)
{
    (void)wparam;
    (void)lparam;
    if (msg == WM_CLOSE) {
        DestroyWindow(hwnd);
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wparam, lparam);
}

static void pump_messages(int *closed)
{
    MSG msg;
    while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
        if (msg.message == WM_QUIT) *closed = 1;
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
}

static uint32_t clamp_u32(uint32_t value, uint32_t lo, uint32_t hi)
{
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

int main(void)
{
    HINSTANCE hinstance = GetModuleHandleA(NULL);
    WNDCLASSEXA wc;
    HWND hwnd = NULL;
    HMODULE loader = NULL;
    VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    VkRenderPass render_pass = VK_NULL_HANDLE;
    VkCommandPool command_pool = VK_NULL_HANDLE;
    VkSemaphore acquire_sem = VK_NULL_HANDLE;
    VkSemaphore render_sem = VK_NULL_HANDLE;
    VkFence frame_fence = VK_NULL_HANDLE;
    VkExtensionProperties *instance_exts = NULL;
    VkPhysicalDevice *physical_devices = NULL;
    VkQueueFamilyProperties *queue_props = NULL;
    VkExtensionProperties *device_exts = NULL;
    VkSurfaceFormatKHR *formats = NULL;
    VkPresentModeKHR *present_modes = NULL;
    VkImage *images = NULL;
    VkImageView *views = NULL;
    VkFramebuffer *framebuffers = NULL;
    VkCommandBuffer *cmds = NULL;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    uint32_t queue_family = UINT32_MAX;
    uint32_t instance_ext_count = 0, physical_count = 0, queue_count = 0;
    uint32_t device_ext_count = 0, format_count = 0, present_mode_count = 0;
    uint32_t image_count = 0, i;
    VkSurfaceCapabilitiesKHR caps;
    VkSurfaceFormatKHR chosen_format;
    VkExtent2D extent;
    VkResult vr;
    int rc = 0, closed = 0;

    PFN_vkGetInstanceProcAddr gip = NULL;
    PFN_vkGetDeviceProcAddr gdp = NULL;
    PFN_vkEnumerateInstanceExtensionProperties enum_instance_exts = NULL;
    PFN_vkCreateInstance create_instance = NULL;
    PFN_vkDestroyInstance destroy_instance = NULL;
    PFN_vkCreateWin32SurfaceKHR create_win32_surface = NULL;
    PFN_vkDestroySurfaceKHR destroy_surface = NULL;
    PFN_vkEnumeratePhysicalDevices enum_physical = NULL;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_props = NULL;
    PFN_vkGetPhysicalDeviceSurfaceSupportKHR get_surface_support = NULL;
    PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR get_surface_caps = NULL;
    PFN_vkGetPhysicalDeviceSurfaceFormatsKHR get_surface_formats = NULL;
    PFN_vkGetPhysicalDeviceSurfacePresentModesKHR get_present_modes = NULL;
    PFN_vkEnumerateDeviceExtensionProperties enum_device_exts = NULL;
    PFN_vkCreateDevice create_device = NULL;
    PFN_vkDestroyDevice destroy_device = NULL;
    PFN_vkGetDeviceQueue get_device_queue = NULL;
    PFN_vkCreateSwapchainKHR create_swapchain = NULL;
    PFN_vkDestroySwapchainKHR destroy_swapchain = NULL;
    PFN_vkGetSwapchainImagesKHR get_swapchain_images = NULL;
    PFN_vkAcquireNextImageKHR acquire_next_image = NULL;
    PFN_vkQueuePresentKHR queue_present = NULL;
    PFN_vkCreateImageView create_image_view = NULL;
    PFN_vkDestroyImageView destroy_image_view = NULL;
    PFN_vkCreateRenderPass create_render_pass = NULL;
    PFN_vkDestroyRenderPass destroy_render_pass = NULL;
    PFN_vkCreateFramebuffer create_framebuffer = NULL;
    PFN_vkDestroyFramebuffer destroy_framebuffer = NULL;
    PFN_vkCreateCommandPool create_command_pool = NULL;
    PFN_vkDestroyCommandPool destroy_command_pool = NULL;
    PFN_vkAllocateCommandBuffers allocate_cmds = NULL;
    PFN_vkBeginCommandBuffer begin_cmd = NULL;
    PFN_vkEndCommandBuffer end_cmd = NULL;
    PFN_vkCmdBeginRenderPass cmd_begin_render_pass = NULL;
    PFN_vkCmdEndRenderPass cmd_end_render_pass = NULL;
    PFN_vkCreateSemaphore create_semaphore = NULL;
    PFN_vkDestroySemaphore destroy_semaphore = NULL;
    PFN_vkCreateFence create_fence = NULL;
    PFN_vkDestroyFence destroy_fence = NULL;
    PFN_vkWaitForFences wait_fences = NULL;
    PFN_vkResetFences reset_fences = NULL;
    PFN_vkQueueSubmit queue_submit = NULL;
    PFN_vkDeviceWaitIdle device_wait_idle = NULL;

#define RESOLVE_INSTANCE(var, name, type) \
    do { \
        var = (type)gip(instance, name); \
        if (!(var)) { rc = fail(40, "resolve-instance-function", "missing " name); goto done; } \
    } while (0)
#define RESOLVE_DEVICE(var, name, type) \
    do { \
        var = (type)gdp(device, name); \
        if (!(var)) { rc = fail(60, "resolve-device-function", "missing " name); goto done; } \
    } while (0)

    printf("SCHEMA=%s\n", PROBE_SCHEMA);
    printf("ARCH=x86_64-windows\n");
    printf("TARGET_FRAMES=%u\n", TARGET_FRAMES);

    memset(&wc, 0, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.hInstance = hinstance;
    wc.lpfnWndProc = wnd_proc;
    wc.lpszClassName = WINDOW_CLASS;
    if (!RegisterClassExA(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
        return fail(10, "register-window-class", "RegisterClassExA failed");

    hwnd = CreateWindowExA(0, WINDOW_CLASS, "Madeira Vulkan Swapchain Probe",
                           WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                           640, 360, NULL, NULL, hinstance, NULL);
    if (!hwnd) return fail(11, "create-window", "CreateWindowExA failed");
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    printf("WIN32_WINDOW=PASS\n");

    loader = LoadLibraryA("vulkan-1.dll");
    if (!loader) { rc = fail(12, "load-vulkan-loader", "vulkan-1.dll is missing"); goto done; }
    gip = resolve_gip(loader);
    if (!gip) { rc = fail(13, "resolve-vulkan-loader", "vkGetInstanceProcAddr is missing"); goto done; }
    enum_instance_exts = (PFN_vkEnumerateInstanceExtensionProperties)
        gip(VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
    create_instance = (PFN_vkCreateInstance)gip(VK_NULL_HANDLE, "vkCreateInstance");
    if (!enum_instance_exts || !create_instance) {
        rc = fail(14, "resolve-global-functions", "required global Vulkan functions are missing");
        goto done;
    }

    vr = enum_instance_exts(NULL, &instance_ext_count, NULL);
    if (vr != VK_SUCCESS || !instance_ext_count) {
        rc = fail(15, "enumerate-instance-extensions", "no instance extensions reported");
        goto done;
    }
    instance_exts = (VkExtensionProperties *)calloc(instance_ext_count, sizeof(*instance_exts));
    if (!instance_exts) { rc = fail(16, "allocate", "instance extension allocation failed"); goto done; }
    vr = enum_instance_exts(NULL, &instance_ext_count, instance_exts);
    if (vr != VK_SUCCESS) { rc = fail(17, "enumerate-instance-extensions", "instance extension read failed"); goto done; }
    if (!has_extension(instance_exts, instance_ext_count, VK_KHR_SURFACE_EXTENSION_NAME) ||
        !has_extension(instance_exts, instance_ext_count, VK_KHR_WIN32_SURFACE_EXTENSION_NAME)) {
        rc = fail(18, "guest-wsi-extensions", "VK_KHR_surface/VK_KHR_win32_surface missing");
        goto done;
    }

    {
        VkApplicationInfo app;
        VkInstanceCreateInfo ci;
        const char *enabled[3];
        uint32_t enabled_count = 0;
        VkInstanceCreateFlags flags = 0;
        memset(&app, 0, sizeof(app));
        app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.pApplicationName = "Madeira Vulkan Swapchain Probe";
        app.apiVersion = VK_API_VERSION_1_1;
        enabled[enabled_count++] = VK_KHR_SURFACE_EXTENSION_NAME;
        enabled[enabled_count++] = VK_KHR_WIN32_SURFACE_EXTENSION_NAME;
#ifdef VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME
        if (has_extension(instance_exts, instance_ext_count, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME)) {
            enabled[enabled_count++] = VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME;
#ifdef VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR
            flags |= VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
#endif
        }
#endif
        memset(&ci, 0, sizeof(ci));
        ci.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        ci.flags = flags;
        ci.pApplicationInfo = &app;
        ci.enabledExtensionCount = enabled_count;
        ci.ppEnabledExtensionNames = enabled;
        vr = create_instance(&ci, NULL, &instance);
        if (vr != VK_SUCCESS || instance == VK_NULL_HANDLE) {
            char msg[96]; snprintf(msg, sizeof(msg), "vkCreateInstance failed (%d)", (int)vr);
            rc = fail(19, "create-instance", msg); goto done;
        }
    }
    printf("INSTANCE=PASS\n");

    RESOLVE_INSTANCE(destroy_instance, "vkDestroyInstance", PFN_vkDestroyInstance);
    RESOLVE_INSTANCE(create_win32_surface, "vkCreateWin32SurfaceKHR", PFN_vkCreateWin32SurfaceKHR);
    RESOLVE_INSTANCE(destroy_surface, "vkDestroySurfaceKHR", PFN_vkDestroySurfaceKHR);
    RESOLVE_INSTANCE(enum_physical, "vkEnumeratePhysicalDevices", PFN_vkEnumeratePhysicalDevices);
    RESOLVE_INSTANCE(get_queue_props, "vkGetPhysicalDeviceQueueFamilyProperties", PFN_vkGetPhysicalDeviceQueueFamilyProperties);
    RESOLVE_INSTANCE(get_surface_support, "vkGetPhysicalDeviceSurfaceSupportKHR", PFN_vkGetPhysicalDeviceSurfaceSupportKHR);
    RESOLVE_INSTANCE(get_surface_caps, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR", PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR);
    RESOLVE_INSTANCE(get_surface_formats, "vkGetPhysicalDeviceSurfaceFormatsKHR", PFN_vkGetPhysicalDeviceSurfaceFormatsKHR);
    RESOLVE_INSTANCE(get_present_modes, "vkGetPhysicalDeviceSurfacePresentModesKHR", PFN_vkGetPhysicalDeviceSurfacePresentModesKHR);
    RESOLVE_INSTANCE(enum_device_exts, "vkEnumerateDeviceExtensionProperties", PFN_vkEnumerateDeviceExtensionProperties);
    RESOLVE_INSTANCE(create_device, "vkCreateDevice", PFN_vkCreateDevice);
    gdp = (PFN_vkGetDeviceProcAddr)gip(instance, "vkGetDeviceProcAddr");
    if (!gdp) { rc = fail(41, "resolve-instance-function", "missing vkGetDeviceProcAddr"); goto done; }

    {
        VkWin32SurfaceCreateInfoKHR sci;
        memset(&sci, 0, sizeof(sci));
        sci.sType = VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR;
        sci.hinstance = hinstance;
        sci.hwnd = hwnd;
        vr = create_win32_surface(instance, &sci, NULL, &surface);
        if (vr != VK_SUCCESS || surface == VK_NULL_HANDLE) {
            char msg[96]; snprintf(msg, sizeof(msg), "vkCreateWin32SurfaceKHR failed (%d)", (int)vr);
            rc = fail(20, "create-win32-surface", msg); goto done;
        }
    }
    printf("WIN32_SURFACE=PASS\n");

    vr = enum_physical(instance, &physical_count, NULL);
    if (vr != VK_SUCCESS || !physical_count) {
        rc = fail(21, "enumerate-physical-devices", "no physical devices reported"); goto done;
    }
    physical_devices = (VkPhysicalDevice *)calloc(physical_count, sizeof(*physical_devices));
    if (!physical_devices) { rc = fail(22, "allocate", "physical device allocation failed"); goto done; }
    vr = enum_physical(instance, &physical_count, physical_devices);
    if (vr != VK_SUCCESS) { rc = fail(23, "enumerate-physical-devices", "physical device read failed"); goto done; }

    /* Pick a device+queue that can both draw and present and supports swapchain. */
    for (i = 0; i < physical_count && physical == VK_NULL_HANDLE; ++i) {
        VkPhysicalDevice candidate = physical_devices[i];
        uint32_t q;
        free(device_exts); device_exts = NULL; device_ext_count = 0;
        vr = enum_device_exts(candidate, NULL, &device_ext_count, NULL);
        if (vr != VK_SUCCESS || !device_ext_count) continue;
        device_exts = (VkExtensionProperties *)calloc(device_ext_count, sizeof(*device_exts));
        if (!device_exts) { rc = fail(24, "allocate", "device extension allocation failed"); goto done; }
        vr = enum_device_exts(candidate, NULL, &device_ext_count, device_exts);
        if (vr != VK_SUCCESS || !has_extension(device_exts, device_ext_count, VK_KHR_SWAPCHAIN_EXTENSION_NAME)) continue;

        get_queue_props(candidate, &queue_count, NULL);
        free(queue_props); queue_props = NULL;
        if (!queue_count) continue;
        queue_props = (VkQueueFamilyProperties *)calloc(queue_count, sizeof(*queue_props));
        if (!queue_props) { rc = fail(25, "allocate", "queue allocation failed"); goto done; }
        get_queue_props(candidate, &queue_count, queue_props);
        for (q = 0; q < queue_count; ++q) {
            VkBool32 present = VK_FALSE;
            if (!(queue_props[q].queueFlags & VK_QUEUE_GRAPHICS_BIT) || !queue_props[q].queueCount) continue;
            if (get_surface_support(candidate, q, surface, &present) == VK_SUCCESS && present) {
                physical = candidate;
                queue_family = q;
                break;
            }
        }
    }
    if (physical == VK_NULL_HANDLE || queue_family == UINT32_MAX) {
        rc = fail(26, "select-device", "no graphics+present queue with VK_KHR_swapchain found"); goto done;
    }
    printf("GRAPHICS_PRESENT_QUEUE=%u\n", queue_family);
    printf("HAS_KHR_SWAPCHAIN=1\n");

    {
        float priority = 1.0f;
        VkDeviceQueueCreateInfo qci;
        VkDeviceCreateInfo dci;
        const char *enabled[2];
        uint32_t enabled_count = 0;
        memset(&qci, 0, sizeof(qci));
        qci.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        qci.queueFamilyIndex = queue_family;
        qci.queueCount = 1;
        qci.pQueuePriorities = &priority;
        enabled[enabled_count++] = VK_KHR_SWAPCHAIN_EXTENSION_NAME;
#ifdef VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME
        if (has_extension(device_exts, device_ext_count, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME))
            enabled[enabled_count++] = VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME;
#endif
        memset(&dci, 0, sizeof(dci));
        dci.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        dci.queueCreateInfoCount = 1;
        dci.pQueueCreateInfos = &qci;
        dci.enabledExtensionCount = enabled_count;
        dci.ppEnabledExtensionNames = enabled;
        vr = create_device(physical, &dci, NULL, &device);
        if (vr != VK_SUCCESS || device == VK_NULL_HANDLE) {
            char msg[96]; snprintf(msg, sizeof(msg), "vkCreateDevice failed (%d)", (int)vr);
            rc = fail(27, "create-device", msg); goto done;
        }
    }
    printf("LOGICAL_DEVICE=PASS\n");

    RESOLVE_DEVICE(destroy_device, "vkDestroyDevice", PFN_vkDestroyDevice);
    RESOLVE_DEVICE(get_device_queue, "vkGetDeviceQueue", PFN_vkGetDeviceQueue);
    RESOLVE_DEVICE(create_swapchain, "vkCreateSwapchainKHR", PFN_vkCreateSwapchainKHR);
    RESOLVE_DEVICE(destroy_swapchain, "vkDestroySwapchainKHR", PFN_vkDestroySwapchainKHR);
    RESOLVE_DEVICE(get_swapchain_images, "vkGetSwapchainImagesKHR", PFN_vkGetSwapchainImagesKHR);
    RESOLVE_DEVICE(acquire_next_image, "vkAcquireNextImageKHR", PFN_vkAcquireNextImageKHR);
    RESOLVE_DEVICE(queue_present, "vkQueuePresentKHR", PFN_vkQueuePresentKHR);
    RESOLVE_DEVICE(create_image_view, "vkCreateImageView", PFN_vkCreateImageView);
    RESOLVE_DEVICE(destroy_image_view, "vkDestroyImageView", PFN_vkDestroyImageView);
    RESOLVE_DEVICE(create_render_pass, "vkCreateRenderPass", PFN_vkCreateRenderPass);
    RESOLVE_DEVICE(destroy_render_pass, "vkDestroyRenderPass", PFN_vkDestroyRenderPass);
    RESOLVE_DEVICE(create_framebuffer, "vkCreateFramebuffer", PFN_vkCreateFramebuffer);
    RESOLVE_DEVICE(destroy_framebuffer, "vkDestroyFramebuffer", PFN_vkDestroyFramebuffer);
    RESOLVE_DEVICE(create_command_pool, "vkCreateCommandPool", PFN_vkCreateCommandPool);
    RESOLVE_DEVICE(destroy_command_pool, "vkDestroyCommandPool", PFN_vkDestroyCommandPool);
    RESOLVE_DEVICE(allocate_cmds, "vkAllocateCommandBuffers", PFN_vkAllocateCommandBuffers);
    RESOLVE_DEVICE(begin_cmd, "vkBeginCommandBuffer", PFN_vkBeginCommandBuffer);
    RESOLVE_DEVICE(end_cmd, "vkEndCommandBuffer", PFN_vkEndCommandBuffer);
    RESOLVE_DEVICE(cmd_begin_render_pass, "vkCmdBeginRenderPass", PFN_vkCmdBeginRenderPass);
    RESOLVE_DEVICE(cmd_end_render_pass, "vkCmdEndRenderPass", PFN_vkCmdEndRenderPass);
    RESOLVE_DEVICE(create_semaphore, "vkCreateSemaphore", PFN_vkCreateSemaphore);
    RESOLVE_DEVICE(destroy_semaphore, "vkDestroySemaphore", PFN_vkDestroySemaphore);
    RESOLVE_DEVICE(create_fence, "vkCreateFence", PFN_vkCreateFence);
    RESOLVE_DEVICE(destroy_fence, "vkDestroyFence", PFN_vkDestroyFence);
    RESOLVE_DEVICE(wait_fences, "vkWaitForFences", PFN_vkWaitForFences);
    RESOLVE_DEVICE(reset_fences, "vkResetFences", PFN_vkResetFences);
    RESOLVE_DEVICE(queue_submit, "vkQueueSubmit", PFN_vkQueueSubmit);
    RESOLVE_DEVICE(device_wait_idle, "vkDeviceWaitIdle", PFN_vkDeviceWaitIdle);
    get_device_queue(device, queue_family, 0, &queue);

    memset(&caps, 0, sizeof(caps));
    vr = get_surface_caps(physical, surface, &caps);
    if (vr != VK_SUCCESS) { rc = fail(61, "surface-capabilities", "query failed"); goto done; }
    vr = get_surface_formats(physical, surface, &format_count, NULL);
    if (vr != VK_SUCCESS || !format_count) { rc = fail(62, "surface-formats", "none reported"); goto done; }
    formats = (VkSurfaceFormatKHR *)calloc(format_count, sizeof(*formats));
    if (!formats) { rc = fail(63, "allocate", "format allocation failed"); goto done; }
    vr = get_surface_formats(physical, surface, &format_count, formats);
    if (vr != VK_SUCCESS) { rc = fail(64, "surface-formats", "read failed"); goto done; }
    chosen_format = formats[0];
    for (i = 0; i < format_count; ++i) {
        if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM || formats[i].format == VK_FORMAT_B8G8R8A8_SRGB) {
            chosen_format = formats[i]; break;
        }
    }
    vr = get_present_modes(physical, surface, &present_mode_count, NULL);
    if (vr != VK_SUCCESS || !present_mode_count) { rc = fail(65, "present-modes", "none reported"); goto done; }
    present_modes = (VkPresentModeKHR *)calloc(present_mode_count, sizeof(*present_modes));
    if (!present_modes) { rc = fail(66, "allocate", "present-mode allocation failed"); goto done; }
    vr = get_present_modes(physical, surface, &present_mode_count, present_modes);
    if (vr != VK_SUCCESS) { rc = fail(67, "present-modes", "read failed"); goto done; }

    if (caps.currentExtent.width != UINT32_MAX) extent = caps.currentExtent;
    else {
        extent.width = clamp_u32(640, caps.minImageExtent.width, caps.maxImageExtent.width);
        extent.height = clamp_u32(360, caps.minImageExtent.height, caps.maxImageExtent.height);
    }
    image_count = caps.minImageCount + 1;
    if (caps.maxImageCount && image_count > caps.maxImageCount) image_count = caps.maxImageCount;

    {
        VkSwapchainCreateInfoKHR sci;
        memset(&sci, 0, sizeof(sci));
        sci.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
        sci.surface = surface;
        sci.minImageCount = image_count;
        sci.imageFormat = chosen_format.format;
        sci.imageColorSpace = chosen_format.colorSpace;
        sci.imageExtent = extent;
        sci.imageArrayLayers = 1;
        sci.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
        sci.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
        sci.preTransform = caps.currentTransform;
        sci.compositeAlpha = (caps.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR)
                                 ? VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
                                 : (VkCompositeAlphaFlagBitsKHR)(caps.supportedCompositeAlpha & (~caps.supportedCompositeAlpha + 1));
        sci.presentMode = VK_PRESENT_MODE_FIFO_KHR;
        sci.clipped = VK_TRUE;
        vr = create_swapchain(device, &sci, NULL, &swapchain);
        if (vr != VK_SUCCESS || swapchain == VK_NULL_HANDLE) {
            char msg[96]; snprintf(msg, sizeof(msg), "vkCreateSwapchainKHR failed (%d)", (int)vr);
            rc = fail(68, "create-swapchain", msg); goto done;
        }
    }
    printf("SWAPCHAIN=PASS\n");

    vr = get_swapchain_images(device, swapchain, &image_count, NULL);
    if (vr != VK_SUCCESS || !image_count) { rc = fail(69, "swapchain-images", "none returned"); goto done; }
    images = (VkImage *)calloc(image_count, sizeof(*images));
    views = (VkImageView *)calloc(image_count, sizeof(*views));
    framebuffers = (VkFramebuffer *)calloc(image_count, sizeof(*framebuffers));
    cmds = (VkCommandBuffer *)calloc(image_count, sizeof(*cmds));
    if (!images || !views || !framebuffers || !cmds) { rc = fail(70, "allocate", "swapchain resources failed"); goto done; }
    vr = get_swapchain_images(device, swapchain, &image_count, images);
    if (vr != VK_SUCCESS) { rc = fail(71, "swapchain-images", "read failed"); goto done; }

    for (i = 0; i < image_count; ++i) {
        VkImageViewCreateInfo iv;
        memset(&iv, 0, sizeof(iv));
        iv.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        iv.image = images[i];
        iv.viewType = VK_IMAGE_VIEW_TYPE_2D;
        iv.format = chosen_format.format;
        iv.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
        iv.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
        iv.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
        iv.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
        iv.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        iv.subresourceRange.levelCount = 1;
        iv.subresourceRange.layerCount = 1;
        vr = create_image_view(device, &iv, NULL, &views[i]);
        if (vr != VK_SUCCESS) { rc = fail(72, "create-image-view", "failed"); goto done; }
    }

    {
        VkAttachmentDescription attachment;
        VkAttachmentReference ref;
        VkSubpassDescription subpass;
        VkRenderPassCreateInfo rp;
        memset(&attachment, 0, sizeof(attachment));
        attachment.format = chosen_format.format;
        attachment.samples = VK_SAMPLE_COUNT_1_BIT;
        attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        attachment.finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        ref.attachment = 0;
        ref.layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
        memset(&subpass, 0, sizeof(subpass));
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &ref;
        memset(&rp, 0, sizeof(rp));
        rp.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
        rp.attachmentCount = 1;
        rp.pAttachments = &attachment;
        rp.subpassCount = 1;
        rp.pSubpasses = &subpass;
        vr = create_render_pass(device, &rp, NULL, &render_pass);
        if (vr != VK_SUCCESS) { rc = fail(73, "create-render-pass", "failed"); goto done; }
    }

    for (i = 0; i < image_count; ++i) {
        VkFramebufferCreateInfo fb;
        memset(&fb, 0, sizeof(fb));
        fb.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
        fb.renderPass = render_pass;
        fb.attachmentCount = 1;
        fb.pAttachments = &views[i];
        fb.width = extent.width;
        fb.height = extent.height;
        fb.layers = 1;
        vr = create_framebuffer(device, &fb, NULL, &framebuffers[i]);
        if (vr != VK_SUCCESS) { rc = fail(74, "create-framebuffer", "failed"); goto done; }
    }

    {
        VkCommandPoolCreateInfo cp;
        VkCommandBufferAllocateInfo ca;
        memset(&cp, 0, sizeof(cp));
        cp.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        cp.queueFamilyIndex = queue_family;
        vr = create_command_pool(device, &cp, NULL, &command_pool);
        if (vr != VK_SUCCESS) { rc = fail(75, "create-command-pool", "failed"); goto done; }
        memset(&ca, 0, sizeof(ca));
        ca.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        ca.commandPool = command_pool;
        ca.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        ca.commandBufferCount = image_count;
        vr = allocate_cmds(device, &ca, cmds);
        if (vr != VK_SUCCESS) { rc = fail(76, "allocate-command-buffers", "failed"); goto done; }
    }

    for (i = 0; i < image_count; ++i) {
        VkCommandBufferBeginInfo bi;
        VkClearValue clear;
        VkRenderPassBeginInfo rbi;
        memset(&bi, 0, sizeof(bi));
        bi.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        bi.flags = VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT;
        vr = begin_cmd(cmds[i], &bi);
        if (vr != VK_SUCCESS) { rc = fail(77, "begin-command-buffer", "failed"); goto done; }
        clear.color.float32[0] = 0.04f;
        clear.color.float32[1] = 0.12f;
        clear.color.float32[2] = 0.22f;
        clear.color.float32[3] = 1.0f;
        memset(&rbi, 0, sizeof(rbi));
        rbi.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
        rbi.renderPass = render_pass;
        rbi.framebuffer = framebuffers[i];
        rbi.renderArea.extent = extent;
        rbi.clearValueCount = 1;
        rbi.pClearValues = &clear;
        cmd_begin_render_pass(cmds[i], &rbi, VK_SUBPASS_CONTENTS_INLINE);
        cmd_end_render_pass(cmds[i]);
        vr = end_cmd(cmds[i]);
        if (vr != VK_SUCCESS) { rc = fail(78, "end-command-buffer", "failed"); goto done; }
    }

    {
        VkSemaphoreCreateInfo si;
        VkFenceCreateInfo fi;
        memset(&si, 0, sizeof(si)); si.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        memset(&fi, 0, sizeof(fi)); fi.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO; fi.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        if (create_semaphore(device, &si, NULL, &acquire_sem) != VK_SUCCESS ||
            create_semaphore(device, &si, NULL, &render_sem) != VK_SUCCESS ||
            create_fence(device, &fi, NULL, &frame_fence) != VK_SUCCESS) {
            rc = fail(79, "create-sync", "semaphore/fence creation failed"); goto done;
        }
    }

    for (i = 0; i < TARGET_FRAMES && !closed; ++i) {
        uint32_t image_index = 0;
        VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
        VkSubmitInfo submit;
        VkPresentInfoKHR present;
        pump_messages(&closed);
        if (closed) break;
        vr = wait_fences(device, 1, &frame_fence, VK_TRUE, UINT64_MAX);
        if (vr != VK_SUCCESS) { rc = fail(80, "wait-fence", "failed"); goto done; }
        vr = reset_fences(device, 1, &frame_fence);
        if (vr != VK_SUCCESS) { rc = fail(81, "reset-fence", "failed"); goto done; }
        vr = acquire_next_image(device, swapchain, UINT64_MAX, acquire_sem, VK_NULL_HANDLE, &image_index);
        if (vr != VK_SUCCESS && vr != VK_SUBOPTIMAL_KHR) { rc = fail(82, "acquire-image", "failed"); goto done; }
        memset(&submit, 0, sizeof(submit));
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.waitSemaphoreCount = 1;
        submit.pWaitSemaphores = &acquire_sem;
        submit.pWaitDstStageMask = &wait_stage;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &cmds[image_index];
        submit.signalSemaphoreCount = 1;
        submit.pSignalSemaphores = &render_sem;
        vr = queue_submit(queue, 1, &submit, frame_fence);
        if (vr != VK_SUCCESS) { rc = fail(83, "queue-submit", "failed"); goto done; }
        memset(&present, 0, sizeof(present));
        present.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
        present.waitSemaphoreCount = 1;
        present.pWaitSemaphores = &render_sem;
        present.swapchainCount = 1;
        present.pSwapchains = &swapchain;
        present.pImageIndices = &image_index;
        vr = queue_present(queue, &present);
        if (vr != VK_SUCCESS && vr != VK_SUBOPTIMAL_KHR) { rc = fail(84, "queue-present", "failed"); goto done; }
        if ((i + 1) % 30 == 0) printf("FRAME_%u=PASS\n", i + 1);
    }
    if (closed) { rc = fail(85, "window-closed", "probe window closed before target frame count"); goto done; }
    printf("PRESENTED_FRAMES=%u\n", TARGET_FRAMES);
    printf("CLEAR_PRESENT=PASS\n");
    printf("RESULT=PASS\n");
    printf("NEXT_GATE=detroit-process-and-shader-compilation\n");

done:
    if (device != VK_NULL_HANDLE && device_wait_idle) device_wait_idle(device);
    if (device != VK_NULL_HANDLE) {
        if (destroy_fence && frame_fence) destroy_fence(device, frame_fence, NULL);
        if (destroy_semaphore && render_sem) destroy_semaphore(device, render_sem, NULL);
        if (destroy_semaphore && acquire_sem) destroy_semaphore(device, acquire_sem, NULL);
        if (destroy_command_pool && command_pool) destroy_command_pool(device, command_pool, NULL);
        if (destroy_framebuffer && framebuffers) for (i = 0; i < image_count; ++i) if (framebuffers[i]) destroy_framebuffer(device, framebuffers[i], NULL);
        if (destroy_render_pass && render_pass) destroy_render_pass(device, render_pass, NULL);
        if (destroy_image_view && views) for (i = 0; i < image_count; ++i) if (views[i]) destroy_image_view(device, views[i], NULL);
        if (destroy_swapchain && swapchain) destroy_swapchain(device, swapchain, NULL);
        if (destroy_device) destroy_device(device, NULL);
    }
    if (surface != VK_NULL_HANDLE && destroy_surface) destroy_surface(instance, surface, NULL);
    if (instance != VK_NULL_HANDLE && destroy_instance) destroy_instance(instance, NULL);
    if (loader) FreeLibrary(loader);
    if (hwnd) DestroyWindow(hwnd);
    UnregisterClassA(WINDOW_CLASS, hinstance);
    free(cmds); free(framebuffers); free(views); free(images); free(present_modes);
    free(formats); free(device_exts); free(queue_props); free(physical_devices); free(instance_exts);
    return rc;
}
