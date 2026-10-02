# House Party port — canonical state

Updated: 2026-10-02

This file tracks the House Party-specific state on top of Madeira. It deliberately
separates build/install/debug/capture evidence from actual game-runtime evidence.

## Source and provenance

- Original owned game files are inputs only. Do not modify, rename, delete, or commit them.
- Run \`tools/house-party/fingerprint.py\` against a derived/extracted working copy and keep
  its JSON output outside the source directory.
- Do not commit game binaries, assets, saves, Microsoft redistributables, or other proprietary inputs.
- Historical branch \`joey-house-party\` is preserved for provenance.
- Active integration branch: \`joey-house-party-current\`, created from Madeira v0.1.1-era current main.

## Reconciled architecture

Historical owned-build inspection says House Party is a Windows x86-64 Unity IL2CPP
build using the Direct3D 11 path. That is the working hypothesis, not a substitute
for current evidence. The new fingerprint must be run against the current owned
build to record the exact Unity version, PE imports, plugins, media inventory,
important SHA-256 hashes and any version evidence that is actually present.

Do not assume Mono. Do not spend Cpp2IL/IL2CPP reconstruction effort until the
manifest reconfirms IL2CPP and the translated runtime lanes have been exhausted.

## Runtime lanes

### Mac translated Windows execution

Target classification: Windows x86-64 executable running through a compatibility/
translation stack. This is **not** a native Apple build.

Reconciled historical verification: CrossOver 26.3 was present and launcher/bottle
routing was repaired, but the attempt stopped at a sandbox Unix-socket permission
blocker before a verified House Party boot. No prior Mac report proves main menu or
gameplay. This cycle has not produced a fresh runtime result either.

Next measurement is a clean, repeatable DX11 matrix on the Mac, preserving one
known-good prefix per backend. DXMT and D3DMetal should be compared rather than
ranked by assumption.

### iPad / Madeira

Target classification: Windows x86-64 game code dynamically translated by FEX,
with ARM64EC Wine and DXMT inside an iOS app. This is local execution, but it is
**not** a true native House Party iPad build.

Current upstream base now includes the October 2 launch/address-space and image
mapping fixes. Historical work reached build/install/JIT/debugger plumbing and
separately hit repeated CoreDevice screenshot transport failures; none of that
proved House Party launch, rendering, menu, gameplay or save/load on the physical
M4 iPad. The highest House Party runtime milestone therefore remains below
"launches" until a current device run proves otherwise.

Physical-device work is intentionally queued while the iPad is in active use.
That is an execution constraint, not evidence of a runtime failure.

### True native reconstruction

No true ARM64 House Party build has been produced. Keep this lane evidence-driven.
The fingerprint and asset inventory come first; translated first-playable remains
the shorter path unless new reconstruction evidence changes that.

## Current critical path

1. Run the owned-build fingerprint and freeze the compatibility manifest.
2. Build current Madeira in the configuration known to run guest code (Debug, not
   the historical Release workflow).
3. Build/package the ARM64EC \`winegstreamer.dll\` path, but leave 64-bit media opt-in.
4. When the iPad is available, retest process launch on the current 63 GB address-map
   code before writing any new memory/JIT patch.
5. Only after launch/render evidence: enable \`MADEIRA_WG_64BIT=1\` for the House Party
   test session and validate video/audio separately.
6. Validate input, sustained gameplay, save/load, then performance/touch polish.

## Validation vocabulary

Use only the highest stage actually observed:

\`source inspected -> builds -> installs -> launches -> renders -> reaches menu ->
starts gameplay -> input works -> sustained gameplay -> save/load verified ->
performance measured -> regression tested\`.

A debugger attach, screenshot, successful compile, or successful install is not a
gameplay milestone.

## House Party-specific automation added this cycle

- \`tools/house-party/fingerprint.py\`: read-only machine-readable compatibility manifest.
- \`tests/host/check-house-party-fingerprint.py\`: synthetic regression test for the manifest tool.
- \`build/wine-pe/build-winegstreamer.sh\`: builds/packages the x64 media PE bridge.
- \`tests/host/check-house-party-media.py\`: source-level guard for that packaging path.
- \`tools/house-party/check-gptk4.sh\`: read-only GPTK 4 / Xcode / Metal CLI / Codex-skill probe.
- \`docs/house-party/ACCELERATION_REGISTER.json\`: structured acceleration decisions and results.

## Explicitly discarded for now

- Blindly rebasing the old House Party branch: too stale and needlessly conflict-heavy.
- Carrying forward its Release iOS workflow: current upstream build notes say the
  playable guest configuration is Debug and Release has crashed guest execution.
- Repeating the same CoreDevice screenshot transport loop without a new hypothesis.
- Calling Madeira execution "native House Party on iPad."


## Status-report reconciliation

Older percentage and calendar estimates described pipeline readiness, not verified
gameplay. They are superseded by the milestone vocabulary above. Do not derive a
new completion percentage from staged files, CI jobs, JIT attachment, install
success or capture plumbing.
