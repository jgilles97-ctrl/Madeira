#!/usr/bin/env python3
"""Prepare Detroit's compute writeback canary for strict MinGW/Vulkan builds.

Two intentionally small, fail-closed transformations live here instead of
weakening compiler warnings:
1. Compile the portability-subset helper only when the Vulkan headers expose
   VK_KHR_portability_subset. Older headers otherwise see an unused function.
2. Use Vulkan's normal GLSL450 SPIR-V memory model instead of the old sample's
   deprecated Simple memory model.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"error: {label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch(text: str) -> str:
    helper = '''static int has_extension(const VkExtensionProperties *exts, uint32_t count,
                         const char *name)
{
    uint32_t i;
    for (i = 0; i < count; ++i)
        if (!strcmp(exts[i].extensionName, name)) return 1;
    return 0;
}
'''
    wrapped = '''#ifdef VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME
static int has_extension(const VkExtensionProperties *exts, uint32_t count,
                         const char *name)
{
    uint32_t i;
    for (i = 0; i < count; ++i)
        if (!strcmp(exts[i].extensionName, name)) return 1;
    return 0;
}
#endif
'''
    text = replace_once(text, helper, wrapped, "portability-subset helper")

    text = replace_once(
        text,
        '(3u << 16) | OP_MEMORY_MODEL, 0, 0,',
        '(3u << 16) | OP_MEMORY_MODEL, 0, 1,',
        "SPIR-V Logical/GLSL450 memory model",
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = patch(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out, encoding="utf-8")
    print(f"PASS: wrote portable Vulkan-valid compute canary to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
