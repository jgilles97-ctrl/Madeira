#!/usr/bin/env python3
"""Generate driver_ios.c with the optional winios Vulkan callback wired.

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

/* Detroit/MoltenVK: optional iOS Vulkan driver. Weak keeps the normal Madeira
 * build identical when build/win32u-unix/vulkan_driver_ios.c is not linked. */
extern UINT winios_pVulkanInit( UINT version, void *vulkan_handle,
                                const struct vulkan_driver_funcs **driver_funcs ) __attribute__((weak));"""

    wire_anchor = "        winios_user_driver.pUpdateDisplayDevices = winios_UpdateDisplayDevices;"
    wire_replacement = """        if (winios_pVulkanInit)
        {
            winios_user_driver.pVulkanInit = winios_pVulkanInit;
            dprintf( 2, \"[winios] Vulkan driver callback ENABLED\\n\" );
        }
        winios_user_driver.pUpdateDisplayDevices = winios_UpdateDisplayDevices;"""

    if text.count(decl_anchor) != 1:
        raise SystemExit(f"expected exactly one declaration anchor, found {text.count(decl_anchor)}")
    if text.count(wire_anchor) != 1:
        raise SystemExit(f"expected exactly one wiring anchor, found {text.count(wire_anchor)}")

    text = text.replace(decl_anchor, decl_replacement, 1)
    text = text.replace(wire_anchor, wire_replacement, 1)
    dst.write_text(text, encoding="utf-8")
    print(f"patched {src} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
