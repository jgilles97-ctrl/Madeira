/* Static MoltenVK loader adapter for Wine win32u on jailed iOS. */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <vulkan/vulkan.h>

static unsigned char madeira_vulkan_handle_token;

void *madeira_vulkan_dlopen(const char *path, int mode)
{
    (void)mode;
    if (!path) return NULL;
    fprintf(stderr, "[madeira-vulkan] static MoltenVK open: %s\n", path);
    fflush(stderr);
    return &madeira_vulkan_handle_token;
}

void *madeira_vulkan_dlsym(void *handle, const char *name)
{
    if (handle != &madeira_vulkan_handle_token || !name) return NULL;

    /* Wine's win32u/vulkan.c asks the host library for only these two direct
     * exports. Every other Vulkan entry point is then obtained through them. */
    if (!strcmp(name, "vkGetInstanceProcAddr"))
        return (void *)(uintptr_t)&vkGetInstanceProcAddr;
    if (!strcmp(name, "vkGetDeviceProcAddr"))
        return (void *)(uintptr_t)&vkGetDeviceProcAddr;

    /* The iOS WSI driver's VulkanInit uses this as a capability check. Keep
     * it honest by resolving through MoltenVK's own instance proc lookup. */
    if (!strcmp(name, "vkCreateMetalSurfaceEXT"))
        return (void *)(uintptr_t)vkGetInstanceProcAddr(VK_NULL_HANDLE,
                                                        "vkCreateMetalSurfaceEXT");

    return NULL;
}

int madeira_vulkan_dlclose(void *handle)
{
    return handle == &madeira_vulkan_handle_token ? 0 : -1;
}
