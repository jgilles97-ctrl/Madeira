# HunieCam Studio on iPad through Madeira

**Status:** compatibility workbench; **not yet a playability claim**.

The goal is to run a legitimately owned Windows copy of **HunieCam Studio** locally on the iPad through Madeira. Streaming does not count. A splash screen, menu, mouse-only success, one lucky launch, or green CI does not count as completion.

For the detailed research history, see `HUNIECAM_CYCLE_2.md` through `HUNIECAM_CYCLE_7.md`.

## Plain-English finish line

The actual iPad must prove:

- the Windows game launches locally;
- real management gameplay works;
- taps/pointer positions are accurate across the whole surface;
- **three real gameplay drag/releases succeed using one consistent finger-based Madeira input mode**;
- rendering and audio are correct;
- a disposable save survives a full restart and visibly restores progress;
- the intended 60 FPS test cap is measured, not assumed;
- at least 30 representative minutes remain stable;
- three independent cold launches work;
- two suspend/resume cycles work;
- the documented final profile reproduces from a clean Madeira start.

Unknown evidence never counts as success.

## Authoritative baseline

Upstream Madeira `main` was rechecked directly through GitHub during Cycle 7 and still points to:

`48f976429c189f8396e23d251d8a82f43c705922`

That is the October 6, 2026 upstream commit already incorporated into this branch/fork history. Do not tune HunieCam against an older Madeira runtime and mistake an already-fixed runtime bug for a game-specific problem.

PR #4 intentionally remains draft until the device gates pass.

## Known title shape

Public title/depot evidence points to an old, comparatively small Unity title:

- Steam app ID: `426000`;
- Windows executable: `HunieCamStudio.exe`;
- known Steam Windows build: 32-bit x86;
- classic Unity/Mono, publicly identified as Unity `5.3.4f1`;
- bundled Unity Mono under `HunieCamStudio_Data/Mono/mono.dll`;
- configuration expected under `HKCU\Software\HuniePot\HunieCam Studio`;
- saves expected under `%USERPROFILE%\AppData\LocalLow\HuniePot\HunieCam Studio\`;
- publicly documented as having no native FPS cap.

References:

- https://store.steampowered.com/app/426000/
- https://steamdb.info/app/426000/
- https://www.pcgamingwiki.com/wiki/HunieCam_Studio

Owned files always outrank web metadata. `tools/huniecam_probe.py` records the actual architecture/hashes/runtime layout.

## The title-specific touch risk

PCGamingWiki currently notes a Windows touchscreen/stylus failure especially relevant to HunieCam: portraits can move while the **release does not register**.

That is a reason to test the risk, **not proof the same bug exists on iPad/Madeira**.

Cycle 7 therefore records three real gameplay drag trials. Every trial must separately prove:

1. press registered;
2. movement registered;
3. release registered;
4. the game reacted to the completed drag.

Final touch acceptance has two additional rules:

- all three passing trials must use one consistent finger-based Madeira mode: `direct_finger` **or** `touch_pointer`;
- hardware mouse/trackpad success is useful diagnosis, but **cannot substitute for touch-first iPad success**.

Using a mouse can answer “is this a touch-only problem?” It cannot close the project.

## Clean first physical-iPad profile

Start with no title-specific workaround:

- executable: `HunieCamStudio.exe`;
- direct game launch first;
- working directory: game/program folder;
- resolution: **1280×720**;
- display: **Fit**;
- intended cap: **60 FPS**;
- launch arguments: none;
- per-game compatibility config: empty/default;
- renderer override: none;
- JIT + Memory+: verified ready before launch.

The renderer-neutral rule matters. Let the owned Unity player select its renderer and record the result in Unity's `output_log.txt`. A clean Direct3D 11 selection is not itself a failure.

## What to collect after one launch

Keep original evidence. Never hand-edit a result to make a gate pass.

At minimum:

- `madeira-log.txt`;
- `HunieCamStudio_Data/output_log.txt` if Unity created it;
- the exact owned game folder/preflight;
- exact config/arguments;
- measured FPS/device-state evidence where available.

Run the current evidence pipeline from the repository root:

```sh
python3 tools/huniecam_pipeline.py \
  --install "/path/to/HunieCam Studio" \
  --madeira-log "/path/to/madeira-log.txt" \
  --unity-log "/path/to/HunieCamStudio_Data/output_log.txt" \
  --out-dir huniecam-evidence
```

If no Unity log exists, omit `--unity-log` rather than inventing one.

Pipeline V8 produces the current sealed evidence set:

- owned-build preflight;
- config guard;
- session diagnosis;
- known upstream-issue matching;
- performance/FPS-cap/device-state analysis;
- first-failure capsule;
- provenance run record;
- PE import audit;
- bundled native-module audit;
- conservative dependency plan;
- Run Context V2 exact launch identity;
- Evidence Contract V4;
- next-run decision;
- Manifest V6;
- Device Evidence V3 template already linked to that exact run ID.

Do not reuse that device form for another launch.

## Current evidence formats

The schema audit intentionally fails CI if current producers/consumers silently drift:

| Evidence | Current format |
|---|---|
| Preflight | `MADEIRA_HUNIECAM_PROBE_V4` |
| Session | `MADEIRA_HUNIECAM_SESSION_V3` |
| Config guard | `MADEIRA_HUNIECAM_CONFIG_GUARD_V2` |
| Performance | `MADEIRA_HUNIECAM_PERFORMANCE_V2` |
| Run record | `MADEIRA_HUNIECAM_RUN_RECORD_V1` |
| Run context | `MADEIRA_HUNIECAM_RUN_CONTEXT_V2` |
| PE imports | `MADEIRA_HUNIECAM_PE_IMPORTS_V1` |
| Native modules | `MADEIRA_HUNIECAM_NATIVE_MODULES_V1` |
| Device evidence | `MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3` |
| Save verify | `MADEIRA_HUNIECAM_SAVE_VERIFY_V2` |
| Repeatability | `MADEIRA_HUNIECAM_REPEATABILITY_V3` |
| Evidence contract | `MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4` |
| Acceptance | `MADEIRA_HUNIECAM_ACCEPTANCE_V9` |
| Manifest | `MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V6` |
| Pipeline | `MADEIRA_HUNIECAM_PIPELINE_V8` |

## Evidence-first triage

Always fix the **earliest proven blocker**. Do not stack speculative switches.

### JIT/Memory+ failure

Stop. Repair the Madeira prerequisite and repeat the unchanged clean profile.

### WoW64/address-space refusal

Treat it as a runtime/address-space problem. Do not confuse it with ordinary RAM shortage or pile on game settings.

### Missing DLL

Use the PE/native-module evidence. The dependency planner separates:

- direct executable import;
- bundled native/plugin requester;
- dynamic/indirect unknown requester;
- no missing-DLL evidence.

Do not install generic VC++/DirectX/.NET/Wine-Mono packages without exact evidence.

### Protected-memory / `store-undecoded`

Do not assume every `[store-undecoded]` is Unity-Mono RWX.

- `insn=0xd4200000` is the separate guest-breakpoint/INT3 family.
- A real protected-memory store plus evidence that HunieCam's Unity Mono is active can justify one controlled test of:

```ini
env.MADEIRA_WOW_RWX_PLAIN = 1
```

It is never baseline and must be rolled back if it does not measurably improve the run.

### Graphics

Observe the actual API first:

- clean D3D11 → leave it alone;
- D3D11 tied to graphics-init/crash evidence, or graphics init fails before an API is proven → one `-force-d3d9` A/B;
- D3D9 is proven and the remaining failure is graphics-specific → separate `d3d9 = native` A/B.

Never combine renderer experiments in one diagnostic run.

### Steam/Dock

Keep Steam integration separate from direct game compatibility. Do not change Unity/FEX/graphics settings to fix a Dock-only problem.

### Game works but performance evidence is dirty

Repeat the unchanged profile for a clean measurement. Do not add another compatibility switch.

### Pointer works but touch drag/release fails

That is a real HunieCam usability blocker. Test with a hardware mouse/trackpad only to diagnose whether the problem is touch-specific. Mouse success still does not satisfy touch-first acceptance.

## Why Wine Mono is not baseline

Madeira supports Wine Mono for Windows .NET Framework programs. HunieCam instead carries its own Unity Mono runtime and managed assemblies. Wine Mono is therefore not a default HunieCam prerequisite.

This does not block installing an exact Windows prerequisite if the real PE/runtime evidence names one.

## Performance rule

The clean profile intends a 60 FPS Madeira cap because the title itself is publicly documented as uncapped. The analyzer must actually measure evidence that the intended cap works. Sustained 90/120/144 FPS is not a valid “60 FPS baseline.”

Serious thermal pressure and Low Power Mode also block clean performance comparisons.

## Save protocol

Use a disposable save first.

1. Snapshot the expected `HunieCam Studio` LocalLow folder **BEFORE** progress.
2. Make visible progress.
3. Save/exit normally where possible.
4. Snapshot **AFTER**.
5. Fully close/reopen Madeira and the game.
6. Snapshot **RELAUNCH**.
7. Save Verify V2 must prove all three snapshots came from the same exact hashed source directory.
8. The post-progress tree must survive relaunch.
9. Confirm **inside the relaunched game** that the same visible progress returned.

Matching files alone never prove semantic save restoration.

## Device Evidence V3

Fill the run-linked form generated by Pipeline V8. Unknown observations remain `null`.

### Nine-point pointer grid

All must pass:

- top-left, top-center, top-right;
- middle-left, center, middle-right;
- bottom-left, bottom-center, bottom-right.

### Three touch drag/release trials

Each records:

- `input_mode`;
- press;
- movement;
- release;
- resulting game response.

For final acceptance:

- all three outcomes must be complete successes;
- all three must use the **same** input mode;
- that mode must be `direct_finger` or `touch_pointer`.

`hardware_mouse` and trackpad-type modes remain diagnostic only.

### Other required observations

Record:

- JIT/Memory+ ready;
- real management gameplay;
- correct rendering;
- stable audio;
- visible save restoration;
- acceptable busy-play responsiveness after automated performance evidence is clean;
- stable minutes;
- three visible cold-launch trials;
- two suspend/resume trials;
- final-profile repeatability.

## Repeatability V3

Three manual checkboxes are not enough. Repeatability V3 requires at least three **different sealed Run Context V2 files** with:

- unique run IDs;
- same owned build;
- same launch profile;
- same bundled native-module set;
- required game/scene depth;
- no triaged fatal failure;
- the primary acceptance run included.

## Final Acceptance V9

All required gates must pass:

1. owned game identity;
2. valid current evidence contract;
3. fully sealed Run Context V2;
4. current Device Evidence V3;
5. same-run device observations;
6. JIT + Memory+ ready;
7. Windows launch;
8. HunieCam managed game code;
9. real gameplay;
10. correct rendering;
11. nine-point pointer grid;
12. **three successful real gameplay drags in one consistent finger-based Madeira mode**;
13. correct audio;
14. real save write;
15. save tree survives relaunch;
16. exact-folder Save Verify V2;
17. visibly restored save progress;
18. clean automated performance evidence;
19. acceptable busy-play behavior;
20. >=30 stable minutes;
21. three visibly successful cold launches;
22. three distinct sealed cold-launch contexts;
23. two suspend/resume cycles;
24. repeatable final profile.

False or unknown means not accepted.

## Current verification state

Latest code-test head for Cycle 7 touch-first hardening:

`bcc041152223f6438ecdde7b1fd472e700a46223`

- broad compatibility workflow `37901397569`: Python 3.11 / 3.12 / 3.13 all green;
- evidence guardrails workflow `37901397765`: Python 3.11 / 3.12 / 3.13 all green.

The tests explicitly prove that hardware-mouse drag success cannot satisfy touch acceptance, mixed finger modes cannot masquerade as one repeatable profile, and consistent `touch_pointer` can pass when all other evidence passes.

These workflows prove the **tooling and gates**, not physical-iPad gameplay.

## Completion rule

Do not call this complete because Madeira builds, Wine starts, Unity opens, the title menu appears, ordinary taps work, a hardware mouse can drag, CI is green, or a synthetic acceptance fixture passes.

The project is complete only when the **actual iPad Pro M4** produces current evidence that passes every Acceptance V9 gate, including touch-first HunieCam drag/release gameplay, save restoration and repeatability.
