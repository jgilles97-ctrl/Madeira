# HunieCam Studio iPad/Madeira — Cycle 5 (34 distinct passes)

Status: research + implementation complete; final CI must remain green. This cycle **does not** claim HunieCam is playable on iPad. A physical iPad run is still required.

## Plain-English result

Cycle 5 makes the evidence chain much harder to mix up or accidentally overstate.

The biggest changes are:

- every serious run can now be tied to the exact owned HunieCam binary by hashes;
- two runs from different binaries are rejected as an A/B comparison;
- the 60 FPS baseline must be measured as actually active, because HunieCam itself is publicly documented as uncapped;
- configuration stored in the Windows/Wine registry is kept separate from LocalLow save data;
- final acceptance requires valid machine evidence, not only manual checkboxes;
- a compact redacted first-failure capsule is generated for fast Madeira-runtime diagnosis;
- the next-run engine cannot jump to final acceptance when the profile/evidence/performance measurement is invalid.

## Clean baseline after Cycle 5

- program: `HunieCamStudio.exe`
- owned PE must prove 32-bit x86 before the route is trusted
- launch: direct game launch first; Steam/Dock remains a separate layer
- working folder: game/program folder
- resolution: `1280x720`
- display: `Fit`
- target cap: 60 FPS
- launch arguments: none
- per-game compatibility config: empty
- renderer override: **none**
- actual Direct3D API: observe it in Unity `output_log.txt`; do not guess
- JIT + Memory+: ready before the run counts
- capture: `madeira-log.txt` + Unity `output_log.txt`

DirectX 9 support is a minimum title compatibility reference, not proof that every clean run must choose D3D9. A naturally selected D3D11 path is left alone unless the evidence ties it to a graphics failure.

## 34-pass audit

| Pass | Question / implementation | Result |
| ---: | --- | --- |
| 1 | Did upstream Madeira move after the Oct. 6 baseline? | No newer upstream commit was found during this cycle. Rebase churn still provides no value. |
| 2 | Did the Windows HunieCam depot move? | Public reference still shows Windows depot 426001 last updated July 18, 2020. Owned files remain authoritative. |
| 3 | Is single-player inherently internet-dependent on the currently tested SteamOS/Deck build? | Steam Deck compatibility metadata reports no internet requirement for setup or single-player. This supports keeping Steam/Dock authorization separate from core game-runtime testing; it does not prove the Windows Steam DLLs are irrelevant. |
| 4 | Where does the Windows title keep configuration? | Public reference places HunieCam settings under `HKCU\Software\HuniePot\HunieCam Studio`. |
| 5 | Where does it keep Windows saves? | LocalLow remains the separate save lane: `%USERPROFILE%\AppData\LocalLow\HuniePot\HunieCam Studio\`. |
| 6 | Is 1280×720 within the title's own display range? | Yes. Public reference lists built-in widescreen choices up to 1600×900. |
| 7 | Does the title supply its own FPS cap? | Public reference reports no native FPS cap, so Madeira's 60 FPS setting must be measured rather than assumed. |
| 8 | Was every tool using Cycle 4's renderer-neutral rule? | No. Preflight/config-guard wording still carried an older D3D9-baseline assumption. Corrected. |
| 9 | Can preflight state the renderer rule unambiguously? | Probe V4 now says no renderer override; actual API must be observed in Unity's log. DirectX 9.0a is only the minimum graphics reference. |
| 10 | Can one run be tied to an exact owned binary? | Added `huniecam_run_record.py`, joining game hashes, launch profile, session stage/failures and optional performance. |
| 11 | Can a deterministic build identity survive path/location changes? | Run record builds a fingerprint from executable and runtime/game hashes rather than host paths. |
| 12 | Can an updated/replaced EXE masquerade as a successful A/B tweak? | No. Run comparison V2 returns `INVALID_PROVENANCE` when owned-build fingerprints differ. |
| 13 | Can performance comparisons silently change resolution/display/FPS? | Run records expose those fields and run comparison reports whether the performance baseline stayed the same. |
| 14 | Can a supposed 60 FPS run actually be uncapped? | Performance V2 verifies the intended cap from measured samples; sustained 90/120/144 cannot pass as a 60 FPS baseline. |
| 15 | Can thermal throttling contaminate a benchmark? | Serious/critical thermal pressure still blocks a clean comparison. |
| 16 | Can Low Power Mode contaminate it? | Yes; it remains a hard comparison blocker. Screen recording stays a warning because its impact is workload-dependent. |
| 17 | Can stale JSON files from different runs be mixed together? | Added `huniecam_evidence_contract.py` with schema + executable-hash + stage consistency checks. |
| 18 | Will the evidence contract understand current Guard V2? | Yes; V1 remains readable and V2 is explicitly supported. |
| 19 | Can physical-iPad observations use a fixed template instead of vague prose? | Added `huniecam_device_evidence.py`. Unknown fields remain `null`. |
| 20 | Is pointer acceptance explicit? | Template names nine positions: four corners, four edge-midpoints and center. All nine must pass. |
| 21 | Are three cold launches truly three trials? | Template records three individual success/failure/null trials. |
| 22 | Are suspend/resume checks truly two trials? | Template records two individual cycles. |
| 23 | Can acceptance pass with mixed/stale evidence? | Acceptance V4 adds a required `evidence_contract_valid` machine gate. |
| 24 | Can a manual 'performance feels fine' override dirty measurements? | No. Acceptance V4 also requires clean automated performance/cap evidence. |
| 25 | Can a guard-rejected profile reach the acceptance lane? | Next-run V2 returns `BLOCK_INVALID_PROFILE`. |
| 26 | Can mixed/stale evidence reach the acceptance lane? | Next-run V2 returns `BLOCK_INVALID_EVIDENCE`. |
| 27 | What if game code works but FPS/cap/thermal evidence is unproven? | Next-run V2 requests a clean **measurement baseline** with no new compatibility switch. |
| 28 | Can the historical 'best stage' ledger mix game builds? | Attempt Ledger V2 locks to the first provenance-ready owned-build fingerprint; another build is rejected. |
| 29 | Can Fit vs Stretch be treated as the same run? | No. Display mode is now part of the attempt/profile fingerprint and cross-checked against the run record. |
| 30 | Can title configuration changes be separated from save loss? | Added `huniecam_registry_snapshot.py`; it hashes only the HunieCam registry section/values and exposes names, not raw values. |
| 31 | Can the first important runtime failure be packaged quickly? | Added `huniecam_failure_capsule.py`: priority-ranked excerpt + full-log hash + privacy redaction while preserving instructions/addresses/status codes. |
| 32 | Can one command produce the strengthened evidence set? | Pipeline V3 now emits preflight, guard, session, issue matches, performance/cap status, failure capsule, run record, contract, next-run decision, manifest and optional registry/storage reports. |
| 33 | Does targeted CI cover the Cycle 5 evidence chain? | The old 'cycle 3 guardrails' workflow UI name is now `HunieCam evidence guardrails` and covers the critical Cycle 5 tools/tests on Python 3.11/3.12/3.13. |
| 34 | Can this cycle be frozen without claiming device success? | Final step is the full CI + targeted guardrail matrix, PR update, and keeping PR #4 draft. Physical gameplay acceptance remains mandatory. |

## The first real device run now produces a sealed evidence set

The pipeline's intended result folder contains, at minimum:

- `huniecam-preflight.json` — exact owned-build identity/hashes and title route;
- `huniecam-guard.json` — proves the launch did not contain a confounded/known-bad experiment;
- `huniecam-session.json` — deepest proven runtime stage and classified failures;
- `huniecam-issues.json` — relevant upstream Madeira failure families;
- `huniecam-performance.json` — FPS/frame-time/cap/device-state evidence;
- `huniecam-failure-capsule.json` — compact redacted first-failure evidence;
- `huniecam-run-record.json` — build + profile + session provenance seal;
- `huniecam-evidence-contract.json` — cross-file consistency result;
- `huniecam-next-run.json` — the one next evidence-backed action;
- `huniecam-evidence-manifest.json` — hashes of evidence artifacts;
- optional `huniecam-registry-snapshot.json` — title configuration fingerprints only;
- optional `huniecam-storage.json` — large dump/log warning report.

The original private logs remain the source of truth. Redacted/capsule output is a convenience for review or upstream discussion, not a replacement for the original evidence.

## Save protocol remains intentionally conservative

Do not assume a particular autosave trigger for acceptance.

1. Use a disposable/test save.
2. Record visible in-game state/progress.
3. Snapshot the LocalLow save tree as **BEFORE**.
4. Make clear visible progress.
5. Use an explicit normal save/normal exit path when available; do not force-kill the game as the save trigger.
6. Snapshot as **AFTER**.
7. Fully close the game and Madeira session.
8. Start the same provenance-locked baseline profile again.
9. Snapshot as **RELAUNCH**.
10. Machine verification requires BEFORE→AFTER to change and AFTER==RELAUNCH.
11. Separately verify inside the game that the exact visible progress returned.

Registry configuration fingerprints are intentionally excluded from this save gate.

## Acceptance V4 requirements

Every required gate must be PASS. Unknown never means pass.

Machine / structured evidence includes:

- owned executable identity/hash;
- valid cross-file evidence contract;
- Windows launch + managed-game-code stage;
- real save write + relaunch persistence;
- clean measured performance baseline with intended cap proven active;
- structured nine-point pointer grid;
- three cold-launch trials;
- two suspend/resume trials;
- >=30 minutes stable representative play.

Manual observations still matter for things software cannot infer safely:

- real management gameplay is actually playable;
- rendering is visually correct;
- audio is correct;
- relaunched save visibly restores the same progress;
- performance/responsiveness feels acceptable while measurements remain clean;
- the documented final profile reproduces from a clean Madeira start.

## What is still unproven

The workbench is stronger; the game is still not proven playable on the physical iPad.

The most valuable missing evidence is now a real clean device run using:

`HunieCamStudio.exe` → direct launch → program folder → 1280×720 → Fit → 60 FPS → no args → empty per-game config → no renderer override.

The next action after that run should come from the pipeline, not from accumulating guesses.
