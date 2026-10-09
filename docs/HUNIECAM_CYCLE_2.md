# HunieCam Studio iPad/Madeira — research + implementation cycle 2

This is the second 21-pass cycle. It continues the existing workbench rather than restarting it. The rule is the same: each pass answers a different question or closes a different implementation gap.

## Resulting first-run profile

Use this for the first real iPad run unless the owned files contradict preflight:

- Launch route: **direct game** first; test Madeira Dock separately.
- Program: `HunieCamStudio.exe`.
- Working folder: the game/program folder (Madeira's direct-launch default).
- Resolution: **1280×720** for the first run.
- Display: Fit.
- Frame limit: **60 FPS**.
- Launch arguments: none.
- Per-game config: empty/default.
- Graphics: Madeira's default translated D3D9 frontend.
- Input: touch/pointer first; mouse/trackpad as the precision reference.
- Wine Mono download: **not required for HunieCam's own Unity runtime**.
- Save testing: disposable test save only until persistence is proven.

Why 1280×720 instead of an iPad-shaped default: Madeira's current 11-inch-iPad default is about 1152×800, while HunieCam is an older 16:9-era Unity title, its documented resolution support tops out at 1600×900, and Valve's Deck compatibility notes say the game does not support the Deck's native screen resolution. Start from a common 16:9 PC mode and test screen-shaped modes only after correctness.

## Second 21-pass audit

| Pass | Question | Finding / implementation |
|---|---|---|
| 1 | Did upstream Madeira move again after the Oct. 6 baseline? | No newer upstream commit was found; the compatibility branch is still based on the latest upstream head found in this cycle. |
| 2 | Does HunieCam need Madeira's downloadable Wine Mono? | No for the game's Unity runtime: the Windows depot ships `HunieCamStudio_Data/Mono/mono.dll` and its own managed assemblies. The preflight now reports this explicitly. |
| 3 | Could Wine-Mono-specific Madeira optimizations be wrongly assumed to cover HunieCam? | Yes. Madeira's current WoW64 docs explicitly say Unity's own Mono is not auto-matched by the Wine-Mono RWX optimization. |
| 4 | Is there a controlled fallback for Unity Mono RWX/store storms? | Yes. `env.MADEIRA_WOW_RWX_PLAIN = 1` is now a conditional one-variable A/B experiment, never a default. |
| 5 | Can one iPad run automatically choose that experiment? | Yes. Added `tools/huniecam_session_triage.py`; it recommends the RWX A/B only when the logs show Unity Mono plus protected-memory store evidence. |
| 6 | Can we distinguish a JIT failure from a title failure? | Yes. Session triage makes missing JIT/Memory+ the highest-priority prerequisite and refuses to recommend graphics tuning first. |
| 7 | Can we distinguish 32-bit virtual-address failure from RAM pressure? | Yes. Session triage has a separate WoW64 map-refusal lane. |
| 8 | What if Unity unexpectedly chooses D3D11? | The old Unity player supports `-force-d3d9`; the session tool recommends it only when the Unity log actually shows D3D11. |
| 9 | Should `-force-d3d9` be a default argument? | No. D3D9 is the expected baseline; adding a redundant switch hides whether the normal route works. |
| 10 | What if D3D9 starts but rendering crashes? | The next controlled graphics A/B is `d3d9 = native`, with an explicit rollback. |
| 11 | How do we know Unity itself initialized? | Session triage reads old Unity `output_log.txt` markers such as `Initialize engine version`, `GfxDevice`, and `Begin MonoManager ReloadAssembly`. |
| 12 | How do we know the actual game assembly loaded? | It detects `Assembly-CSharp.dll` loading separately from engine startup. |
| 13 | What resolution is least likely to create a false UI/display failure? | 1280×720 baseline; device-shaped resolution is deferred until the game is otherwise correct. |
| 14 | What frame policy is safest for this click-heavy older title? | 60 FPS baseline. The game is documented as uncapped, so uncapped mode is not useful as the first correctness test. |
| 15 | Does the Windows depot have a simple launch entry? | Yes. Steam lists one Windows launch program: `HunieCamStudio.exe`. |
| 16 | Can working-directory mistakes break Steam/API DLL discovery? | Potentially. The depot has Steam API DLLs both beside the EXE and in Unity Plugins. Madeira's direct launch already defaults to the program's folder; the preflight now records that requirement. |
| 17 | Can the owned install be compared to the known public depot without redistributing it? | Yes. Preflight v2 checks the depot's expected file shape and records identity hashes while treating the owned files as authoritative. |
| 18 | Do we have to treat Steam/Dock as part of core runtime compatibility? | No. Session triage keeps Steam initialization in a separate lane so FEX/Wine/D3D9 success is not confused with Steamworks integration. |
| 19 | Can Steam Cloud rescue a broken save workflow? | No known native Steam Cloud support is documented for HunieCam. Added a read-only save fingerprint tool to prove save writes and relaunch persistence ourselves. |
| 20 | Can save testing avoid exposing personal/proprietary contents? | Yes. `tools/huniecam_save_probe.py` records relative names, byte sizes, SHA-256 fingerprints and an aggregate tree hash; it never outputs file contents or absolute parent paths. |
| 21 | Are these new decisions regression-tested? | Added synthetic tests for session diagnosis, depot-shape/preflight v2 and save persistence; CI runs all HunieCam tools on Python 3.11, 3.12 and 3.13. |

## One-run evidence command sequence

On the Mac, before the first iPad test:

```sh
python3 tools/huniecam_probe.py "/path/to/HunieCam Studio" \
  --json huniecam-preflight.json
```

After the iPad run, preserve `madeira-log.txt` and, if Unity created it, `HunieCamStudio_Data/output_log.txt`, then run:

```sh
python3 tools/huniecam_session_triage.py \
  --madeira-log madeira-log.txt \
  --unity-log output_log.txt \
  --preflight huniecam-preflight.json \
  --json huniecam-session.json
```

The output reports the deepest proven startup stage, the high-signal failure family, and **one** next experiment.

## Save proof sequence

The expected Windows save location is under:

`%USERPROFILE%\AppData\LocalLow\HuniePot\HunieCam Studio\`

Before creating progress:

```sh
python3 tools/huniecam_save_probe.py snapshot "/path/to/save/folder" \
  --json huniecam-save-before.json
```

After making visible progress and exiting normally:

```sh
python3 tools/huniecam_save_probe.py snapshot "/path/to/save/folder" \
  --json huniecam-save-after.json
python3 tools/huniecam_save_probe.py compare \
  huniecam-save-before.json huniecam-save-after.json
```

After fully relaunching Madeira and HunieCam, snapshot again. A stable post-relaunch tree plus visible in-game progress closes the persistence gate.

## Conditional experiment ladder

Do not skip levels.

1. **Clean baseline** — 1280×720, 60 FPS, default D3D9, no config switches.
2. **JIT/Memory+ failure** — fix the runtime prerequisite and repeat level 1 unchanged.
3. **Missing DLL** — satisfy only the exact legitimate prerequisite and repeat.
4. **Unity selected D3D11** — add only `-force-d3d9`.
5. **Unity Mono protected-memory/store evidence** — preserve the original log, then A/B only `env.MADEIRA_WOW_RWX_PLAIN = 1`.
6. **D3D9 reached but graphics crash/corruption remains** — A/B only `d3d9 = native`.
7. **Steam API fails after game/runtime startup** — compare direct launch with legitimate Madeira Dock launch.
8. **Game assembly/scene startup succeeds** — stop compatibility tuning and move to gameplay/input/audio/save/stability acceptance.

## Sources used in cycle 2

- SteamDB app/depot/configuration for app 426000 and depot 426001.
- PCGamingWiki HunieCam Studio page for save path, Steam Cloud status, video/FPS/resolution behavior.
- Unity command-line documentation for old Windows standalone players, including `-force-d3d9` and `output_log.txt` behavior.
- Current Madeira `docs/WOW64.md`, `Library.swift`, upstream commit history, and issue #123.

These public sources guide the plan; the actual owned files plus iPad logs decide what is true for the tested build.
