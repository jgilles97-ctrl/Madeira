# HunieCam Studio → iPad/Madeira — Cycle 7

## Purpose

Cycle 7 is a 68-pass research, implementation, integration and verification cycle. The goal is not to accumulate compatibility switches. The goal is to make one physical-iPad run maximally informative, prevent false success, and close the remaining evidence gaps before any claim that HunieCam Studio is playable on iPad.

**Hard rule:** CI proves the tools, not the game. The port remains unproven until the physical iPad passes every current acceptance gate.

## Authoritative baseline

- Upstream Madeira `main` was rechecked directly through GitHub and is still `48f976429c189f8396e23d251d8a82f43c705922` (October 6, 2026). No phantom/newer upstream rebase is assumed.
- PR #4 remains draft and `main` remains untouched.
- Clean first run remains: direct `HunieCamStudio.exe`, game/program folder, 1280×720, Fit, intended 60 FPS, no launch arguments, empty per-game compatibility config, no forced renderer, JIT + Memory+ ready.
- The title ships its own Unity Mono runtime. Wine Mono is not a HunieCam game-runtime prerequisite.
- Renderer selection remains evidence-driven. A clean Direct3D 11 selection is not a failure by itself.
- Public PCGamingWiki input notes report that HunieCam relies heavily on dragging portraits and that touch/stylus release can fail on Windows. This is a risk to test, **not evidence that the same bug exists on iPad/Madeira**.

## Current evidence formats

Cycle 7 pins these current formats so producer/consumer drift becomes a CI failure:

- Preflight: `MADEIRA_HUNIECAM_PROBE_V4`
- Session: `MADEIRA_HUNIECAM_SESSION_V3`
- Config guard: `MADEIRA_HUNIECAM_CONFIG_GUARD_V2`
- Performance: `MADEIRA_HUNIECAM_PERFORMANCE_V2`
- Run record: `MADEIRA_HUNIECAM_RUN_RECORD_V1`
- Run context: `MADEIRA_HUNIECAM_RUN_CONTEXT_V2`
- PE imports: `MADEIRA_HUNIECAM_PE_IMPORTS_V1`
- Native modules: `MADEIRA_HUNIECAM_NATIVE_MODULES_V1`
- Device evidence: `MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3`
- Save snapshot/compare/verify: V2
- Repeatability: `MADEIRA_HUNIECAM_REPEATABILITY_V3`
- Evidence contract: `MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4`
- Acceptance: `MADEIRA_HUNIECAM_ACCEPTANCE_V9`
- Evidence manifest: `MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V6`
- Pipeline: `MADEIRA_HUNIECAM_PIPELINE_V8`

## The 68 passes

1. Rechecked the authoritative upstream `main` branch rather than trusting repository-summary noise.
2. Confirmed upstream still ends at `48f976429c189f8396e23d251d8a82f43c705922`.
3. Rechecked PR #4 state: open, draft, unmerged and mergeable.
4. Re-anchored repeatedly on the live feature-branch head to avoid overwriting concurrent/newer work.
5. Audited the broad HunieCam CI matrix rather than relying on commit status alone.
6. Audited the targeted evidence-guardrail matrix separately.
7. Used failing CI as defect discovery instead of calling committed code complete.
8. Traced stale evidence-contract test assumptions to current Contract V4.
9. Traced stale pipeline assertions to current Pipeline V8.
10. Verified the run-context seal includes the exact launch/session evidence instead of only the executable.
11. Kept the exact owned-build fingerprint requirement.
12. Kept the separate launch-profile fingerprint requirement.
13. Kept display mode in profile identity so Fit and Stretch are not comparable input baselines.
14. Kept the exact guard JSON sealed into Run Context V2.
15. Kept the exact performance JSON sealed into Run Context V2.
16. Kept the exact PE import audit sealed into Run Context V2.
17. Kept the exact native-module audit sealed into Run Context V2.
18. Kept the native-module-set fingerprint exposed for repeatability.
19. Confirmed replacing a bundled native module changes the sealed run identity.
20. Kept PE dependency decisions evidence-based rather than installing generic redistributables.
21. Kept direct-EXE missing imports separate from plugin/native-module requesters.
22. Kept unresolved dynamic DLL dependencies explicitly unproven.
23. Kept no-missing-DLL evidence as a command to change nothing.
24. Kept direct game launch and Dock/Steam integration as separate compatibility lanes.
25. Kept Wine Mono out of the baseline because HunieCam carries its own Unity Mono.
26. Kept renderer-neutral baseline: no forced D3D9/D3D11.
27. Kept `-force-d3d9` only for a graphics failure where the evidence justifies that one A/B.
28. Kept `d3d9 = native` only after D3D9 is proven and the remaining problem is graphics-specific.
29. Kept `MADEIRA_WOW_RWX_PLAIN=1` conditional on real Unity-Mono protected-memory/store evidence.
30. Kept `insn=0xd4200000` breakpoint-family evidence separate from generic store faults.
31. Kept one-variable-at-a-time config guarding.
32. Kept A/B comparison locked to the identical owned build.
33. Kept performance comparison blocked by dirty/uncomparable measurements.
34. Kept the intended 60 FPS cap as something measured, not assumed from UI settings.
35. Kept Low Power Mode as a performance-comparison blocker.
36. Kept serious/critical thermal pressure as a performance-comparison blocker.
37. Kept screen capture visible as possible measurement overhead rather than hiding it.
38. Kept registry/config evidence separate from LocalLow save evidence.
39. Kept save snapshots privacy-minimal: relative file information/hashes, not save contents.
40. Kept Save Verify V2 locked to one exact hashed source directory.
41. Kept the expected `HunieCam Studio` save-folder identity as a machine gate.
42. Kept BEFORE → AFTER → RELAUNCH as three distinct save states.
43. Kept visible restored in-game progress mandatory even when file hashes persist.
44. Kept Repeatability V3 at three distinct sealed run IDs.
45. Kept all repeatability runs on the identical owned build.
46. Kept all repeatability runs on the identical launch profile.
47. Kept all repeatability runs on the identical native-module set.
48. Kept scene/game-stage minimum for repeatability.
49. Kept triaged fatal errors incompatible with a repeatability pass.
50. Added/retained a final acceptance-bundle orchestrator so final evidence is assembled consistently.
51. Revalidated the final provenance contract after the acceptance report is generated.
52. Kept the final manifest privacy-minimal instead of embedding logs, saves, binaries or credentials.
53. Extended explicit schema synchronization auditing through the current Cycle 7 formats.
54. Made silent producer/consumer schema drift a CI failure.
55. Added Device Evidence V3 as the only current final device-evidence format.
56. Added three title-specific real-gameplay drag/release trials.
57. Required each drag trial to prove press registration.
58. Required each drag trial to prove movement registration.
59. Required each drag trial to prove release registration.
60. Required each drag trial to prove the resulting in-game response.
61. Verified an unknown release/result remains UNKNOWN, never PASS.
62. Verified a false release/result fails even when pointer positioning itself passes.
63. Blocked legacy Device Evidence V2 from finishing Cycle 7 because it cannot prove the drag/release risk.
64. Kept the nine-point pointer grid in addition to, not instead of, drag/release testing.
65. Kept real gameplay, rendering, audio, save restoration, measured performance, >=30 stable minutes, 3 observed cold starts, 3 sealed cold starts, 2 suspend/resume cycles and repeatable final profile as hard acceptance gates.
66. Repaired all stale Acceptance/Bundle/Device/Manifest/Schema/Pipeline regression fixtures without weakening the new gate.
67. Ran the final broad and targeted matrices across Python 3.11, 3.12 and 3.13; all jobs passed.
68. Reasserted the completion rule: green CI and synthetic happy paths do **not** mean HunieCam is playable on iPad; physical-device evidence is still required.

## Why the drag/release gate matters

A nine-point pointer test can prove that taps/cursor positions reach the right parts of the screen, but it cannot prove HunieCam's core drag-heavy interaction works. Public Windows-touchscreen notes specifically report a failure mode where the drag moves but the release does not register. Cycle 7 therefore tests four separate facts for each real gameplay drag:

1. press registered;
2. movement registered;
3. release registered;
4. the game actually reacted to the completed drag.

Three successful real gameplay trials are required. A failure or unknown result blocks acceptance. The public Windows report is only a reason to test this; the iPad/Madeira result must come from the actual device.

## Final CI for this cycle

Final verified head before this document: `0f21c8483fa3b270bd98ab97812fef5c5cd92bbf`.

- `HunieCam iPad compatibility checks` run **37900821124**: Python 3.11, 3.12 and 3.13 all passed compilation, focused diagnostics, the complete HunieCam regression suite and generic Madeira log-triage regressions.
- `HunieCam evidence guardrails` run **37900821167**: Python 3.11, 3.12 and 3.13 all passed schema synchronization, provenance/dependency, device/final-acceptance and pipeline/runtime-triage guardrails.

CI caught real integration drift during the cycle (old Contract/Pipeline/Device/Manifest/Acceptance expectations) and the fixes updated the tests/consumers to the stricter formats. The hard gates were not relaxed to obtain green results.

## Exact clean first physical-iPad run

1. Use the current feature-branch Madeira build.
2. Confirm JIT + Memory+ before launching.
3. Launch `HunieCamStudio.exe` directly first.
4. Working folder: the game/program folder.
5. Resolution: 1280×720.
6. Display: Fit.
7. Intended cap: 60 FPS; measure it so the cap is proven active.
8. No launch arguments.
9. Empty per-game compatibility config.
10. No forced renderer.
11. Collect `madeira-log.txt`.
12. Collect Unity `HunieCamStudio_Data/output_log.txt` if produced.
13. Run Pipeline V8 and keep its sealed run-linked device form for that exact launch.
14. Do not reuse the form for another run ID.

If the runtime reaches real gameplay, the physical test must include the nine pointer locations **and three real gameplay drag/release trials** before input can pass.

## Conditional next-step ladder

- JIT missing → repair the JIT prerequisite; no title tuning.
- WoW64/address-space mapping failure → address that runtime problem; do not pile on game switches.
- Missing DLL → use the PE/native-module dependency evidence to identify the exact requester/prerequisite.
- Clean D3D11 → leave it alone.
- D3D11 + graphics-init/crash evidence → one `-force-d3d9` A/B.
- Unity Mono + real protected-memory store problem (not breakpoint `0xd4200000`) → one `MADEIRA_WOW_RWX_PLAIN=1` A/B.
- Proven D3D9 + remaining graphics-specific failure → one `d3d9 = native` A/B.
- Steam/Dock-only failure → keep it separate from direct game compatibility.
- Scene/game code works but performance evidence is dirty → repeat the unchanged profile for clean measurement.
- Pointer works but drag release fails → input usability blocker; do not accept the port.
- Full current evidence passes → run the final acceptance bundle; only an actual `accepted=true` backed by device evidence closes the project.

## Current project status

**Proven:** the research/diagnostic/evidence machinery is internally consistent and CI-green across all three Python versions.

**Not proven:** HunieCam Studio running as a fully usable local Madeira game on the physical iPad Pro M4. No documentation or CI result may replace that device proof.
