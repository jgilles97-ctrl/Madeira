/*
 * vulkan_wsi_probe.c - prove Madeira's Win32 -> Wine -> MoltenVK WSI path.
 *
 * This is intentionally a Windows x64 executable and dynamically loads
 * vulkan-1.dll. A PASS therefore exercises the same guest ABI Detroit uses;
 * it cannot accidentally bypass Wine by linking host MoltenVK directly.
 */

#define WIN32_LEAN_AND_MEAN
#define VK_USE_PLATFORM_WIN32_KHR 1
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define PROBE_SCHEMA "MADEIRA_VK_WSI_PROBE_V1"
#define WINDOW_CLASS "MadeiraVulkanWSIProbe"

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

static LRESULT CALLBACK wnd_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)
{
    if (msg == WM_CLOSE) {
        DestroyWindow(hwnd);
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wparam, lparam);
}

int main(void)
{
    HINSTANCE hinstance = GetModuleHandleA(NULL);
    WNDCLASSEXA wc;
    HWND hwnd = NULL;
    HMODULE loader = NULL;
    VkExtensionProperties *instance_exts = NULL;
    VkPhysicalDevice *devices = NULL;
    VkQueueFamilyProperties *queues = NULL;
    VkSurfaceFormatKHR *formats = NULL;
    VkPresentModeKHR *present_modes = NULL;
    VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    PFN_vkGetInstanceProcAddr gip = NULL;
    PFN_vkEnumerateInstanceExtensionProperties enum_instance_exts = NULL;
    PFN_vkCreateInstance create_instance = NULL;
    PFN_vkDestroyInstance destroy_instance = NULL;
    PFN_vkCreateWin32SurfaceKHR create_win32_surface = NULL;
    PFN_vkDestroySurfaceKHR destroy_surface = NULL;
    PFN_vkEnumeratePhysicalDevices enum_devices = NULL;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queues = NULL;
    PFN_vkGetPhysicalDeviceSurfaceSupportKHR get_surface_support = NULL;
    PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR get_surface_caps = NULL;
    PFN_vkGetPhysicalDeviceSurfaceFormatsKHR get_surface_formats = NULL;
    PFN_vkGetPhysicalDeviceSurfacePresentModesKHR get_present_modes = NULL;
    uint32_t ext_count = 0, device_count = 0, queue_count = 0;
    uint32_t format_count = 0, present_mode_count = 0;
    uint32_t present_queue = UINT32_MAX;
    uint32_t i;
    VkResult vr;
    int rc = 0;

    printf("SCHEMA=%s\n", PROBE_SCHEMA);
    printf("ARCH=x86_64-windows\n");

    memset(&wc, 0, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.hInstance = hinstance;
    wc.lpfnWndProc = wnd_proc;
    wc.lpszClassName = WINDOW_CLASS;
    if (!RegisterClassExA(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
        return fail(10, "register-window-class", "RegisterClassExA failed");

    hwnd = CreateWindowExA(0, WINDOW_CLASS, "Madeira Vulkan WSI Probe",
                           WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                           640, 360, NULL, NULL, hinstance, NULL);
    if (!hwnd) return fail(11, "create-window", "CreateWindowExA failed");
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    printf("WIN32_WINDOW=PASS\n");

    loader = LoadLibraryA("vulkan-1.dll");
    if (!loader) {
        rc = fail(12, "load-vulkan-loader", "vulkan-1.dll is missing");
        goto done;
    }
    gip = (PFN_vkGetInstanceProcAddr)GetProcAddress(loader, "vkGetInstanceProcAddr");
    if (!gip) {
        rc = fail(13, "resolve-vulkan-loader", "vkGetInstanceProcAddr is missing");
        goto done;
    }
    enum_instance_exts = (PFN_vkEnumerateInstanceExtensionProperties)
        gip(VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
    create_instance = (PFN_vkCreateInstance)gip(VK_NULL_HANDLE, "vkCreateInstance");
    if (!enum_instance_exts || !create_instance) {
        rc = fail(14, "resolve-global-functions", "required global Vulkan functions are missing");
        goto done;
    }

    vr = enum_instance_exts(NULL, &ext_count, NULL);
    if (vr != VK_SUCCESS || !ext_count) {
        rc = fail(15, "enumerate-instance-extensions", "no instance extensions reported");
        goto done;
    }
    instance_exts = (VkExtensionProperties *)calloc(ext_count, sizeof(*instance_exts));
    if (!instance_exts) {
        rc = fail(16, "allocate", "instance extension allocation failed");
        goto done;
    }
    vr = enum_instance_exts(NULL, &ext_count, instance_exts);
    if (vr != VK_SUCCESS) {
        rc = fail(17, "enumerate-instance-extensions", "instance extension read failed");
        goto done;
    }

    printf("HAS_KHR_SURFACE=%d\n",
           has_extension(instance_exts, ext_count, VK_KHR_SURFACE_EXTENSION_NAME));
    printf("HAS_KHR_WIN32_SURFACE=%d\n",
           has_extension(instance_exts, ext_count, VK_KHR_WIN32_SURFACE_EXTENSION_NAME));
    if (!has_extension(instance_exts, ext_count, VK_KHR_SURFACE_EXTENSION_NAME) ||
        !has_extension(instance_exts, ext_count, VK_KHR_WIN32_SURFACE_EXTENSION_NAME)) {
        rc = fail(18, "guest-wsi-extensions",
                  "Wine guest did not expose VK_KHR_surface + VK_KHR_win32_surface");
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
        app.pApplicationName = "Madeira Vulkan WSI Probe";
        app.apiVersion = VK_API_VERSION_1_1;

        enabled[enabled_count++] = VK_KHR_SURFACE_EXTENSION_NAME;
        enabled[enabled_count++] = VK_KHR_WIN32_SURFACE_EXTENSION_NAME;
#ifdef VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME
        if (has_extension(instance_exts, ext_count,
                          VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME)) {
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
            char msg[96];
            snprintf(msg, sizeof(msg), "vkCreateInstance failed (%d)", (int)vr);
            rc = fail(19, "create-instance", msg);
            goto done;
        }
    }
    printf("INSTANCE=PASS\n");

    destroy_instance = (PFN_vkDestroyInstance)gip(instance, "vkDestroyInstance");
    create_win32_surface = (PFN_vkCreateWin32SurfaceKHR)gip(instance, "vkCreateWin32SurfaceKHR");
    destroy_surface = (PFN_vkDestroySurfaceKHR)gip(instance, "vkDestroySurfaceKHR");
    enum_devices = (PFN_vkEnumeratePhysicalDevices)gip(instance, "vkEnumeratePhysicalDevices");
    get_queues = (PFN_vkGetPhysicalDeviceQueueFamilyProperties)
        gip(instance, "vkGetPhysicalDeviceQueueFamilyProperties");
    get_surface_support = (PFN_vkGetPhysicalDeviceSurfaceSupportKHR)
        gip(instance, "vkGetPhysicalDeviceSurfaceSupportKHR");
    get_surface_caps = (PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR)
        gip(instance, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR");
    get_surface_formats = (PFN_vkGetPhysicalDeviceSurfaceFormatsKHR)
        gip(instance, "vkGetPhysicalDeviceSurfaceFormatsKHR");
    get_present_modes = (PFN_vkGetPhysicalDeviceSurfacePresentModesKHR)
        gip(instance, "vkGetPhysicalDeviceSurfacePresentModesKHR");
    if (!destroy_instance || !create_win32_surface || !destroy_surface || !enum_devices ||
        !get_queues || !get_surface_support || !get_surface_caps ||
        !get_surface_formats || !get_present_modes) {
        rc = fail(20, "resolve-wsi-functions", "required Win32/surface functions are missing");
        goto done;
    }

    {
        VkWin32SurfaceCreateInfoKHR sci;
        memset(&sci, 0, sizeof(sci));
        sci.sType = VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR;
        sci.hinstance = hinstance;
        sci.hwnd = hwnd;
        vr = create_win32_surface(instance, &sci, NULL, &surface);
        if (vr != VK_SUCCESS || surface == VK_NULL_HANDLE) {
            char msg[128];
            snprintf(msg, sizeof(msg), "vkCreateWin32SurfaceKHR failed (%d)", (int)vr);
            rc = fail(21, "create-win32-surface", msg);
            goto done;
        }
    }
    printf("WIN32_SURFACE=PASS\n");

    vr = enum_devices(instance, &device_count, NULL);
    if (vr != VK_SUCCESS || !device_count) {
        rc = fail(22, "enumerate-physical-devices", "no Vulkan physical devices found");
        goto done;
    }
    devices = (VkPhysicalDevice *)calloc(device_count, sizeof(*devices));
    if (!devices) {
        rc = fail(23, "allocate", "physical-device allocation failed");
        goto done;
    }
    vr = enum_devices(instance, &device_count, devices);
    if (vr != VK_SUCCESS) {
        rc = fail(24, "enumerate-physical-devices", "physical-device enumeration failed");
        goto done;
    }

    get_queues(devices[0], &queue_count, NULL);
    if (!queue_count) {
        rc = fail(25, "queue-families", "no queue families reported");
        goto done;
    }
    queues = (VkQueueFamilyProperties *)calloc(queue_count, sizeof(*queues));
    if (!queues) {
        rc = fail(26, "allocate", "queue allocation failed");
        goto done;
    }
    get_queues(devices[0], &queue_count, queues);
    for (i = 0; i < queue_count; ++i) {
        VkBool32 supported = VK_FALSE;
        vr = get_surface_support(devices[0], i, surface, &supported);
        if (vr == VK_SUCCESS && supported) {
            printf("QUEUE_%u_PRESENT=1\n", i);
            if (present_queue == UINT32_MAX) present_queue = i;
        }
    }
    if (present_queue == UINT32_MAX) {
        rc = fail(27, "surface-present-support",
                  "no Vulkan queue can present to the Win32/Metal surface");
        goto done;
    }
    printf("PRESENT_QUEUE_FAMILY=%u\n", present_queue);

    {
        VkSurfaceCapabilitiesKHR caps;
        memset(&caps, 0, sizeof(caps));
        vr = get_surface_caps(devices[0], surface, &caps);
        if (vr != VK_SUCCESS) {
            rc = fail(28, "surface-capabilities", "surface capability query failed");
            goto done;
        }
        printf("SURFACE_MIN_IMAGES=%u\n", caps.minImageCount);
        printf("SURFACE_MAX_IMAGES=%u\n", caps.maxImageCount);
        printf("SURFACE_CURRENT_EXTENT=%ux%u\n",
               caps.currentExtent.width, caps.currentExtent.height);
    }

    vr = get_surface_formats(devices[0], surface, &format_count, NULL);
    if (vr != VK_SUCCESS || !format_count) {
        rc = fail(29, "surface-formats", "surface has no usable formats");
        goto done;
    }
    formats = (VkSurfaceFormatKHR *)calloc(format_count, sizeof(*formats));
    if (!formats) {
        rc = fail(30, "allocate", "surface-format allocation failed");
        goto done;
    }
    vr = get_surface_formats(devices[0], surface, &format_count, formats);
    if (vr != VK_SUCCESS) {
        rc = fail(31, "surface-formats", "surface format read failed");
        goto done;
    }
    printf("SURFACE_FORMAT_COUNT=%u\n", format_count);
    for (i = 0; i < format_count && i < 8; ++i)
        printf("SURFACE_FORMAT_%u=%d,%d\n", i, (int)formats[i].format,
               (int)formats[i].colorSpace);

    vr = get_present_modes(devices[0], surface, &present_mode_count, NULL);
    if (vr != VK_SUCCESS || !present_mode_count) {
        rc = fail(32, "present-modes", "surface has no present modes");
        goto done;
    }
    present_modes = (VkPresentModeKHR *)calloc(present_mode_count, sizeof(*present_modes));
    if (!present_modes) {
        rc = fail(33, "allocate", "present-mode allocation failed");
        goto done;
    }
    vr = get_present_modes(devices[0], surface, &present_mode_count, present_modes);
    if (vr != VK_SUCCESS) {
        rc = fail(34, "present-modes", "present-mode read failed");
        goto done;
    }
    printf("PRESENT_MODE_COUNT=%u\n", present_mode_count);
    for (i = 0; i < present_mode_count && i < 8; ++i)
        printf("PRESENT_MODE_%u=%d\n", i, (int)present_modes[i]);

    printf("RESULT=PASS\n");
    printf("NEXT_GATE=swapchain-clear-frame\n");

done:
    if (surface != VK_NULL_HANDLE && destroy_surface)
        destroy_surface(instance, surface, NULL);
    if (instance != VK_NULL_HANDLE && destroy_instance)
        destroy_instance(instance, NULL);
    if (loader) FreeLibrary(loader);
    if (hwnd) DestroyWindow(hwnd);
    UnregisterClassA(WINDOW_CLASS, hinstance);
    free(present_modes);
    free(formats);
    free(queues);
    free(devices);
    free(instance_exts);
    return rc;
}
