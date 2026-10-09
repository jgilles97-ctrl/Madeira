#!/usr/bin/env python3
"""Generate driver_ios.c with the iOS Vulkan callback wired.

This generator is invoked ONLY by the Vulkan-enabled win32u build. The Vulkan
callback is therefore a strong reference on purpose: a weak reference would not
reliably pull vulkan_driver_ios.o out of a static archive, producing a build that
looked successful but silently fell back to Wine's null Vulkan driver.

Keep the large Madeira driver source readable/upstream-friendly: this patch is
small, deterministic, and fails loudly if the expected anchors drift.
"""

from __future__ import annotations

import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch_driver_vulkan.py INPUT OUTPUT", file=sys.stderr)
        return 2

    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    text = src.read_text(encoding="utf-8")

    decl_anchor = "static struct user_driver_funcs winios_user_driver;"
    decl_replacement = """static struct user_driver_funcs winios_user_driver;

/* Detroit/MoltenVK: this generated source is used only when MADEIRA_VULKAN is
 * enabled. Keep a STRONG reference so the static linker must pull the iOS
 * Vulkan user-driver object into the app; silent nulldrv fallback is a bug. */
extern UINT winios_pVulkanInit( UINT version, void *vulkan_handle,
                                const struct vulkan_driver_funcs **driver_funcs );"""

    wire_anchor = "        winios_user_driver.pUpdateDisplayDevices = winios_UpdateDisplayDevices;"
    wire_replacement = """        winios_user_driver.pVulkanInit = winios_pVulkanInit;
        dprintf( 2, \"[winios] Vulkan driver callback ENABLED\\n\" );
        winios_user_driver.pUpdateDisplayDevices = winios_UpdateDisplayDevices;"""

    if text.count(decl_anchor) != 1:
        raise SystemExit(f"expected exactly one declaration anchor, found {text.count(decl_anchor)}")
    if text.count(wire_anchor) != 1:
        raise SystemExit(f"expected exactly one wiring anchor, found {text.count(wire_anchor)}")

    text = text.replace(decl_anchor, decl_replacement, 1)
    text = text.replace(wire_anchor, wire_replacement, 1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"patched {src} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
