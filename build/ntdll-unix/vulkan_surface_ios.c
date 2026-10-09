/*
 * vulkan_surface_ios.c - Madeira iOS WSI binding helper.
 *
 * Wine's macOS Vulkan driver ultimately needs a CAMetalLayer when translating
 * vkCreateWin32SurfaceKHR to vkCreateMetalSurfaceEXT. Madeira already has the
 * authoritative HWND -> CAMetalLayer mapping in IOSDisplayShim.m for DXMT.
 * Reuse that path instead of inventing a second window registry.
 *
 * This file has deliberately NO Vulkan dependency. It owns only the lifetime
 * bridge between a Wine HWND and the retained Metal-view token exported by
 * IOSDisplayShim. A later winevulkan/win32u bridge supplies Vulkan types and
 * calls vkCreateMetalSurfaceEXT with the returned layer pointer.
 */

#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

#include "vulkan_surface_ios.h"

#ifndef RTLD_DEFAULT
#define RTLD_DEFAULT ((void *)-2)
#endif

typedef void *(*create_metal_view_fn)(void *view, void *device);
typedef void *(*get_metal_layer_fn)(void *view);
typedef void (*release_metal_view_fn)(void *view);

static pthread_once_t resolve_once = PTHREAD_ONCE_INIT;
static create_metal_view_fn p_create_metal_view;
static get_metal_layer_fn p_get_metal_layer;
static release_metal_view_fn p_release_metal_view;
static int resolve_ok;

static void resolve_display_exports(void)
{
    p_create_metal_view = (create_metal_view_fn)dlsym(
        RTLD_DEFAULT, "macdrv_view_create_metal_view");
    p_get_metal_layer = (get_metal_layer_fn)dlsym(
        RTLD_DEFAULT, "macdrv_view_get_metal_layer");
    p_release_metal_view = (release_metal_view_fn)dlsym(
        RTLD_DEFAULT, "macdrv_view_release_metal_view");

    resolve_ok = p_create_metal_view && p_get_metal_layer && p_release_metal_view;
    if (!resolve_ok)
    {
        fprintf(stderr,
                "[madeira-vulkan] display shim exports unavailable: create=%p get=%p release=%p\n",
                (void *)p_create_metal_view, (void *)p_get_metal_layer,
                (void *)p_release_metal_view);
        fflush(stderr);
    }
}

/* Return 1 when the app binary exports the WSI hooks this bridge requires. */
__attribute__((used, visibility("default")))
int madeira_vulkan_surface_bridge_ready(void)
{
    pthread_once(&resolve_once, resolve_display_exports);
    return resolve_ok;
}

/*
 * Acquire a retained Metal-view token for a Wine HWND.
 *
 * IOSDisplayShim's macdrv_view_create_metal_view() deliberately treats its
 * `view` argument as the HWND in Madeira. Passing the HWND directly therefore
 * works for both game mode (fullscreen singleton layer) and desktop mode
 * (per-window compositor layer). Its metal-device parameter is ignored, but
 * it expects a non-NULL handle, so use the same sentinel convention as the
 * display shim itself.
 *
 * Return values:
 *   0  success
 *  -1  invalid arguments
 *  -2  display shim exports are unavailable
 *  -3  no Metal view/layer exists for this HWND yet
 */
__attribute__((used, visibility("default")))
int madeira_vulkan_surface_acquire(void *hwnd,
                                   struct madeira_vulkan_surface_binding *binding)
{
    void *view;
    void *layer;

    if (!binding) return -1;
    binding->metal_view = NULL;
    binding->metal_layer = NULL;
    binding->hwnd = hwnd;

    if (!madeira_vulkan_surface_bridge_ready()) return -2;

    view = p_create_metal_view(hwnd, (void *)(uintptr_t)1);
    if (!view) return -3;

    layer = p_get_metal_layer(view);
    if (!layer)
    {
        p_release_metal_view(view);
        return -3;
    }

    binding->metal_view = view;
    binding->metal_layer = layer;

    fprintf(stderr, "[madeira-vulkan] WSI acquire hwnd=%p view=%p layer=%p\n",
            hwnd, view, layer);
    fflush(stderr);
    return 0;
}

__attribute__((used, visibility("default")))
void madeira_vulkan_surface_release(struct madeira_vulkan_surface_binding *binding)
{
    if (!binding || !binding->metal_view) return;

    if (madeira_vulkan_surface_bridge_ready())
        p_release_metal_view(binding->metal_view);

    fprintf(stderr, "[madeira-vulkan] WSI release hwnd=%p view=%p layer=%p\n",
            binding->hwnd, binding->metal_view, binding->metal_layer);
    fflush(stderr);

    binding->metal_view = NULL;
    binding->metal_layer = NULL;
    binding->hwnd = NULL;
}
