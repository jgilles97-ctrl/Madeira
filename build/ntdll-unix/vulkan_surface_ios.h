#ifndef MADEIRA_VULKAN_SURFACE_IOS_H
#define MADEIRA_VULKAN_SURFACE_IOS_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Opaque-to-Vulkan lifetime record for one Wine HWND -> CAMetalLayer mapping.
 * The pointers are Objective-C objects only to the app/display shim; the Wine
 * Vulkan bridge treats them as opaque C pointers.
 */
struct madeira_vulkan_surface_binding
{
    void *metal_view;   /* retained token; release with madeira_vulkan_surface_release */
    void *metal_layer;  /* borrowed CAMetalLayer pointer, valid while token is retained */
    void *hwnd;         /* diagnostic identity */
};

int madeira_vulkan_surface_bridge_ready(void);
int madeira_vulkan_surface_acquire(void *hwnd,
                                   struct madeira_vulkan_surface_binding *binding);
void madeira_vulkan_surface_release(struct madeira_vulkan_surface_binding *binding);

#ifdef __cplusplus
}
#endif

#endif /* MADEIRA_VULKAN_SURFACE_IOS_H */
