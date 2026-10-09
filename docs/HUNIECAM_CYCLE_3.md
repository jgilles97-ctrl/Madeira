# HunieCam Studio iPad/Madeira — Cycle 3 (34 distinct passes)

Status: research + implementation cycle complete. This document does **not** claim the game is playable on iPad yet. Device acceptance still requires real iPad evidence.

This cycle deliberately avoided repeating the same search 34 times. Each pass answered a different question or implemented a different control so the first real device run produces useful evidence instead of another pile of guesses.

## Plain-English result

The project is now much harder to fool accidentally.

Before this cycle, one Madeira error label could send the project down the wrong path, two tweaks could be tested together without realizing it, and save persistence could be described with mismatched evidence types. Those weaknesses are now addressed by code and tests.

The clean first-run profile remains:

- Windows program: `HunieCamStudio.exe`
- CPU route: 32-bit x86 through Madeira WoW64 + FEX, once the owned file confirms i386
- launch: direct game launch first
- working folder: the game's/program's folder
- resolution: `1280x720`
- display mode: `fit`
- frame limit: 60 FPS
- arguments: none
- per-game compatibility config: empty
- graphics: Madeira's normal translated D3D9 frontend first
- input: touch/pointer/mouse first; controller is not an acceptance requirement
- JIT + Memory+: must be ready before the run counts

Steam's public Windows launch configuration also names `HunieCamStudio.exe` with no special arguments, so the baseline no longer depends on an invented launch command.

## 34-pass audit

| Pass | High-leverage question / action | Result |
| ---: | --- | --- |
| 1 | Did upstream Madeira move after our Oct. 6 baseline? | No newer upstream commit was found as of Oct. 9. Rebase churn would not improve HunieCam today. |
| 2 | Did the public Windows HunieCam launch route change? | Current public Steam configuration still launches `HunieCamStudio.exe` directly with no special arguments. |
| 3 | Does the public Windows depot still look like classic Unity/Mono? | Yes: old Unity managed assemblies, `Mono/mono.dll`, CSteamworks and Steam API DLLs remain the useful shape reference. Owned files still decide. |
| 4 | Can `[store-undecoded]` mean something other than a Mono JIT store? | Yes. Madeira issue #173 shows `insn=0xd4200000`, an AArch64 BRK corresponding to a guest breakpoint/INT3, under the same label. |
| 5 | What does that change for HunieCam diagnosis? | Session triage now separates the breakpoint/runtime family from real protected-memory stores and will not suggest RWX-plain for the breakpoint case. |
| 6 | Can self-modifying image faults be recognized? | Added `SEC_IMAGE WRITECOPY` detection and issue #173 routing. |
| 7 | Are known-bad old Unity Mono overrides still able to creep into our profile? | Added a config guard that rejects `mono-suspend=hybrid` and forced WX, both ruled out by issue #123 evidence. |
| 8 | Can multiple tweaks be tested together accidentally? | Config guard fails any run with more than one compatibility variable. |
| 9 | Can speculative JIT-pool changes slip through quietly? | They are explicitly warned because pool changes can worsen WoW64 virtual-address pressure. |
| 10 | Are graphics experiments separated? | `-force-d3d9` and `d3d9 = native` are different one-variable experiments with different triggers and rollback. |
| 11 | Can current logs be matched to relevant upstream Madeira issues? | Added `huniecam_issue_matcher.py` with explicit signatures and actions. |
| 12 | Can attractive but irrelevant Unity fixes be rejected? | The matcher explicitly marks IL2CPP issues #230/#232 as non-matches when preflight proves HunieCam's classic bundled Mono/no `GameAssembly.dll`. |
| 13 | Can an old 32-bit CPU-feature failure be recognized? | Added a lead for Madeira issue #116 (SSE2/CPU feature reporting) instead of misclassifying it as graphics. |
| 14 | Can a Dock wait screen hide the actual game error? | Added issue #233 recognition so a game-owned error dialog is investigated instead of treating “Waiting for its window” as the root problem. |
| 15 | Does controller trouble need to block this port? | No. Issue #90 is kept as low-relevance reference only. Pointer/touch is the acceptance baseline. |
| 16 | Is the owned runtime family recorded explicitly? | Preflight V3 records `runtime_family`, `mono_runtime_found` and `gameassembly_found`. |
| 17 | Can the two Steam API copies be identified safely? | Preflight hashes root and Unity-plugin `steam_api.dll` copies and reports whether they match; differing copies are preserved, not overwritten. |
| 18 | Is public depot metadata allowed to override the owned build? | No. It remains shape/reference data only. The actual PE, hashes, files and Unity strings win. |
| 19 | Can we reproduce the clean Madeira library entry exactly? | Added `huniecam_library_profile.py`: 32-bit, direct, 1280×720, Fit, 60 FPS, no args/config. |
| 20 | Can a bad library path escape the Wine `drive_c` tree? | The profile generator rejects absolute paths, `..`, and any program name other than `HunieCamStudio.exe`. |
| 21 | Can repeated runs be compared objectively? | Added `huniecam_attempt_ledger.py` with profile hashes and deepest-stage scoring. |
| 22 | Can an experiment that regresses be promoted by accident? | Ledger labels `REGRESSED_VS_BEST` and warns against promotion/keeping the tweak. |
| 23 | Can we notice that we are repeating the same diagnostic profile again? | Duplicate diagnostic profiles are fingerprinted and warned; intentional repeatability/acceptance repeats remain allowed. |
| 24 | Can the project decide when to stop tuning? | Added `huniecam_next_run.py`: once game code/scene evidence is reached, it switches to acceptance testing instead of piling on switches. |
| 25 | Can a true Madeira runtime bug stop title-level tweak churn? | Next-run engine returns `BLOCKED_ON_RUNTIME_EVIDENCE` for relevant runtime families such as issue #173/stale DXMT. |
| 26 | Can raw logs be shared without throwing away the useful crash details? | Added redactor for user paths, emails, tokens, pairing-like secrets while preserving addresses, instruction words, modules and status codes. |
| 27 | Can crash debugging silently fill iPad storage? | Added read-only storage guard for `fex-jit-dump.bin` and large logs. It never deletes evidence automatically. |
| 28 | Can one command produce the main diagnostic reports? | Added `huniecam_pipeline.py`: preflight → config guard → session triage → issue match → next-run decision → evidence manifest. |
| 29 | Can evidence be shared without embedding proprietary game/save/log content? | Added a manifest that stores hashes/sizes and small structured summaries; raw logs/save bytes are not embedded. |
| 30 | Was save acceptance using the right evidence type? | Found a flaw: acceptance expected a “progress written” flag from a snapshot. Snapshots cannot prove change. |
| 31 | Is the save model fixed? | `huniecam_save_probe.py verify` now requires BEFORE → AFTER progress → AFTER RELAUNCH and proves both a real write and exact tree persistence. Acceptance V2 consumes that verification. |
| 32 | Will every new HunieCam helper be tested automatically? | CI now compiles every `tools/huniecam_*.py` and discovers every `tests/test_huniecam_*.py` on Python 3.11/3.12/3.13. |
| 33 | Is the new evidence workflow documented as one coherent system? | This cycle document consolidates the baseline, decision rules, known non-matches, save lifecycle and run sequence. |
| 34 | Is the branch/PR state independently rechecked after all changes? | Final cycle step: run the expanded CI matrix, fix any failures, update PR #4, and keep it draft/unmerged until real device gates pass. |

## New/expanded tools from this cycle

### `tools/huniecam_config_guard.py`

Use before any non-default run. It tells you whether the run is clean, a recognized one-variable experiment, an unreviewed change, or invalid/confounded.

Known controlled experiments today:

- `-force-d3d9` — only when Unity chose D3D11 or graphics initialization fails before D3D9 is proven.
- `env.MADEIRA_WOW_RWX_PLAIN = 1` — only when the real evidence is Unity Mono protected-memory/store activity; never just because `store-undecoded` appears.
- `d3d9 = native` — only after Unity/D3D9 startup succeeds and the remaining measured problem is graphics-specific.

Known rejected HunieCam tweaks:

- `mono-suspend = hybrid`
- forced `MADEIRA_WX = 1` / `wx = 1`
- forcing D3D11/OpenGL/Vulkan as speculative renderer changes

`real-suspend=1` is not globally forbidden, but it is warned: it helped a modern IL2CPP title, while issue #123 found no benefit for Unity Mono. It requires new HunieCam evidence before use.

### `tools/huniecam_issue_matcher.py`

Routes signatures to relevant upstream reports without pretending a match proves identical root cause.

High-value distinction:

- real store + Mono evidence → issue #123 family may be relevant;
- `[store-undecoded] ... insn=0xd4200000` + WRITECOPY → issue #173 family; **do not** use RWX-plain as the assumed fix.

### `tools/huniecam_attempt_ledger.py`

Records each serious run as metadata:

- exact profile fingerprint;
- deepest stage;
- failure/marker codes;
- whether it improved, matched or regressed;
- whether the same diagnostic profile was already tested.

This makes “it seemed a bit better” much harder to substitute for evidence.

### `tools/huniecam_next_run.py`

Takes session + issue + prior-run evidence and decides between:

- fix prerequisite first;
- block on a Madeira runtime bug;
- clean baseline;
- one controlled A/B;
- deliberate repeatability run;
- device acceptance.

### `tools/huniecam_storage_guard.py`

Finds large crash dumps/logs but does not delete them. Upstream managed-runtime reports have produced `fex-jit-dump.bin` files hundreds of MiB in size, so this is part of keeping the project sustainable on an iPad.

### `tools/huniecam_log_redact.py`

Makes a safer copy for sharing while preserving the low-level details needed to fix Madeira itself.

### `tools/huniecam_pipeline.py`

First-run analysis example:

```sh
python3 tools/huniecam_pipeline.py \
  --install "/path/to/HunieCam Studio" \
  --madeira-log madeira-log.txt \
  --unity-log output_log.txt \
  --out-dir huniecam-evidence
```

This analyzes evidence only. It does not launch the game, modify the game files, or change the Madeira prefix.

## Save acceptance — corrected lifecycle

A save test now has four distinct proofs:

1. **BEFORE snapshot** — what existed before making new visible progress.
2. **AFTER snapshot** — taken after making visible progress and exiting normally.
3. **RELAUNCH snapshot** — taken after fully closing/reopening Madeira/game.
4. **Manual visible check** — the game itself visibly restores that same progress.

Machine verification passes only if:

- BEFORE → AFTER changed; and
- AFTER tree hash == RELAUNCH tree hash.

Even then, manual visible restoration remains required. Matching files do not prove the game successfully interpreted those files.

## Pointer acceptance

Madeira's current hardware-input design is favorable for this title: on iPad, when the program shows a cursor, hardware pointer position can be sent as absolute Windows cursor coordinates mapped to the game view. Fit mode is therefore intentionally part of the baseline: preserve aspect ratio first, then test the entire surface—corners, small targets, menus and repeated clicks.

Do not call pointer input successful merely because one large button can be clicked.

## What is still not proven

None of this code replaces the physical-device test.

The project still needs an actual iPad run proving:

1. JIT + Memory+ ready.
2. Owned i386 HunieCam build identified.
3. Windows executable starts.
4. Unity/Mono reaches real game code.
5. Real management gameplay works.
6. Rendering is correct.
7. Touch/pointer alignment works across the full screen.
8. Audio is correct.
9. The three-stage save verification passes and visible progress returns.
10. Performance/timing is acceptable in a representative busy scene.
11. 30-minute stability.
12. Three cold launches.
13. Two suspend/resume cycles.
14. The final profile reproduces from a clean Madeira start.

Until those are evidenced, the correct status is **compatibility workbench ready for device validation**, not “port complete.”

## Upstream references used in this cycle

- Madeira issue #123 — Unity/Mono/.NET/Java protected-memory/store failures and Unity-Mono experiments that were ruled out: https://github.com/willfaust/Madeira/issues/123
- Madeira issue #173 — WoW64 WRITECOPY + guest breakpoint/INT3 misdelivery: https://github.com/willfaust/Madeira/issues/173
- Madeira issue #116 — 32-bit SSE2/CPU feature reporting: https://github.com/willfaust/Madeira/issues/116
- Madeira issue #230 — IL2CPP/wintypes missing; explicit non-match for classic HunieCam Mono: https://github.com/willfaust/Madeira/issues/230
- Madeira issue #232 — modern IL2CPP `real-suspend=1`; explicit non-match unless HunieCam evidence changes runtime family: https://github.com/willfaust/Madeira/issues/232
- Madeira issue #233 — Dock start screen can hide a game-owned error dialog: https://github.com/willfaust/Madeira/issues/233
- Madeira issue #90 — Windows.Gaming.Input/HID controller path; low priority for pointer-first HunieCam: https://github.com/willfaust/Madeira/issues/90

Public Steam/SteamDB/PCGamingWiki facts are reference data only. The owned install preflight is authoritative for the executable, architecture, runtime layout and exact file hashes.
