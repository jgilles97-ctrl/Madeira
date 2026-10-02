# Porting memory — House Party

Last reconciled: 2026-10-02

## Goal

Get Joey's legitimately owned House Party Windows build as complete and reliable
as practical on Apple-silicon Mac and M4 iPad. Preserve an explicit distinction
between a true Apple-native ARM64 build and local Windows execution through
Wine/FEX/DXMT.

## Ground rules

- Owned game sources are read-only inputs and never belong in this repository.
- Do not repeat an equivalent failure without a new hypothesis/instrumentation.
- Runtime, install, JIT/debugger, capture, and validation are separate statuses.
- Preserve a translated first-playable result even while native feasibility work continues.
- Do not interrupt the physical iPad while it is in use; continue host/static/cloud lanes.

## Current facts to reload first

- Fork main was fast-forwarded on 2026-10-02 to Madeira v0.1.1-era upstream
  commit \`b0a6692b76be512aabf9555833a74d0b8d07b3ac\`.
- Historical House Party branch remains preserved; it is intentionally not the active base.
- Active branch is \`joey-house-party-current\`.
- Current upstream includes a 63 GB session address-map launch path and recent
  ntdll image-mapping fixes. Retest these before adding another memory/JIT patch.
- Current upstream touch/controller/hardware keyboard+mouse infrastructure should
  be reused rather than recreated.
- 64-bit winegstreamer remains opt-in. Build/package its ARM64EC PE half with
  \`build/wine-pe/build-winegstreamer.sh\`, then enable
  \`env.MADEIRA_WG_64BIT = 1\` only for a controlled House Party media test.
- Current build notes say Debug is the guest-running app configuration; do not
  resurrect the historical Release workflow without fresh evidence.

## Evidence still required

- Fresh compatibility manifest from the owned current House Party build.
- Exact House Party build/version and Unity version.
- Fresh Mac translation result: run `tools/house-party/mac-crossover-smoke.sh`
  on Joey's Mac, then validate launch/menu/gameplay/save/load and DXMT vs D3DMetal.
- Current physical-M4 iPad result on the October 2 Madeira base.
- House Party-specific 64-bit video/audio result.
- Sustained gameplay, save/load, performance and regression results.

## Canonical project files

- \`docs/house-party/STATE.md\`
- \`docs/house-party/ACCELERATION_REGISTER.json\`
- \`tools/house-party/fingerprint.py\`
- \`tools/house-party/check-gptk4.sh\`

Update these after a meaningful result instead of forcing future sessions to
mine raw logs again.
