# HunieCam Studio iPad/Madeira — Cycle 4 (34 distinct passes)

Status: research + implementation cycle complete. This is another 34-pass hardening cycle after Cycle 3. It still does **not** claim the game has been proven playable on the iPad; only a real device run can do that.

## What changed in plain English

Cycle 4 focused on a different problem than the earlier cycles: **how to stop a plausible-looking log or a lucky run from tricking us into keeping the wrong setting.**

The biggest corrections are:

- clean Direct3D 11 selection is no longer treated as a failure by itself;
- a generic `store-undecoded` line no longer automatically earns a Unity-Mono memory tweak;
- A/B runs are compared automatically and are rejected as scientifically ambiguous when more than one variable changed;
- performance comparisons are rejected when there are no measurements, serious thermal throttling, or Low Power Mode;
- acceptance now checks counted evidence for the 30-minute run, three cold launches, two suspend/resume cycles and a nine-point pointer sweep.

## Current clean baseline

Use this until real evidence justifies exactly one change:

- program: `HunieCamStudio.exe`
- launch: direct library entry first
- working folder: program/game folder
- resolution: `1280x720`
- display: Fit
- frame limit: 60 FPS
- launch arguments: none
- per-game compatibility config: empty
- renderer: let the owned Unity build choose normally
- controller: not required
- pointer/touch/mouse: primary input route
- JIT + Memory+: proven ready before the run counts

A renderer override is now diagnostic only. Seeing D3D11 in a clean Unity log is not enough reason to force D3D9.

## 34-pass audit

| Pass | Question / implementation | Result |
| ---: | --- | --- |
| 1 | Is PR #4 still healthy before more changes? | Rechecked the draft PR and existing CI; branch remained mergeable and the previous matrix was green. |
| 2 | Did upstream Madeira move beyond our Oct. 6 baseline? | Rechecked upstream commits on Oct. 9; no newer commit was found, so another rebase would add churn without benefit. |
| 3 | Did HunieCam's Windows game depot move? | SteamDB still reports Windows depot 426001 last updated July 18, 2020. Recent 2026 Steam changes are package/store metadata, not a new Windows game binary. |
| 4 | Does that remove all build uncertainty? | No. The owned EXE/hash remains authoritative, but we no longer need to assume a fresh Windows binary appeared this week. |
| 5 | What do Unity's own 5.3-era docs say about renderer choice? | The standalone player supports `-force-d3d9`, but the normal API depends on the build/player settings; D3D11 selection can be legitimate. |
| 6 | Was our previous D3D11 rule too aggressive? | Yes. Session triage used to recommend `-force-d3d9` merely because D3D11 appeared. That could change a working renderer for no reason. |
| 7 | How is clean D3D11 handled now? | It stays on the clean baseline and asks for deeper evidence. No renderer override is proposed simply from selection. |
| 8 | When is `-force-d3d9` now justified? | Only when D3D11 is accompanied by a graphics failure/crash, or graphics initialization fails before any API is proven. |
| 9 | What if D3D9 is proven and then graphics crashes? | That remains the correct trigger for the separate `d3d9 = native` one-variable A/B. |
| 10 | Can generic `[store-undecoded]` still trigger RWX-plain without Mono evidence? | No. A store label without Unity-Mono evidence is routed to an unclassified Madeira runtime blocker. |
| 11 | What if `[store-undecoded]` is `insn=0xd4200000`? | It stays in the issue #173 breakpoint/INT3 runtime lane and never becomes a Mono RWX experiment. |
| 12 | What if a real store occurs while HunieCam's bundled Mono is present? | Only then can `env.MADEIRA_WOW_RWX_PLAIN = 1` become a controlled A/B candidate. |
| 13 | Can `mono-suspend=hybrid` re-enter through old advice? | Config guard still rejects it because upstream issue #123 already showed the Unity-Mono abort pattern. |
| 14 | Can forced WX re-enter? | Config guard rejects the known-bad forced-WX route for this title. |
| 15 | Can modern IL2CPP `real-suspend=1` advice be copied blindly? | No. It remains a warned/non-transferable idea unless actual HunieCam evidence proves a matching problem. |
| 16 | How do we prove an experiment helped rather than merely changed something? | Added `tools/huniecam_run_compare.py` to compare before/after session evidence. |
| 17 | What does the run comparator measure? | Deepest proven stage, introduced failures, cleared failures and launch-profile differences. |
| 18 | What happens if two variables changed? | Verdict becomes `AMBIGUOUS_MULTI_CHANGE`, even when the newer run reaches farther. The result cannot justify keeping either tweak. |
| 19 | What qualifies a one-variable experiment to stay? | It must move the run deeper or clearly improve the classified failure set; otherwise the tool recommends rollback. |
| 20 | Can notes/timestamps create false experiment differences? | No. Run-comparison metadata such as notes/timestamps is ignored when counting compatibility variables. |
| 21 | Can performance be assessed without actual samples? | No. Added `tools/huniecam_performance.py`; missing FPS/frame-time evidence remains explicitly unproven. |
| 22 | Can thermal throttling poison an A/B comparison? | Yes. Serious/critical thermal state marks a performance comparison as unclean. |
| 23 | Can Low Power Mode poison it? | Yes. Any Low Power Mode sample makes the run unsuitable for a clean performance comparison. |
| 24 | Is screen recording visible in the evidence? | Yes. Device-load capture state is recorded and warned because recording can add overhead. |
| 25 | Can a very high FPS number be treated automatically as better? | No. The parser flags >125 FPS as a runaway/high-rate signal and tells us to verify game timing. |
| 26 | Was acceptance still too checkbox-like? | Yes. Several duration/repetition gates were booleans, which made accidental overclaiming easier. |
| 27 | How is 30-minute stability checked now? | Acceptance V3 accepts `stable_minutes` and requires a numeric value >=30. |
| 28 | How are cold launches checked now? | It accepts `cold_launches` and requires >=3 successful cold starts. |
| 29 | How is suspend/resume checked now? | It accepts `suspend_resume_cycles` and requires >=2 successful cycles. |
| 30 | How is pointer accuracy checked now? | It accepts a counted nine-point sweep: >=9 points tested and every tested point passed. |
| 31 | Does that break older evidence files? | No. Legacy booleans remain supported for backward compatibility, but new evidence should use counted fields. |
| 32 | Does current Madeira's iPad input design support this test strategy? | Yes. Madeira documents absolute pointer-to-Windows-cursor mapping on the game view when the program shows a cursor; full-surface testing is still required on the device. |
| 33 | Are the new comparator/performance/renderer rules under CI? | Added a Cycle 3/4 guardrail workflow and the main glob-based HunieCam workflow automatically compiles/discovers every HunieCam helper/test on Python 3.11/3.12/3.13. |
| 34 | What is the final cycle rule? | Run the full matrix after these changes, fix any failure, update PR #4, and keep it draft/unmerged until the actual iPad acceptance gates are evidenced. |

## New tool: run comparison

`tools/huniecam_run_compare.py` answers a simple question: **did the one thing we changed actually help?**

Example:

```sh
python3 tools/huniecam_run_compare.py \
  --before-session baseline-session.json \
  --after-session experiment-session.json \
  --before-profile baseline-profile.json \
  --after-profile experiment-profile.json \
  --json comparison.json
```

Useful verdicts include:

- `DEEPER` — newer run reached a deeper proven stage;
- `IMPROVED_FAILURE_SET` — same stage, but a previous classified blocker disappeared;
- `REGRESSION` / `REGRESSION_NEW_FAILURE` — worse;
- `NO_PROVEN_MOVEMENT` — nothing objectively improved;
- `AMBIGUOUS_MULTI_CHANGE` — more than one profile variable changed, so the experiment cannot prove cause.

A switch is not promoted merely because the user interface looked different.

## New tool: performance evidence

`tools/huniecam_performance.py` extracts:

- FPS samples;
- frame-time samples;
- median / low-percentile / high-percentile values;
- Madeira `[device-load]` thermal state;
- Low Power Mode;
- screen-capture state;
- a high/runaway-FPS warning.

Example:

```sh
python3 tools/huniecam_performance.py madeira-log.txt --json performance.json
```

It deliberately refuses to call a run clean for performance comparison when the iPad is under serious thermal pressure or Low Power Mode.

## Renderer decision tree — corrected

1. **No graphics failure:** do not force anything.
2. **Clean D3D11 selected:** continue clean; collect deeper evidence.
3. **D3D11 + graphics crash/failure:** one `-force-d3d9` A/B may be justified.
4. **Graphics init fails before any API is proven:** one `-force-d3d9` A/B may be justified.
5. **D3D9 proven + graphics-specific crash:** one `d3d9 = native` A/B may be justified.
6. Never combine renderer experiments in one diagnostic run.

Unity's documentation is the reason for this correction: renderer selection in this era depends on player/build settings. The public HunieCam compatibility data still makes D3D9 relevant, but a real clean log outranks assumptions.

## Acceptance V3 — counted evidence

Preferred manual evidence now looks like:

```json
{
  "jit_memory_ready": true,
  "real_gameplay": true,
  "rendering_correct": true,
  "pointer_points_tested": 9,
  "pointer_points_passed": 9,
  "audio_correct": true,
  "save_progress_visible_after_relaunch": true,
  "performance_acceptable": true,
  "stable_minutes": 30,
  "cold_launches": 3,
  "suspend_resume_cycles": 2,
  "repeatable_profile": true
}
```

The machine save-verification report is still separate. Visible restored progress is still required. A matching save directory alone does not prove the game loaded the save correctly.

## Important public/reference findings from this cycle

- SteamDB package/depot data: Windows depot `426001` last updated **July 18, 2020**; the package itself had newer 2026 metadata activity.
- Unity 5.3 manual: standalone players support `-force-d3d9`, but normal graphics API selection depends on player/build settings.
- Unity standalone logging: `output_log.txt` is normally written unless `-nolog` is used, so our baseline continues to avoid `-nolog`.
- Madeira hardware-input docs: iPad pointer position can map to the Windows program cursor in absolute mode when the game exposes a cursor; this supports a nine-point whole-surface acceptance sweep but does not replace the physical test.

## What remains physically unproven

The real blocker has not changed: **we still need an actual HunieCam run on the iPad**.

Completion requires evidence for all of these:

1. JIT + Memory+ ready.
2. Owned Windows build identified by hash and PE architecture.
3. Windows process launch.
4. Unity/managed game code reached.
5. Real gameplay.
6. Correct rendering.
7. Nine-point pointer sweep fully passes.
8. Correct audio.
9. Save write + exact relaunch persistence + visibly restored progress.
10. Measured acceptable performance/timing under a clean device state.
11. >=30 stable minutes.
12. >=3 successful cold launches.
13. >=2 successful suspend/resume cycles.
14. Final profile reproduces from a clean Madeira start.

Until the device evidence exists, the accurate state remains: **extensively prepared compatibility workbench, not a proven completed port.**
