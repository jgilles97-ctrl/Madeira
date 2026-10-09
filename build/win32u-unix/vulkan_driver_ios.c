/*
 * Madeira iOS Vulkan user-driver bridge.
 *
 * This is the iOS equivalent of Wine's winemac.drv/vulkan.c. Wine exposes
 * VK_KHR_win32_surface to the Windows guest, then this driver maps that request
 * to VK_EXT_metal_surface on the host MoltenVK instance using Madeira's existing
 * HWND -> CAMetalLayer mapping.
 */

#include <stddef.h>
#include <stdio.h>

#include "ntstatus.h"
#include "wine/gdi_driver.h"
#include "wine/vulkan.h"
#include "wine/vulkan_driver.h"

#include "vulkan_surface_ios.h"

struct winios_vulkan_client_surface
{
    struct client_surface client;
    struct madeira_vulkan_surface_binding binding;
};

static struct winios_vulkan_client_surface *impl_from_client(struct client_surface *client)
{
    return CONTAINING_RECORD(client, struct winios_vulkan_client_surface, client);
}

static void winios_vulkan_client_destroy(struct client_surface *client)
{
    struct winios_vulkan_client_surface *surface = impl_from_client(client);
    madeira_vulkan_surface_release(&surface->binding);
}

/* Keep the retained layer alive until Vulkan destroys the VkSurfaceKHR. A
 * Win32 window disappearing must not leave MoltenVK with a dangling CAMetalLayer
 * while the guest tears its swapchain/surface down on another thread. */
static void winios_vulkan_client_detach(struct client_surface *client)
{
    (void)client;
}

static void winios_vulkan_client_update(struct client_surface *client)
{
    (void)client;
}

static void winios_vulkan_client_present(struct client_surface *client, HDC hdc)
{
    (void)client;
    (void)hdc;
}

static const struct client_surface_funcs winios_vulkan_client_funcs =
{
    .destroy = winios_vulkan_client_destroy,
    .detach = winios_vulkan_client_detach,
    .update = winios_vulkan_client_update,
    .present = winios_vulkan_client_present,
};

static VkResult winios_vulkan_surface_create(HWND hwnd,
                                              const struct vulkan_instance *instance,
                                              VkSurfaceKHR *handle,
                                              struct client_surface **client)
{
    struct winios_vulkan_client_surface *surface;
    VkMetalSurfaceCreateInfoEXT info;
    VkResult result;
    int binding_result;

    if (!instance || !handle || !client) return VK_ERROR_INITIALIZATION_FAILED;
    if (!instance->p_vkCreateMetalSurfaceEXT)
    {
        fprintf(stderr, "[madeira-vulkan] host instance lacks vkCreateMetalSurfaceEXT\n");
        return VK_ERROR_EXTENSION_NOT_PRESENT;
    }

    surface = (struct winios_vulkan_client_surface *)client_surface_create(
        sizeof(*surface), &winios_vulkan_client_funcs, hwnd);
    if (!surface) return VK_ERROR_OUT_OF_HOST_MEMORY;

    binding_result = madeira_vulkan_surface_acquire(hwnd, &surface->binding);
    if (binding_result)
    {
        fprintf(stderr, "[madeira-vulkan] HWND -> CAMetalLayer failed (%d), hwnd=%p\n",
                binding_result, hwnd);
        client_surface_release(&surface->client);
        return VK_ERROR_SURFACE_LOST_KHR;
    }

    info.sType = VK_STRUCTURE_TYPE_METAL_SURFACE_CREATE_INFO_EXT;
    info.pNext = NULL;
    info.flags = 0;
    info.pLayer = surface->binding.metal_layer;

    result = instance->p_vkCreateMetalSurfaceEXT(instance->host.instance, &info,
                                                  NULL, handle);
    if (result != VK_SUCCESS)
    {
        fprintf(stderr, "[madeira-vulkan] vkCreateMetalSurfaceEXT failed (%d)\n",
                (int)result);
        client_surface_release(&surface->client);
        return result;
    }

    *client = &surface->client;
    fprintf(stderr, "[madeira-vulkan] VkSurfaceKHR ready hwnd=%p host=0x%llx client=%p\n",
            hwnd, (unsigned long long)*handle, (void *)*client);
    fflush(stderr);
    return VK_SUCCESS;
}

static VkBool32 winios_vulkan_presentation_support(struct vulkan_physical_device *physical_device,
                                                    uint32_t queue_index)
{
    (void)physical_device;
    (void)queue_index;
    return VK_TRUE;
}

static void winios_map_instance_extensions(struct vulkan_instance_extensions *extensions)
{
    /* Guest Windows applications ask for Win32 surfaces. MoltenVK exposes
     * Metal surfaces. Wine handles the public guest/host translation once the
     * two capability bits are mapped to one another here. */
    if (extensions->has_VK_KHR_win32_surface)
        extensions->has_VK_EXT_metal_surface = 1;
    if (extensions->has_VK_EXT_metal_surface)
        extensions->has_VK_KHR_win32_surface = 1;
}

static void winios_map_device_extensions(struct vulkan_device_extensions *extensions)
{
    (void)extensions;
}

static const struct vulkan_driver_funcs winios_vulkan_driver_funcs =
{
    .p_vulkan_surface_create = winios_vulkan_surface_create,
    .p_get_physical_device_presentation_support = winios_vulkan_presentation_support,
    .p_map_instance_extensions = winios_map_instance_extensions,
    .p_map_device_extensions = winios_map_device_extensions,
};

UINT winios_pVulkanInit(UINT version, void *vulkan_handle,
                        const struct vulkan_driver_funcs **driver_funcs)
{
    (void)vulkan_handle;
    if (version != WINE_VULKAN_DRIVER_VERSION)
    {
        fprintf(stderr,
                "[madeira-vulkan] driver version mismatch: win32u=%u iOS-driver=%u\n",
                version, WINE_VULKAN_DRIVER_VERSION);
        return STATUS_INVALID_PARAMETER;
    }
    if (!madeira_vulkan_surface_bridge_ready())
    {
        fprintf(stderr, "[madeira-vulkan] IOSDisplayShim Metal exports are unavailable\n");
        return STATUS_NOT_SUPPORTED;
    }

    *driver_funcs = &winios_vulkan_driver_funcs;
    fprintf(stderr, "[madeira-vulkan] iOS Vulkan user driver ACTIVE\n");
    fflush(stderr);
    return STATUS_SUCCESS;
}
