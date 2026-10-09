#!/usr/bin/env python3
"""Generate virtual_ios.c with Wine's winevulkan unix-call table registered.

Madeira cannot dlopen Wine unix libraries on iOS; it compiles their unix sides
into libntdll_unix.a and virtual_ios.c chooses a table by PE module name. Keep
the large, frequently-changing virtual_ios.c untouched in git and generate a
Vulkan-enabled copy only when MADEIRA_VULKAN is enabled.
"""

from __future__ import annotations

import pathlib
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch_virtual_winevulkan.py INPUT OUTPUT", file=sys.stderr)
        return 2

    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    text = src.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "extern const void *crypt32_unix_call_funcs[];",
        "extern const void *crypt32_unix_call_funcs[];\n"
        "extern const void *winevulkan_unix_call_funcs[];",
        "64-bit winevulkan table declaration",
    )
    text = replace_once(
        text,
        "extern const void *crypt32_unix_call_wow64_funcs[];",
        "extern const void *crypt32_unix_call_wow64_funcs[];\n"
        "extern const void *winevulkan_unix_call_wow64_funcs[];",
        "wow64 winevulkan table declaration",
    )

    anchor = '''        } else if (match && (strstr(match, "dwrite") || strstr(match, "DWrite"))) {'''
    replacement = '''        } else if (match && strstr(match, "winevulkan")) {
            /* Detroit/Vulkan: winevulkan.so cannot be dlopened on iOS. Its
             * unix half is compiled into libntdll_unix.a and registered here. */
            libname = "winevulkan";
            funcs64 = (const void *)winevulkan_unix_call_funcs;
            funcs_wow64 = (const void *)winevulkan_unix_call_wow64_funcs;
        } else if (match && (strstr(match, "dwrite") || strstr(match, "DWrite"))) {'''
    text = replace_once(text, anchor, replacement, "winevulkan dispatch insertion")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"patched {src} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
