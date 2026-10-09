# Detroit: Become Human on iPad — local Madeira path

Status: active engineering target. This document describes the **fully local** path. Streaming is not a success condition.

## Goal

First playable milestone:

- Apple M4 iPad with 8 GB RAM
- game executes locally through Madeira
- 1280x720-class output
- 30 FPS target
- Low settings first
- audio, controller/touch input, saves, and cutscenes working
- no remote PC or cloud rendering

The Windows minimum target for Detroit is already 720p / Low / 30 FPS, so that is the correct first performance gate rather than chasing desktop Ultra settings.

## Architecture

Detroit's PC renderer is Vulkan. It is **not** primarily a D3D11 or D3D12 title, so DXMT and `madeira-d3d12` are not the main graphics path for this game.

The intended stack is:

```text
DetroitBecomeHuman.exe (Windows x86-64)
        |
        v
FEX + Wine ARM64EC
        |
        v
Wine vulkan-1.dll / winevulkan
        |
        v
Madeira iOS Wine Vulkan driver
        |
        v
MoltenVK-Detroit (Vulkan -> Metal)
        |
        v
CAMetalLayer / Metal on Apple M4 GPU
```

CPU translation, Windows compatibility, Vulkan translation, Metal rendering, audio, input, saves, and execution all remain on the iPad.

## What is implemented now

The repository now has a reproducible local Vulkan route instead of only a design document:

- Wine's win32u Vulkan core can be enabled for the jailed-iOS build.
- MoltenVK is statically linked; the route does not depend on loading a desktop Vulkan dylib at runtime.
- Wine's guest `VK_KHR_win32_surface` request is translated to `VK_EXT_metal_surface`.
- The existing Madeira HWND -> `CAMetalLayer` bridge is reused rather than creating a second display system.
- Wine's `winevulkan` unix-call table is registered in Madeira's one-process runtime.
- ARM64EC `vulkan-1.dll` and `winevulkan.dll` are built reproducibly.
- Three x86-64 Windows canaries cover Vulkan device creation, Win32 presentation support, and 120 actual swapchain clear/present frames.
- A fourth x86-64 Windows program runs those canaries in order through the same Wine/FEX child-process path used by real Windows software.
- CI cross-compiles and validates all four Windows programs and also compiles iPhoneOS-side surface/memory canaries.

**None of that is a physical-iPad PASS yet.** The next proof must come from the real M4 iPad.

## MoltenVK-Detroit audit

Madeira currently uses `DiAvisoo/MoltenVK-Detroit` Release003 as the Detroit compatibility baseline. The default build is pinned to the immutable Release003 commit:

```text
8b511fdc5351a37c305bc246e161796ddca56b18
```

A different source revision requires an explicit `MOLTENVK_DETROIT_REF` override. That makes a future fork upgrade deliberate and reviewable instead of allowing a moved tag to silently change our renderer.

Important platform distinction: Release003's well-known fullscreen/window transition work is largely **macOS-specific** (`NSWindow` / `NSView`). It should not be counted as an iOS windowing fix. Madeira's own iOS Wine Vulkan driver and `CAMetalLayer` bridge are therefore still essential.

The fork's Detroit Metal-library cache is not macOS-only. Its shader code reads:

```text
MVK_DTR_MSL_LIBRARY_CACHE
```

and defaults that switch to enabled. When it is set to `0`, the fork bypasses both its process-wide Metal-library cache and its persistent disk-cache path and compiles the Metal library directly. That is why the first 8 GB iPad profile starts with:

```text
MVK_DTR_MSL_LIBRARY_CACHE=0
```

This is intentionally a **memory-first** choice. We can re-enable the cache only after real device measurements show that the retained Metal libraries fit comfortably.

Release003 also ships a Mac-side `compile_msl_library_cache.sh` helper for turning dumped Metal source into `.metallib` files. That helper uses the Xcode Metal command-line tool and is not an on-device iPad solution by itself.

## The 8 GB problem

The M4 GPU and CPU share the same physical memory. Detroit's Windows minimum assumes system RAM plus a discrete GPU with separate video memory. An 8 GB iPad therefore has less memory headroom than that PC layout even though the M4 is much newer and faster.

That does **not** prove the port is impossible, but it makes memory the primary project risk.

Known relevant evidence:

- Detroit's large shader-compilation workload has historically produced very high memory pressure in the Apple-Silicon compatibility work.
- successful Apple-Silicon work uses `MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM=3`;
- Release003's persistent Metal cache can consume roughly 3 GB of **disk** storage after compilation;
- its in-process cache retains `MTLLibrary` objects, which is the more important risk for an 8 GB iPad;
- Madeira therefore records app footprint/peak footprint and device pressure during serious tests.

For the iPad build, optimize **peak RAM first**, then launch time. A slower first launch is acceptable if it avoids an iPadOS out-of-memory kill.

## Detroit profile: conservative first boot

Start with these assumptions until device measurements justify increasing them:

```text
Resolution:       1280x720 or closest supported 16:9 mode
Preset:           Low
Frame target:     30 FPS
Depth of field:   Off
HDR:              Off
High-res mode:    Off
Shader source:    LZ4 compression enabled
Detroit MSL cache: disabled for the first memory baseline
Device stats:     enabled
```

The project profile is `docs/detroit-m4-8gb.cfg`.

The desktop Detroit fork recommends `MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION=1`, but current MoltenVK documents that switch as having **no effect on iOS or tvOS**. Do not count it as an iPad memory/performance lever.

## Implementation gates

Do not skip ahead. A physical-device gate is green only with evidence from the real iPad. Build/CI success is useful evidence that enables a gate, but it is not a substitute for device execution.

### Gate V0 — MoltenVK device build

**Build plumbing implemented. Physical link/runtime proof still belongs to the later device gate.**

Run:

```sh
build/moltenvk-ios/build.sh
```

Expected output:

```text
toolchains/moltenvk-detroit-ios/lib/libMoltenVK.a
```

The default source is the audited Release003 commit, and the fork's own dependency resolver is used so its matching SPIRV-Cross revision is not accidentally replaced.

### Gate V1 — Wine Vulkan integration

**Build/contract plumbing implemented.**

Acceptance already enforced by repository tests includes:

- Wine win32u Vulkan is built instead of compiled out;
- `pVulkanInit` is a strong static-link reference;
- `winevulkan` unix calls are registered in Madeira;
- host Vulkan entry points resolve to statically linked MoltenVK;
- ARM64EC guest Vulkan DLLs are produced;
- no desktop `dlopen` Vulkan dependency is required by the jailed-iOS path.

### Gate V2 — Vulkan device on the physical iPad

The first x64 canary must run through Madeira/FEX/Wine and:

1. load `vulkan-1.dll`;
2. create a Vulkan instance;
3. enumerate the Apple GPU through MoltenVK;
4. create and destroy a logical device cleanly.

### Gate V3 — Windows surface and 120 presented frames

The next two x64 canaries must:

1. create a real Win32 window;
2. create `VK_KHR_win32_surface` from the Windows side;
3. reach Madeira's iOS bridge and `VkMetalSurfaceEXT`;
4. find a presentation-capable queue;
5. create a swapchain;
6. clear/present **120 consecutive frames**;
7. exit cleanly.

The one-command controller runs V2 and V3 in the required order:

```text
MADEIRA_EXE=vulkan-device-gate-x64.exe
```

Do not launch Detroit as the next debugging step unless the log ends with:

```text
VULKAN_DEVICE=PASS
WIN32_SURFACE=PASS
PRESENTED_120_FRAMES=PASS
OVERALL=PASS
NEXT_GATE=detroit-process-and-shader-compilation
```

A failure stops the sequence immediately and marks later stages as skipped, so the first broken layer stays obvious.

### Gate V4 — Detroit process start

Only after the physical Vulkan gate is green, launch the user's legitimately owned Detroit installation. The game must reach its first shader-processing stage without a Wine loader failure, access violation, missing Vulkan function, or immediate Metal/Vulkan failure.

### Gate V5 — shader compilation on 8 GB

Record at least:

- starting app footprint;
- peak footprint;
- footprint at meaningful shader-progress checkpoints;
- available system memory/headroom;
- cache size;
- time to completion;
- iPad thermal state;
- compression setting;
- whether the Detroit Metal-library cache is enabled.

First baseline:

```text
MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM=3
MVK_DTR_MSL_LIBRARY_CACHE=0
```

If shader processing dies under memory pressure, treat memory/cache behavior as the first suspect before changing unrelated FEX or Wine code.

### Gate V6 — menu and first scene

Reach Chloe/menu, then the opening hostage mission. Automatically classify known historical Detroit/MoltenVK signatures where possible, including:

- graphics-pipeline binding crashes;
- blending on `R32Uint` attachments;
- missing vertex descriptor attributes;
- missing draw-index binding;
- float shader output targeting `R32Uint`;
- shader-interface mismatch such as `user(locn10)`;
- repeated shader recompilation/cache loops.

Do not silently patch `DetroitBecomeHuman.exe`. Third-party Mac guides include an executable hex workaround for a blur effect; that is not part of Madeira's default compatibility path. Prefer runtime/configuration fixes and keep the user's original game binaries untouched.

### Gate V7 — 30-minute stability

Play for 30 continuous minutes at 720p Low/30. No crash, iPadOS memory-pressure kill, corrupted rendering, runaway cache growth, or audio/input loss.

### Gate V8 — chapter coverage

The first mission is not enough. Use several scenes with different rendering workloads. Include `On The Run`, because that scene exposed a later shader-interface problem in earlier Detroit/MoltenVK work.

### Gate V9 — save/resume

Quit normally, relaunch, load a save, and verify the cache does not require destructive cleanup on every launch.

### Gate V10 — full-game qualification

Credits-to-credits completion is the real compatibility gate. Any scene-specific workaround must be documented and regression-tested.

## Cache policy for iPad

Do not delete shader caches automatically on every launch. Destructive cleanup hides cache bugs and makes launch performance worse.

Use this order:

1. establish the first low-memory baseline with the Detroit MSL library cache disabled;
2. preserve known-good game/runtime caches;
3. validate cache version/build identity;
4. quarantine only a cache proven incompatible;
5. regenerate only when required;
6. test the Metal-library cache as a separate optimization after memory is known safe;
7. expose destructive rebuild actions explicitly rather than doing them silently.

A future persistent-cache design must stay within the iPad app sandbox and use public Apple APIs. The Release003 Mac helper is useful research, not an on-device deployment mechanism.

## Game-file policy

Do not commit or redistribute Detroit game files, Steam authentication material, copyrighted game caches, or patched game executables. Madeira contains compatibility code, tooling, tests, and instructions. The user supplies a legitimately owned game installation.

## Current blockers, in priority order

1. **Run the one-command Vulkan gate on the physical M4 iPad.** This is the first remaining proof that CI cannot supply.
2. **Launch Detroit through the now-proven graphics path.**
3. **Keep shader compilation alive within the 8 GB memory limit.**
4. **Measure whether Release003's Metal-library cache can be safely re-enabled.**
5. **Fix any Detroit-specific shader/rendering failures that remain on iOS.**
6. **Add/verify audio, saves, controller, mouse/keyboard, then touch-first input.**
7. **Reach stable 720p/30 and 30-minute stability.**
8. **Qualify multiple chapters and eventually a full-game run.**

## Definition of progress

A document, Mac/CrossOver result, successful cross-build, or green CI run is not counted as "Detroit runs on iPad." The next major milestone is specifically:

```text
real M4 iPad
  -> x64 Windows gate starts through FEX/Wine
  -> Vulkan device PASS
  -> Windows-to-Metal surface PASS
  -> 120 consecutive presented frames PASS
```

Only then does the project advance to Detroit process start and shader compilation.
