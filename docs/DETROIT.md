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

The official Windows minimum target for Detroit is already 720p / Low / 30 FPS, so that is the correct first performance gate rather than chasing desktop Ultra settings.

## Architecture correction

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
MoltenVK-Detroit (Vulkan -> Metal)
        |
        v
Metal on Apple M4 GPU
```

CPU translation, Windows compatibility, Vulkan translation, Metal rendering, audio, input, saves, and execution all remain on the iPad.

## Why the target is now substantially more credible

During 2026, contributors working in KhronosGroup/MoltenVK issue #2054 got the full game running on Apple Silicon with a Detroit-specific MoltenVK branch. The important fixes include:

- argument-buffer/SPIRV-Cross fixes needed by Detroit's descriptor-heavy shaders;
- draw-ID handling fixes;
- workarounds for Detroit pipelines that ask for blending on `R32Uint` attachments;
- workarounds for shader/attachment type mismatches;
- a fix for a later `On The Run` shader-interface failure;
- shader-cache memory handling;
- a persistent Metal shader-library cache;
- a fullscreen/window transition fix.

`DiAvisoo/MoltenVK-Detroit` Release003 is the latest published Detroit-specific release found during the 2026-10-09 audit. It is a **reference implementation, not yet an iPad proof**. Its source still supports an iOS build target, which makes it a much better starting point than re-creating the Detroit compatibility patches from scratch.

## The 8 GB problem

The M4 GPU and CPU share the same physical memory. Detroit's Windows minimum calls for 8 GB system RAM plus a discrete GPU with its own VRAM. An 8 GB iPad therefore has less memory headroom than the minimum PC layout even though the M4 is much newer and faster.

That does **not** prove the port is impossible, but it makes memory the primary project risk.

Known relevant evidence:

- the full PC game used to stall around 98% during shader processing because saving the compiled pipeline data caused a large memory spike;
- `MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM` was required by successful Apple-Silicon runs;
- Release003 defaults to a persistent Metal shader cache that can consume roughly 3 GB of storage;
- Madeira's Memory+ / increased-memory-limit entitlement is therefore a hard prerequisite for serious testing.

For the iPad build, cache design must optimize **peak RAM first**, then launch time. A slower first launch is acceptable if it avoids a jetsam/out-of-memory kill.

## Detroit profile: conservative first boot

Start with these assumptions until device measurements justify increasing them:

```text
Resolution:       1280x720 or closest supported 16:9 mode
Preset:           Low
Frame target:     30 FPS
Depth of field:   Off
HDR:              Off
High-res mode:    Off
Shader cache:     compressed
Metal cache:      optional until memory/IO measurements are known
```

The desktop Detroit fork recommends:

```text
MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM=3
MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION=1
```

For an 8 GB iPad, **do not automatically assume maximum concurrent compilation is optimal**. More simultaneous compiler work can increase peak memory. Our iPad tuning matrix must test concurrency off/on and record peak footprint, completion time, and whether iPadOS kills the process.

## Implementation gates

Do not skip ahead. Each gate must leave a log artifact that says what passed or failed.

### Gate V0 — MoltenVK device build

Run:

```sh
build/moltenvk-ios/build.sh
```

Expected result:

```text
toolchains/moltenvk-detroit-ios/lib/libMoltenVK.a
```

The build is pinned to the Detroit Release003 source by default and uses that source tree's own dependency resolver so the required SPIRV-Cross revision is not accidentally replaced.

### Gate V1 — Wine Vulkan unix side

Madeira's Wine tree already contains `dlls/winevulkan`. The missing Madeira work is to compile/register its unix side in the same one-process iOS model used by the other Wine unix libraries.

Acceptance:

- `winevulkan.dll` loads;
- its unix-call table is registered inside Madeira;
- the host Vulkan functions resolve to the linked MoltenVK library;
- no `dlopen` dependency on an unavailable macOS dylib exists on device.

### Gate V2 — headless Vulkan probe

Before launching Detroit, run a tiny Windows x64 probe through the exact FEX/Wine path. It must:

1. load `vulkan-1.dll`;
2. create a Vulkan instance;
3. enumerate the M4 GPU through MoltenVK;
4. print Vulkan version, memory heaps, queue families, descriptor-indexing support, subgroup support, and required portability features;
5. create and destroy a logical device cleanly.

This separates CPU/Wine/Vulkan-loader failures from Detroit-specific shader problems.

### Gate V3 — presentation probe

Create a Win32 window and Vulkan swapchain through Madeira and display a clear frame on the iPad. Then render a triangle for several minutes while recording memory and frame timing.

### Gate V4 — Detroit process start

The game must reach its first shader-compilation screen without a Wine loader failure, access violation, or missing Vulkan function.

### Gate V5 — shader compilation

Measure at least:

- starting footprint;
- peak footprint;
- footprint at 50%, 90%, 98%, and completion;
- cache size;
- time to completion;
- iPad thermal state;
- whether Memory+ is active;
- compression setting;
- concurrent compilation setting.

If the process dies near 98%, treat memory/cache finalization as the first suspect before changing unrelated FEX or Wine code.

### Gate V6 — menu and first scene

Reach Chloe/menu, then the opening hostage mission. Known historical failure signatures that should be classified automatically include:

- `MVKCmdBindGraphicsPipeline` crashes;
- blending enabled on `MTLPixelFormatR32Uint`;
- missing vertex descriptor attributes;
- missing `spvDrawIndex` binding;
- float shader output targeting `R32Uint`;
- shader-interface mismatch such as `user(locn10)`;
- Metal/ShaderCache recompilation loops.

### Gate V7 — 30-minute stability

Play for 30 continuous minutes at 720p Low/30. No crash, jetsam kill, corrupted rendering, runaway cache growth, or audio/input loss.

### Gate V8 — chapter coverage

The first mission is not enough. Use several scenes with different rendering workloads. Include `On The Run`, because that scene exposed a later shader-interface bug in earlier Detroit/MoltenVK work.

### Gate V9 — save/resume

Quit normally, relaunch, load a save, and verify the cache does not require destructive cleanup on every launch.

### Gate V10 — full-game qualification

Credits-to-credits completion is the real compatibility gate. Any scene-specific workaround must be documented and regression-tested.

## Cache policy for iPad

Do not delete shader caches automatically on every launch. Destructive cleanup hides cache bugs and makes launch performance worse.

Use this order:

1. preserve a known-good cache;
2. validate cache version/build identity;
3. quarantine only a cache proven incompatible;
4. regenerate once;
5. prefer bounded/persistent cache storage;
6. expose a manual "Rebuild Detroit shader cache" action with a warning.

The desktop Release003 cache compiler is useful research, but its shell/Xcode workflow cannot simply run inside a normal iPad app. For iPad, we need one of these routes:

- generate compatible Metal libraries during a trusted Mac-side build step and package/copy them legally for the user's own game/runtime; or
- compile/cache on device using public Metal APIs without external command-line tools.

The second route is the cleaner long-term product architecture if performance and memory allow it.

## Game-file policy

Do not commit or redistribute Detroit game files, Steam authentication material, copyrighted shader caches extracted from the game, or patched executables. Madeira should contain only compatibility code, tooling, tests, and instructions. The user supplies a legitimately owned game installation.

## Current blockers, in priority order

1. **Wine Vulkan integration in Madeira's one-process iOS runtime.**
2. **MoltenVK-Detroit iOS build and link validation.**
3. **A Vulkan probe proving the bridge before the game is involved.**
4. **Peak-memory control during Detroit shader compilation on 8 GB.**
5. **Persistent shader-library cache strategy appropriate for iPad.**
6. **Scene-by-scene graphics correctness.**
7. **Performance tuning to stable 720p/30.**
8. **Touch-first controls after the core runtime is stable.**

## Definition of progress

A document or successful Mac run is not counted as an iPad-port milestone. A gate is green only when it has evidence from the real iPad or a deterministic build/test artifact that directly enables that gate.
