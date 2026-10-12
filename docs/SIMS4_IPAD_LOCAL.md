# The Sims 4 — local iPad Pro M4 lane

## Goal

Run the Windows x86-64 build of The Sims 4 fully on the iPad Pro M4 through
Madeira. Streaming is not success. The Mac install is reference/storage only.

Initial performance target: 1280×720, Low, 30 FPS. Touch-first is the final
input goal; keyboard/mouse/controller may be used while diagnosing launch and
rendering.

## Baseline

This lane starts from `jgilles97-ctrl/Madeira` main after the October 9, 2026
sync with current upstream. Do not resurrect the older Sims branch without
proving a missing capability first.

Current Madeira already provides the important generic pieces: FEX x86-64 to
ARM64 translation, Wine ARM64EC, DXMT D3D11 to Metal, iOS 27 in-app JIT,
Memory+, a per-game library, Wine desktop launch mode, per-game config, touch
controls, keyboard/mouse/controller input, audio/video support, and 30 FPS
pacing when the bundled DXMT supports it.

A key architectural constraint is that Windows child processes are pseudo-
processes inside one iOS Mach task. Steam/Chromium work in Madeira proves that
real Chromium helpers can run under this model, but a helper fault can threaten
the whole app. Therefore EA CEF work must classify helper roles and collect
role-specific evidence before any containment/gating change is attempted.

## Gate A — launcher prerequisites and EA App

Do not jump straight into EA App. Qualify the smaller dependencies first.

### A0 — static EA prefix audit

```bash
python3 tools/sims4_ea_prefix_audit.py "/path/to/wine-prefix" \
  --json sims4-ea-prefix.json
```

This inventories and hashes:

- `EADesktop.exe`;
- `EALauncher.exe`;
- `EABackgroundService.exe`;
- `EACefSubProcess.exe`;
- `system.reg` / `user.reg` service and Network List Manager registration;
- `C:\ProgramData\EA Desktop\backgroundservice.ini` when present.

Presence of `backgroundservice.ini` does **not** mean it is stale. Proton's
current EA workaround only removes it after the Windows service is proven
`STOPPED` or `STOP_PENDING`; preserve/capture the file first and change that one
variable only.

### A1 — exact runtime audit

```bash
python3 tools/sims4_runtime_audit.py \
  --json sims4-runtime-audit.json
```

The SHA-256 runtime fingerprint binds each device run to an exact ARM64EC
runtime. Never compare two runs as though they used the same runtime unless the
fingerprint matches.

The v2 audit separates three kinds of modules:

- core runtime: D3D11, DXGI, XTAJIT64;
- generic network coverage: WinHTTP;
- physically validated Madeira launcher coverage: `netprofm.dll`, `sensapi.dll`,
  `avifil32.dll`, `msvfw32.dll`.

The last four have been built and exercised successfully in physical Madeira
secondary-launcher testing. That is stronger evidence than a guess, but it is
still **not proof EA App requires each DLL**. The branch builds them as launcher
coverage and lets the canary/import logs decide causality.

The cloud macOS lane has also now demonstrated that all four modules build from
the exact pinned Madeira Wine submodule and pinned llvm-mingw toolchain. The
workflow preserves these expensive outputs even if a later canary compilation
step fails, so one downstream failure no longer discards useful build evidence.

### A2 — small x64 launcher canary

The branch provides `tests/x64/sims4-launcher-canary.c`. The cloud macOS job
builds it as a real x86-64 Windows PE alongside the four ARM64EC coverage DLLs.

On iPad it checks, in dependency order:

1. x64/FEX execution;
2. child-process/pseudo-process handoff;
3. Service Control Manager access;
4. `EABackgroundService` registration/query, exact state and PID;
5. DirectWrite system-font enumeration and whether `Arial` resolves, while also
   recording `Liberation Sans` and `Tahoma` availability;
6. `sensapi!IsNetworkAlive`;
7. `INetworkListManager` through `netprofm.dll`;
8. raw TCP to 1.1.1.1:443;
9. WinHTTP HTTPS.

The DirectWrite probe covers a current EA/Wine failure class where
`EACefSubProcess.exe` can fail when Arial is unavailable. Do not preemptively
install or alias fonts; prove the condition first.

It deliberately does **not** call `InternetCheckConnectionW`; upstream Madeira
physical testing found that probe unsafe on the affected baseline.

Parse a device canary log with:

```bash
python3 tools/sims4_launcher_canary_parse.py launcher-canary.log \
  --json sims4-launcher-canary.json
```

The parser works the earliest failed prerequisite first. A fully passing canary
only advances to `LAUNCH_EA_APP_IN_WINE_DESKTOP`; it does not claim EA App or
The Sims 4 works.

If and only if the parsed device result proves `Arial` is missing, generate a
non-mutating remediation plan:

```bash
python3 tools/sims4_font_remediation.py sims4-launcher-canary.json \
  --json sims4-font-plan.json
```

The planner refuses to act on missing/stale evidence. When Arial is absent and
Liberation Sans is actually visible, it can propose the Wine-native
`HKCU\Software\Wine\Fonts\Replacements` alias plus a rollback command. Re-run
the identical DirectWrite canary after any manually applied change and require
`arial=1` before EA App is tested.

Networking must be tested after Madeira performs its normal JIT/VPN handoff.
Do not manually tear down the JIT VPN early: upstream device evidence shows raw
TCP/WinHTTP may report no route while the LocalDevVPN path is still active.

### A3 — EA App desktop/service/CEF qualification

First EA profile:

- launch through the Wine desktop so explorer keeps the Wine session alive;
- start Windows services first when qualifying service/RPC behavior;
- 1280×720, Fit;
- frame generation off;
- no renderer override until the log identifies a graphics problem;
- JIT and Memory+ ready;
- one variable per run;
- capture Madeira/Wine log plus EA helper command lines.

Current triage recognizes separate EA failure families: service/RPC, stale
background-service state, update/symlink behavior, MSI/update failures, DirtySDK
networking, CEF, launcher hard-error exits, missing DLLs, route/WinHTTP state,
DXMT and guest access violations.

### A4 — classify Chromium helpers

```bash
python3 tools/sims4_ea_cef_roles.py madeira-log.txt \
  --json sims4-ea-cef-roles.json
```

The classifier separates roles such as:

- `--type=gpu-process`;
- `--type=renderer`;
- `--type=utility`;
- `--utility-sub-type=network.mojom.NetworkService`.

It is observation-only. Do not kill, skip or special-case `EACefSubProcess.exe`
by executable name. Madeira has already demonstrated that Chromium can run in
its pseudo-process model; helper containment needs role-specific device evidence.

## Gate B — TS4 qualification

Only after Gate A can start `TS4_x64.exe` in the same session:

1. confirm `TS4_x64.exe` is x86-64;
2. confirm the x64/FEX/Wine launcher canary succeeds;
3. confirm the built-in x64 DX11 canary succeeds on the same Madeira runtime;
4. start TS4 at 1280×720 / Low / 30 FPS / Fit / frame generation off;
5. first success marker is a visible TS4 frame, not merely a process;
6. reach main menu;
7. load a household;
8. save, fully relaunch, and restore the save;
9. validate a small DLC sample before the full DLC set;
10. build the touch-first profile after the runtime is stable.

## Static Sims payload preflight

```bash
python3 tools/sims4_ipad_preflight.py "/path/to/The Sims 4" \
  --ea-prefix "/path/to/wine-prefix" \
  --json sims4-preflight.json
```

It checks the x86-64 PE executable, basic game folder shape, DLC inventory and,
when supplied, the expected EA binaries. `payload_ready=true` is static evidence
only.

## Device log triage

```bash
python3 tools/sims4_log_triage.py madeira-log.txt \
  --json sims4-triage.json
```

Always work the earliest high-signal failure first. Later errors are frequently
secondary noise.

## Reproducible evidence bundle v2

```bash
python3 tools/sims4_evidence_bundle.py \
  --preflight sims4-preflight.json \
  --runtime-audit sims4-runtime-audit.json \
  --ea-prefix-audit sims4-ea-prefix.json \
  --launcher-canary sims4-launcher-canary.json \
  --cef-roles sims4-ea-cef-roles.json \
  --triage sims4-triage.json \
  --run-id ipad-YYYY-MM-DD-NNN \
  --out sims4-evidence.json
```

The v2 bundle hashes and binds the game/runtime/EA-prefix/canary/CEF evidence.
Static blockers outrank the launcher canary, and a failed or incomplete launcher
canary outranks later EA/TS4 logs. This prevents stale evidence from accidentally
advancing the project. The bundle never promotes physical-device success by
itself.

## Acceptance ladder

- `P0` static game + optional EA-prefix payload validated;
- `P1` Madeira JIT + Memory+ ready;
- `P2` x64/FEX/Wine launcher canary passes;
- `P3` x64 DX11 canary passes;
- `P4` EA App UI stable, with CEF roles understood;
- `P5` EA App starts TS4;
- `P6` TS4 process survives initialization;
- `P7` first visible TS4 frame;
- `P8` main menu;
- `P9` household gameplay at the 720p/30 target;
- `P10` save/relaunch/restore;
- `P11` DLC sample validation;
- `P12` touch-first control profile;
- `P13` 30-minute stable session and three cold-launch successes.

CI/static tools cannot prove P1–P13. Physical-device evidence is required.

## Current high-risk areas

1. EA App service/RPC/update compatibility.
2. DirectWrite/font-family resolution before EA CEF startup.
3. CEF helper behavior inside Madeira's one-Mach-task pseudo-process model.
4. Guest networking after the JIT VPN handoff, especially Windows connectivity
   APIs vs raw TCP/WinHTTP.
5. iPad memory pressure once EA CEF and TS4 coexist.
6. D3D11/DXMT compatibility at TS4 initialization.
7. Full-DLC storage and memory cost after base-game repeatability.

## Improved high-leverage iteration prompt — v5

> Continue `jgilles97-ctrl/Madeira`, branch `sim4-ipad-local-v2`, PR #8 toward
> P13: The Sims 4 running fully locally on the iPad Pro M4. Streaming never
> counts. The Mac installation is reference/storage only. At every pass read
> the current branch head, PR, latest completed and queued CI jobs, preserved
> cloud artifacts, upstream Madeira/Wine/Proton changes, static game preflight,
> EA-prefix audit, exact runtime fingerprint, launcher-canary result, CEF-role
> report and newest physical-device evidence. Identify the earliest unproven
> gate and reject stale evidence whose hashes/schema no longer match. Rank
> candidate work by information gained × reversibility ÷ physical-device cost.
> Prefer a small canary that separates several hypotheses over a large EA/Sims
> launch. For EA follow this dependency order unless direct evidence disproves
> it: static prefix → exact runtime → x64/FEX/process/service canary → DirectWrite
> Arial resolution → Windows network-state APIs/raw TCP/WinHTTP → EA Wine-desktop
> launch → CEF helper-role classification → TS4 → DX11 rendering → gameplay.
> Treat the four upstream-validated ARM64EC launcher DLLs as tested runtime
> coverage, not assumed EA requirements. Preserve successful expensive cloud
> outputs even if a later build/test step fails. Never delete
> `backgroundservice.ini` unless the EA service is proven STOPPED/STOP_PENDING
> and the file is captured first. Never apply a font alias unless the same
> device canary proves Arial missing and the replacement family present; require
> the identical canary to pass after the reversible change. Never use
> `InternetCheckConnectionW` on the affected Madeira baseline. Never block an EA
> Chromium helper by executable name alone; classify its CEF role and require
> causal device evidence. Exhaust source inspection, offline/static analysis,
> host tests and cloud builds before spending a physical iPad run. When a
> hypothesis fails, record the elimination and move to a genuinely different
> discriminator. Every repeated pass must add evidence, code, a regression,
> benchmark, preserved artifact, eliminated hypothesis or more discriminating
> experiment. Never claim a physical gate from cloud/host evidence and never
> represent deterministic test iterations as iPad launches.

## Repeated-analysis coverage

The branch contains independent deterministic stress suites for:

- 678 generic Sims/Madeira diagnostic decisions;
- 678 EA-specific launcher failure decisions;
- 678 EA CEF helper-role decisions;
- 678 launcher-canary decision passes;
- 678 evidence-gated Arial remediation decisions.

That is 3,390 diagnostic decisions per Python version. The main CI tests three
Python versions, so a complete green matrix exercises **10,170 deterministic
iterations**. These are regression/decision passes, **not** 10,170 iPad launches.

## Iteration rule

A repeated run counts as progress only when it produces at least one of:

- new physical-device evidence;
- a code/configuration change;
- an eliminated hypothesis;
- a benchmark;
- a regression test;
- a new/preserved cloud build artifact;
- a more discriminating next experiment.

Do not count identical reruns as extra progress.
