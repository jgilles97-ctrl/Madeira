# HunieCam Studio on iPad through Madeira

Status: compatibility workbench, not a success claim. The goal is a real local iPad run of the legitimately owned Windows game through Madeira. Streaming is not part of this route.

## Plain-English goal

Make the Windows copy of **HunieCam Studio** run locally on an iPad using Madeira, with the game itself unchanged. A successful result means more than seeing a logo or menu: gameplay has to work, taps/clicks have to land correctly, sound must work, saves must survive a restart, and repeated launches must stay stable.

Do not call the project complete until the acceptance gates near the end of this document pass on the actual iPad.

## Why this title is a promising Madeira target

Public title metadata and the Windows depot point to a relatively small, old Unity game:

- Steam app ID: `426000`.
- Windows executable: `HunieCamStudio.exe`.
- Steam's published minimum is Windows XP SP2+, 1.2 GHz, 2 GB RAM, a DirectX 9-compatible GPU, DirectX 9.0a, and 1 GB of storage.
- The Windows build is reported as 32-bit x86 and uses Unity/Mono.
- The depot contains Unity's managed assembly layout plus `mono.dll`, `steam_api.dll`, and `CSteamworks.dll`.
- Public compatibility metadata identifies Unity `5.3.4f1` and Direct3D 9.

Those properties line up with parts Madeira now has specifically for older games: WoW64/i386 execution through FEX, a Direct3D 9 path through DXMT to Metal, Windows mouse/keyboard bridging, and per-game settings.

References used for the title facts:

- https://store.steampowered.com/app/426000/
- https://steamdb.info/app/426000/
- https://www.pcgamingwiki.com/wiki/HunieCam_Studio

The local probe in `tools/huniecam_probe.py` must still verify the actual owned copy. Public metadata is guidance, not proof that every store/build has the same executable.

## Current runtime baseline

This compatibility branch starts from upstream Madeira commit:

`48f976429c189f8396e23d251d8a82f43c705922`

Do not test HunieCam on the fork's older October 2 runtime and then tune around failures that upstream has already fixed. Between that fork point and this baseline, upstream gained substantial JIT, WoW64, input, graphics, and Unity/Mono work.

In particular, recent upstream work is directly relevant to Unity/Mono protected-memory writes. Issue `willfaust/Madeira#123` documented Unity/Mono and other managed runtimes failing on unhandled stores into RWX/JIT-backed memory. Later October 6 commits added handling for indexed pair stores and exclusive `STXR/STLXR` patterns. This does not prove HunieCam works; it means a current runtime must be the starting point before title-specific changes are justified.

## The expected execution path

If the owned executable verifies as i386, the expected path is:

`HunieCamStudio.exe (x86)`
→ Madeira WoW64 guest window
→ FEX translates x86 code to ARM64
→ Wine supplies the Windows APIs
→ Unity/Mono runs inside that Windows environment
→ Direct3D 9 goes through DXMT
→ Metal draws the image on iPad

Nothing here recompiles or modifies the proprietary game.

For graphics, use Madeira's **default D3D9 route first**. Only after a clean baseline should `d3d9 = native` be A/B tested as a single-variable experiment. Do not change five switches at once; that makes a good or bad result impossible to explain.

## Input strategy

HunieCam is mostly a pointer-driven management game. Treat it like a mouse/touch application first, not a controller game.

Baseline input order:

1. Direct iPad pointer/tap behavior on the game view.
2. iPad trackpad or mouse if available, because Madeira already maps the visible Windows cursor to the iPad pointer.
3. Keyboard only where the game actually needs it.
4. Controller-to-mouse binding only as an optional convenience after basic input passes.
5. Do not require XInput for acceptance.

The critical device test is not merely "a tap produces a click." Check the full screen: corners, small buttons, drag-like interactions if any, menus, and any resolution/aspect-ratio change. A cursor that is a few pixels off can make the game look playable while still being frustrating.

## Save-data rule

The expected Windows save family is under the Wine user's `AppData\LocalLow\HuniePot\HunieCam Studio` area. Never use Joey's only active save as the first compatibility test.

Use a disposable test save and verify:

1. launch;
2. create visible progress;
3. exit the game normally;
4. confirm the save path contains updated data;
5. fully close/relaunch Madeira;
6. start the game again;
7. confirm the same progress returns.

Preserve the prefix and saves across app rebuild/reinstall tests unless the purpose of that test is explicitly migration/recovery.

## Steam versus direct launch

The Windows depot contains Steamworks libraries. That does **not** mean every first test must go through the full Windows Steam client.

Use two separate questions:

- **Game compatibility:** can the owned `HunieCamStudio.exe` start and play in the Madeira library path?
- **Steam integration:** if the owned copy requires Steam behavior, can Madeira Dock provide what it needs?

Start with the simplest legitimate route available for the user's owned copy. If a direct library launch reaches the game but a Dock launch does not, the blocker is the launch/Steam layer, not necessarily Unity, FEX, or D3D9. Keep those diagnoses separate.

Do not bypass ownership checks or replace Steam files with cracked material. If the user's store build requires Steam, solve the legitimate Steam/Dock path.

## Preflight tool

Run from the repository root on the Mac against the owned Windows install:

```sh
python3 tools/huniecam_probe.py "/path/to/HunieCam Studio" --json huniecam-preflight.json
```

The probe is read-only. It checks:

- `HunieCamStudio.exe` exists;
- the PE architecture from the executable header;
- Unity managed-code and Mono signals;
- Steamworks DLL signals;
- Unity version strings when present;
- hashes for the executable and a few identity files;
- the recommended Madeira CPU, graphics and input route.

A hash identifies the exact tested build without redistributing the game.

Do not hand-edit the probe result to make a gate pass. If the actual build disagrees with the public metadata, update the plan from the actual evidence.

## First launch procedure

1. Use a build from this branch or a later upstream-equivalent branch that contains its needed changes.
2. In Madeira Settings, confirm JIT and Memory+ are ready.
3. Add the owned Windows executable as an isolated library entry.
4. Keep per-game compatibility settings empty/default for the first attempt.
5. Launch once.
6. Record exactly how far it gets: no window, Unity splash, main menu, new game, interactive gameplay, etc.
7. Export `madeira-log.txt` immediately after the attempt.
8. Run:

```sh
python3 tools/madeira_log_triage.py madeira-log.txt --json huniecam-triage.json
```

9. Fix the **earliest high-signal failure**, not the loudest message near the bottom of the log.
10. Repeat one controlled variable at a time.

## Triage order

### A. JIT not ready

If the log says the debugger/JIT was not attached at the pool request, stop there. The game result is invalid because the runtime prerequisite failed.

Use Madeira's current in-app JIT setup on iOS 27 where possible; current Madeira can pair in-app and uses LocalDevVPN for its loopback path. Do not diagnose HunieCam from a run where JIT was not active.

### B. `store-undecoded`

Treat `[store-undecoded]` as critical. Capture the complete first occurrence plus surrounding module/instruction lines. Recent upstream fixes closed several store forms that specifically hit Mono/.NET. If this appears on this current branch, it may identify a still-missing instruction encoding and is much more actionable than randomly toggling Wine settings.

### C. WoW64 guest-window refusal

If `[wow-window] ... refused: map too small` appears, record the address-map and memory information. HunieCam's i386 process needs Madeira's 32-bit guest window. Do not blindly increase JIT pool or swap values; those settings can make virtual-address pressure worse.

### D. Missing DLL

If `import_dll` reports a missing DLL, identify the exact module and why the game imports it. Use only a legitimate redistributable or user's own prerequisite. Madeira intentionally does not redistribute every Microsoft runtime.

### E. Graphics failure

Separate "game process is alive" from "image is correct."

Baseline: default D3D9 route.

If CPU/Mono startup is clearly successful but D3D9 fails, run one A/B test with the game's per-game config:

```ini
d3d9 = native
```

Remove it if it does not improve a measured problem. Never leave a switch merely because it sounds faster.

An old error saying a Metal library uses language version 4.1 on an OS that does not support it is a runtime-build problem seen on older Madeira/DXMT builds. Rebase/update instead of creating a HunieCam workaround for it.

### F. Steam/Dock failure

A Steam refusal or Dock error does not prove the game binary itself is incompatible. Compare with the legitimate direct library route where ownership permits. Keep a separate result for Steam integration.

## Performance targets

HunieCam is lightweight compared with the large 3D titles Madeira targets, so correctness is more important than chasing a high frame counter.

Target order:

1. no stalls/freezes;
2. correct input timing;
3. correct UI rendering and text;
4. stable audio;
5. stable save behavior;
6. smooth animation;
7. only then optimize frame pacing or power use.

Use a measured frame rate where available. The game previously received an official hotfix for runaway/high frame-rate behavior, so do not infer "more FPS is always better."

If a frame cap or vsync-like setting is needed for stable timing, record the before/after result instead of guessing.

## 21-pass research + implementation audit

This project deliberately uses repeated passes with different questions instead of repeating the same search 21 times.

| Pass | Question | Current result / implemented action |
|---|---|---|
| 1 | What exact Windows title/build are we targeting? | Steam app 426000; added a local file-identity probe so the owned copy, not web metadata, decides. |
| 2 | Is the Windows executable 32- or 64-bit? | Public evidence says x86; probe now reads the PE machine field and refuses to pretend if it differs. |
| 3 | What engine/runtime is involved? | Unity/Mono signals are expected; probe checks `Assembly-CSharp.dll`, `mono.dll` and Unity version strings. |
| 4 | What graphics API is the useful baseline? | Direct3D 9; Madeira's D3D9/DXMT path is the baseline. |
| 5 | Is the old fork runtime current enough? | No. Compatibility branch was created from current upstream instead of tuning October 2 code. |
| 6 | Is current JIT setup different from the old project state? | Yes. Current Madeira has in-app JIT/pairing on iOS 27; runbook now uses current prerequisites. |
| 7 | Is there a known Unity/Mono Madeira blocker? | Yes: protected/RWX store emulation family; triage now detects `[store-undecoded]`. |
| 8 | Did upstream move on that blocker? | Yes: recent store-emulation fixes landed; reason to retest current code before patching title behavior. |
| 9 | Is 32-bit support a first-class path? | Yes: WoW64 guest windows plus FEX i386 support; runbook treats guest-window refusal as a real root-cause class. |
| 10 | Does 32-bit D3D9 have more than one route? | Yes: emulated frontend default and optional native D3D9; runbook makes this a controlled A/B, not a default tweak. |
| 11 | Could virtual-address pressure be confused with RAM? | Yes. Triage distinguishes WoW64 map refusal and JIT address-space failure from ordinary out-of-memory. |
| 12 | Could older DXMT builds create a fake title failure? | Yes. Added detection for the reported unsupported Metal-language-version failure family. |
| 13 | Could a missing Windows prerequisite be hidden in a later crash? | Yes. Added `import_dll`/missing-DLL classification. |
| 14 | What is the best first input mode? | Pointer/tap and real mouse/trackpad, not XInput. Existing hardware-input path is explicitly part of acceptance. |
| 15 | What about Steamworks? | Probe inventories Steam DLLs; runbook separates direct game compatibility from Steam/Dock integration. |
| 16 | How do we identify exactly what was tested without sharing the game? | SHA-256 identity hashes in the read-only preflight report. |
| 17 | How do we prevent a one-off lucky launch from being called success? | Acceptance requires repeated cold launches, suspend/resume and a sustained session. |
| 18 | How do we protect saves? | Disposable test save first; persistence after full relaunch is a separate gate. |
| 19 | How do we stop speculative switch creep? | Default baseline, one-variable A/B, documented rollback for every non-default. |
| 20 | How do we make failures actionable for Codex/maintainers? | Machine-readable preflight + log-triage JSON, original log preserved, exact build SHA and device state recorded. |
| 21 | How do we keep this from regressing? | Synthetic unit tests and GitHub CI cover the title probe and newly important log signatures on Python 3.11/3.12/3.13. |

## Acceptance gates

A gate passes only with evidence from the actual iPad run.

1. **Build/runtime:** correct Madeira branch/build installed; JIT and Memory+ ready.
2. **Owned game identity:** preflight records the actual executable architecture/hash and expected Unity/Mono layout, or accurately documents a different layout.
3. **Launch:** `HunieCamStudio.exe` reaches a usable game screen through the chosen legitimate route.
4. **Gameplay:** start/continue a real session and interact with the management loop, not only the title screen.
5. **Image:** text, sprites, windows/panels and effects render without blocking corruption, persistent black areas or wrong scaling.
6. **Pointer:** taps/clicks line up across the whole game surface; menus and small targets are reliable.
7. **Keyboard/mouse:** when attached, real pointer and relevant keys work without stuck input or double delivery.
8. **Sound:** music/effects play normally with no persistent crackle, silence or runaway latency.
9. **Save:** a disposable test save survives a full game exit and Madeira relaunch.
10. **Performance:** frame pacing is measured during a representative busy scene; no runaway-speed behavior.
11. **Stability:** at least a 30-minute representative run without crash/freeze.
12. **Cold launch:** three full launches in a row reach the usable game state.
13. **Suspend/resume:** two background/foreground cycles return without broken image, audio, input or save state.
14. **Rollback:** every non-default per-game switch used has a recorded reason and can be removed independently.
15. **Repeatability:** final launch steps and per-game config reproduce the result from a clean Madeira start.

## Evidence bundle for every serious run

Keep these together:

- Madeira commit SHA/release;
- iPad model and iPadOS version;
- JIT method and JIT/Memory+ ready state;
- `huniecam-preflight.json`;
- original `madeira-log.txt`;
- `huniecam-triage.json`;
- exact per-game config text;
- launch route (direct library or Dock/Steam);
- stage reached;
- input/audio/save result;
- measured frame rate/frame-time if available;
- crash/exit code if any;
- screenshots or screen recording where appropriate;
- one sentence naming what changed from the previous run.

Do not put passwords, Steam tokens, pairing credentials, or proprietary game files into reports.

## Completion rule

The project is **not complete** because research looks favorable, because the app builds, because Wine starts, because Unity shows a splash, or because the main menu appears.

It is complete only when the acceptance gates above pass on the iPad with current evidence. Until then, report the deepest proven stage and the single earliest blocker.
