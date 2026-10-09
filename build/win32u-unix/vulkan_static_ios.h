#ifndef MADEIRA_VULKAN_STATIC_IOS_H
#define MADEIRA_VULKAN_STATIC_IOS_H

/*
 * Preincluded only while compiling Wine's dlls/win32u/vulkan.c for iOS.
 * Wine normally dlopen()s libvulkan and dlsym()s two loader entry points.
 * A jailed iOS app links MoltenVK statically, so redirect those three dlfcn
 * calls to a tiny deterministic shim instead of teaching Wine about a fake
 * dylib path.
 */

#include <dlfcn.h>

void *madeira_vulkan_dlopen(const char *path, int mode);
void *madeira_vulkan_dlsym(void *handle, const char *name);
int madeira_vulkan_dlclose(void *handle);

#define dlopen(path, mode) madeira_vulkan_dlopen((path), (mode))
#define dlsym(handle, name) madeira_vulkan_dlsym((handle), (name))
#define dlclose(handle) madeira_vulkan_dlclose((handle))

#endif /* MADEIRA_VULKAN_STATIC_IOS_H */
