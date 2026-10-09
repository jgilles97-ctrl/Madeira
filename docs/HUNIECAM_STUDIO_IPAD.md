# HunieCam Studio on iPad through Madeira

**Status:** compatibility workbench; **not yet a playability claim**.

The goal is to run a legitimately owned Windows copy of **HunieCam Studio** locally on an M-series iPad through Madeira. Streaming does not count. A logo, menu, or one lucky launch does not count. Final success requires the physical iPad to pass the hard acceptance gates in this guide.

For the detailed research history, see `HUNIECAM_CYCLE_2.md` through `HUNIECAM_CYCLE_7.md`.

## Plain-English target

The final result must prove all of these on the iPad:

- the real Windows game launches locally;
- a real management/gameplay session works;
- taps/pointer positions are accurate across the whole screen;
- **dragging a character and releasing it actually completes the action**;
- rendering and audio are correct;
- a disposable save survives a full Madeira/game restart and visibly restores progress;
- the intended 60 FPS test cap is actually measured;
- the game remains stable for at least 30 minutes;
- three independent cold launches work;
- two suspend/resume tests work;
- the same final profile is repeatable.

Unknown evidence never counts as success.

## Authoritative runtime baseline

This branch is based on upstream Madeira:

`48f976429c189f8396e23d251d8a82f43c705922`

Cycle 7 rechecked the upstream `main` branch directly through GitHub; it still points to that October 6, 2026 commit. Do not tune HunieCam against an older fork/runtime and mistake an already-fixed Madeira bug for a title-specific problem.

PR #4 intentionally remains draft until the device gates pass.

## Known title shape

Public title/depot evidence points to an old, comparatively small Unity game:

- Steam app ID: `426000`;
- Windows executable: `HunieCamStudio.exe`;
- Windows build: 32-bit x86 in the known Steam depot;
- engine/runtime family: classic Unity/Mono, publicly identified as Unity `5.3.4f1`;
- the game carries its own Unity Mono runtime under `HunieCamStudio_Data/Mono/mono.dll`;
- configuration is expected under `HKCU\Software\HuniePot\HunieCam Studio`;
- saves are expected under `%USERPROFILE%\AppData\LocalLow\HuniePot\HunieCam Studio\`;
- the title is publicly documented as not having its own FPS cap.

References:

- https://store.steampowered.com/app/426000/
- https://steamdb.info/app/426000/
- https://www.pcgamingwiki.com/wiki/HunieCam_Studio

The owned files always outrank web metadata. `tools/huniecam_probe.py` records the actual executable architecture/hashes and runtime layout before a serious test is promoted.

## Important Cycle 7 input risk

PCGamingWiki currently notes a Windows touchscreen/stylus problem that is especially relevant to HunieCam: the game relies heavily on dragging portraits, and touch can move the portrait while **release fails to register**.

That report is **not proof the same bug exists on iPad/Madeira**. It is why Cycle 7 now has a mandatory title-specific device test.

For three separate real gameplay drags, Device Evidence V3 records four facts independently:

1. press registered;
2. movement registered;
3. release registered;
4. the game reacted to the completed drag.

All four must be true on all three trials. A normal tap/pointer grid cannot substitute for this test.

## Expected local execution path

For the known 32-bit Windows build:

`HunieCamStudio.exe (x86)`
→ Madeira WoW64/i386 guest execution
→ FEX translates x86 instructions for ARM64
→ Wine supplies Windows APIs
→ HunieCam's bundled Unity/Mono runtime runs
→ the selected Direct3D path is translated to Metal
→ the iPad displays the game.

Nothing in this project recompiles or redistributes the proprietary game.

## Clean first physical-iPad profile

Start with **no title-specific workaround**:

- executable: `HunieCamStudio.exe`;
- launch route: direct game launch first;
- working directory: game/program folder;
- resolution: **1280×720**;
- display mode: **Fit**;
- intended FPS cap: **60 FPS**;
- launch arguments: **none**;
- per-game compatibility config: **empty/default**;
- renderer override: **none**;
- JIT + Memory+: verified ready before launch.

The renderer-neutral rule is important. Let the owned Unity player select its renderer and record the actual result in Unity's `output_log.txt`. A clean Direct3D 11 selection is not automatically wrong.

## What to collect after one launch

Keep the original evidence. Do not hand-edit reports to make them pass.

At minimum collect:

- `madeira-log.txt`;
- `HunieCamStudio_Data/output_log.txt` if Unity created it;
- the exact current game folder/preflight;
- the exact config/arguments used;
- measured FPS/device-state evidence where available.

Run the current one-command evidence pipeline from the repository root:

```sh
python3 tools/huniecam_pipeline.py \
  --install "/path/to/HunieCam Studio" \
  --madeira-log "/path/to/madeira-log.txt" \
  --unity-log "/path/to/HunieCamStudio_Data/output_log.txt" \
  --out-dir huniecam-evidence
```

If no Unity log exists, omit `--unity-log` rather than inventing one.

Pipeline V8 produces the current sealed evidence set, including:

- owned-build preflight;
- config guard;
- session diagnosis;
- known upstream-issue matching;
- performance/FPS-cap/device-state analysis;
- first-failure capsule;
- provenance-locked run record;
- PE-import audit;
- bundled native-module audit;
- conservative dependency plan;
- Run Context V2 with exact per-launch identity;
- Evidence Contract V4;
- next-run decision;
- Manifest V6;
- a Device Evidence V3 template already linked to that exact run ID.

Do not reuse that generated device form for another launch.

## Current evidence versions

The schema audit intentionally fails CI if these current producers/consumers silently drift:

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

## Evidence-first triage order

Always fix the **earliest real blocker**. Do not stack speculative switches.

### 1. JIT/Memory+ prerequisite fails

Stop. That run cannot establish HunieCam compatibility. Repair the Madeira prerequisite, then repeat the unchanged clean profile.

### 2. WoW64/address-space refusal

Treat this as a runtime/address-space problem, not as ordinary RAM shortage and not as a reason to add random game options. Keep the exact address/mapping evidence.

### 3. Missing DLL

Use the current PE/native-module tools to decide what actually requested the DLL.

The dependency plan distinguishes:

- direct executable import;
- bundled native/plugin requester;
- dynamic/indirect missing dependency;
- no missing-DLL evidence.

Do not install a pile of Visual C++, DirectX, .NET, Wine Mono or DLL overrides because they are common Wine fixes. A dependency change needs exact evidence.

### 4. `store-undecoded` / protected-memory failure

Do not treat every `[store-undecoded]` label as a Unity-Mono RWX problem.

- `insn=0xd4200000` belongs to the guest-breakpoint/INT3 family and is diagnosed separately.
- A real protected-memory store plus evidence that HunieCam's Unity Mono is active can justify one controlled test of:

```ini
env.MADEIRA_WOW_RWX_PLAIN = 1
```

It is never part of the baseline and must be rolled back if it does not measurably help.

### 5. Graphics failure

Observe the actual API first.

- clean D3D11 → leave it alone;
- D3D11 tied to a graphics-init/crash problem, or graphics init fails before any API is proven → one A/B test with `-force-d3d9`;
- D3D9 is proven active and CPU/Mono startup succeeds, but a graphics-specific failure remains → a separate one-variable A/B with:

```ini
d3d9 = native
```

Never combine the two experiments in one diagnostic run.

### 6. Steam/Dock failure

Keep Steam integration separate from game compatibility. If the legitimate direct route works but Dock/Steam does not, do not start changing Unity/FEX/graphics settings to fix a Steam-layer problem.

### 7. Game/scene works but measurement is dirty

Do **not** add another compatibility switch. Repeat the same profile and collect clean performance/device evidence.

### 8. Pointer works but dragging/release fails

This is a real usability blocker for HunieCam. Record which of press, movement, release and game response failed. Do not call the port playable just because ordinary taps work.

## Why Wine Mono is not the HunieCam baseline

Madeira has Wine Mono support for Windows .NET Framework programs. HunieCam's game runtime is different: the title carries its own Unity Mono runtime and managed assemblies. Therefore downloading/enabling Wine Mono is not a default HunieCam prerequisite.

A missing Windows dependency still gets handled if the actual PE/runtime evidence names one; this rule only blocks assuming Wine Mono is required because the word "Mono" appears in both systems.

## Performance rule

HunieCam is light compared with modern 3D games, so correctness comes before chasing a large FPS number.

The clean profile intends a 60 FPS Madeira cap because the title itself is publicly documented as uncapped. The performance analyzer must see evidence that the intended cap is actually working. Sustained 90/120/144 FPS is not a valid "60 FPS baseline."

Performance comparisons are also blocked or qualified when device state makes them unfair, including serious thermal pressure or Low Power Mode.

## Save protocol

Never use the only valued save as the first test. Use a disposable save.

Current machine procedure:

1. Snapshot the expected `HunieCam Studio` LocalLow save folder **BEFORE** visible progress.
2. Make visible in-game progress.
3. Save/exit normally where the game allows.
4. Snapshot **AFTER** progress.
5. Fully close/reopen Madeira and the game.
6. Snapshot **RELAUNCH**.
7. Save Verify V2 must prove all three snapshots came from the same exact hashed source directory.
8. The exact AFTER tree must survive RELAUNCH.
9. Finally, confirm **inside the relaunched game** that the same visible progress returned.

Matching files alone never prove the game successfully interpreted the save.

## Physical Device Evidence V3

Fill the run-linked form generated by Pipeline V8. Leave unknown observations as `null`.

### Pointer grid

All nine points must pass:

- top-left, top-center, top-right;
- middle-left, center, middle-right;
- bottom-left, bottom-center, bottom-right.

### HunieCam drag/release

Run three real gameplay drags. Each trial separately records:

- press;
- movement;
- release;
- resulting game response.

Three complete passes are mandatory.

### Other manual observations

Record:

- JIT/Memory+ ready before launch;
- real management gameplay works;
- rendering is correct;
- audio is stable;
- visible save progress returns after relaunch;
- busy play feels acceptably responsive once automated performance evidence is clean;
- stable minutes;
- three visible cold-launch results;
- two suspend/resume results;
- whether the documented final profile reproduced from a clean Madeira start.

## Repeatability proof

Three manual checkboxes are not enough. Repeatability V3 takes at least three **different sealed Run Context V2 files** and requires:

- three unique run IDs;
- same owned build;
- same launch profile;
- same bundled native-module set;
- each reaches at least the required game/scene stage;
- no triaged fatal failure in the counted runs;
- the primary acceptance run is included.

## Final acceptance bundle

After the real device observations, Save Verify V2 and three sealed launches exist, run the final acceptance-bundle tool. It re-derives repeatability, evaluates Acceptance V9, revalidates the final provenance contract and writes a privacy-minimal final manifest.

An `accepted=true` result is meaningful only when its source evidence is from the real iPad. Synthetic CI happy paths test the logic; they do not certify the game.

## Hard acceptance gates

Final Acceptance V9 requires all of these:

1. owned game identity;
2. valid current evidence contract;
3. fully sealed Run Context V2;
4. current Device Evidence V3;
5. device observations tied to the same primary run;
6. JIT + Memory+ ready;
7. Windows executable launch;
8. HunieCam managed game code reached;
9. real gameplay;
10. correct rendering;
11. nine-point pointer grid;
12. three successful real gameplay drag/release trials;
13. correct audio;
14. real save write detected;
15. save tree survives relaunch;
16. exact-folder Save Verify V2 passes;
17. visibly restored save progress;
18. clean automated performance evidence;
19. acceptable observed busy-play behavior;
20. at least 30 stable minutes;
21. three visibly successful cold launches;
22. three distinct sealed cold-launch contexts;
23. two suspend/resume cycles;
24. repeatable documented final profile.

If any required result is false or unknown, the project is not accepted.

## Current verification state

Cycle 7 final helper/evidence validation passed at head `0f21c8483fa3b270bd98ab97812fef5c5cd92bbf` before the Cycle 7 documentation commits:

- broad compatibility workflow `37900821124`: Python 3.11 / 3.12 / 3.13 all green;
- evidence guardrails workflow `37900821167`: Python 3.11 / 3.12 / 3.13 all green.

These workflows proved compilation, schema synchronization, provenance/dependency logic, device/final-acceptance logic, pipeline integration, HunieCam regressions and generic Madeira log triage.

They **did not** prove physical-iPad gameplay.

## Completion rule

Do not call this project complete because Madeira builds, Wine starts, Unity shows a splash, the title menu appears, ordinary taps work, CI is green, or a synthetic acceptance fixture passes.

The project is complete only when **the actual iPad Pro M4** produces current evidence that passes every Acceptance V9 gate, including real HunieCam drag/release gameplay, save restoration and repeatability.
