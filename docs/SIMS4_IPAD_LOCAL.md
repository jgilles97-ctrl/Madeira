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

## Why the project is split into two independent gates

The Sims 4 itself is a 64-bit D3D11 game, but the normal Windows launch chain
also uses EA App. A launcher failure and a game/rendering failure are different
problems. Do not change both at once.

### Gate A — EA App qualification

Prove, on the iPad, that one Wine session can keep the EA launcher and its
children/services alive long enough to reach a stable signed-in/offline-capable
EA App UI and start TS4.

First profile:

- launch the EA executable inside the Wine desktop, not directly;
- enable "Start Windows services first" when testing service/RPC behaviour;
- use 1280×720, Fit;
- frame generation off;
- no renderer override unless the log proves the launcher graphics path needs
  one;
- keep JIT and Memory+ green before starting;
- capture `madeira-log.txt` from the first failure;
- change one variable per run.

Why desktop mode first: secondary launchers commonly start a real child process
and then exit. If the first Wine process exits, a direct Madeira session can
end too. Explorer staying alive removes that ambiguity.

### Gate B — TS4 qualification

Only after Gate A can start `TS4_x64.exe` in the same session:

1. confirm `TS4_x64.exe` is seen as x86-64;
2. confirm the built-in x64 DX11 cube succeeds on the same Madeira build;
3. start at 1280×720 / Low / 30 FPS / Fit / frame generation off;
4. first success marker is a visible TS4 window/frame, not merely a process;
5. next marker is main menu;
6. then load a household;
7. then save, fully relaunch, and verify the save;
8. add DLC validation after base gameplay is repeatable;
9. build the touch-first profile last so input work does not hide runtime faults.

## Static preflight

Run:

```bash
python3 tools/sims4_ipad_preflight.py "/path/to/The Sims 4" \
  --ea-prefix "/path/to/wine-prefix" \
  --json sims4-preflight.json
```

The tool checks:

- `Game/Bin/TS4_x64.exe` exists;
- it is a PE x86-64 executable;
- the basic game folder shape exists;
- DLC folders are inventoried;
- when an EA prefix is supplied, the expected EA App executables are present.

`payload_ready=true` is only a static-file gate. It does not mean the game runs.

## Log triage

After every device run:

```bash
python3 tools/sims4_log_triage.py madeira-log.txt \
  --json sims4-triage.json
```

The report separates failures into runtime/JIT, loader/DLL, EA App service/CEF,
process lifetime, graphics/DXMT, and guest crash stages. Work the *earliest*
high-signal failure first.

## Current highest-risk areas

1. **EA App / secondary-launcher support.** Madeira issue reports for other
   launchers show that services, child-process lifetime, missing 64-bit Wine
   DLLs and network-state APIs can block a launcher even after the game itself
   is otherwise runnable.
2. **EA App CEF.** Modern EA App uses Chromium subprocesses and D3D11. Keep this
   as its own qualification gate.
3. **Memory pressure.** The iPad has 8 GB unified memory. The base game is a
   better first target than the full DLC set. Measure, do not assume.
4. **DX11/DXMT compatibility.** The current game requires DirectX 11. A failing
   Madeira x64 DX11 cube means the Sims test is not yet meaningful.
5. **Storage.** The full install plus DLC is large. Stage only what is needed
   for the next gate when practical; do not duplicate tens of gigabytes inside
   the app container without a reason.

## Acceptance ladder

A run only advances one rung when there is evidence:

- `P0` static payload validated;
- `P1` Madeira JIT + Memory+ ready;
- `P2` x64/FEX/Wine canary passes;
- `P3` x64 DX11 canary passes;
- `P4` EA App UI stable;
- `P5` EA App starts TS4;
- `P6` TS4 process survives initialization;
- `P7` first visible TS4 frame;
- `P8` main menu;
- `P9` household gameplay at the 720p/30 target;
- `P10` save/relaunch/restore;
- `P11` DLC sample validation;
- `P12` touch-first control profile;
- `P13` 30-minute stable session and three cold-launch successes.

CI and static tools may prove P0 only. Physical-device evidence is required for
P1–P13.

## Iteration rule

A repeated run counts as progress only when it produces at least one of:

- new device evidence;
- one code/config change;
- one eliminated hypothesis;
- a benchmark;
- a regression test;
- a reproducibility result for an explicitly stated gate.

Do not count identical reruns as extra progress, and do not claim a gate is
passed from CI when it requires the physical iPad.
