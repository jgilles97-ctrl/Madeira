# Chicken Chase on iPad — Madeira-first port lane

This lane targets the 2007 Positive Solutions / Big Fish / Reflexive Windows game **Chicken Chase**.

The immediate goal is not to rewrite the game. It is to use the existing Madeira iPad runtime to get the original recovered game tree into real gameplay on an M-series iPad as quickly as possible, then use evidence from that run to decide whether the long-term product should remain compatibility-based or become a native recreation.

## Why Madeira is now the primary iPad path

The current Madeira architecture already solves most of the hard generic porting problems:

- 32-bit Windows programs run through Wine WoW64.
- x86 guest code is translated by FEX to ARM64.
- the Wine side of WoW64 remains native ARM64.
- an i386 Windows module farm is built by build/wine-i386/build.sh.
- i386 D3D9 has an explicit DXMT to Metal route.
- GDI window surfaces are connected to the iOS compositor.
- keyboard, mouse and trackpad transport already exist.
- direct touch pointer mode already maps a finger position into guest coordinates and posts Windows mouse events.
- rendering and touch mapping use the same game rectangle, so aspect-fit letterboxing does not skew input.
- the game library accepts x86 PE executables copied into wine/drive_c.

That combination is unusually well matched to Chicken Chase because the original game is a small, mouse-driven 2007 casual title.

## Known Chicken Chase facts

Canonical recovered-game target:

- expected gameplay executable: chicken_chase.exe
- historical display reference: 800x600, 4:3
- input model: primarily left-click interaction
- Big Fish ID: F1402T1L1
- Reflexive AID: 781

The tiny chicken-chase-1.1.0.22.exe file is a bootstrap artifact, not the full game payload.

The CenlumaCore Chicken Chase branch contains the payload recovery, extraction, static analysis and Mac smoke-test pipeline. Do not duplicate that work here.

## First-run architecture

Primary route:

Chicken Chase PE32 x86
-> Wine WoW64
-> FEX x86 to ARM64 translation
-> Madeira iOS Windows bridge
-> renderer-specific path
-> Metal/iOS compositor
-> direct touch mapped to Win32 pointer events

### Renderer decision tree

Run tools/chicken_chase_preflight.py against the recovered game EXE before device work.

#### GDI

Risk: LOWEST

Madeira's iOS win32u driver explicitly composites GDI window surfaces. If Chicken Chase is fundamentally a GDI game, this is the most favorable result.

Action:
- use the normal i386 Wine module farm
- launch directly, not through a desktop session
- do not add a graphics translation layer unless runtime evidence demands one

#### Direct3D 9

Risk: LOW to MEDIUM

Madeira has an explicit i386 D3D9 path through DXMT.

Action:
- first run with Madeira's default D3D9 frontend
- do not turn on the native D3D9 frontend before a baseline exists
- if performance or correctness is poor, compare d3d9 = native against the same acceptance test

#### DirectDraw

Risk: MEDIUM to HIGH until device proof

The i386 Wine farm build does not exclude ddraw.dll, so the module is expected to be available after a complete i386 build. However, this is not proof that Chicken Chase's exact DirectDraw presentation path works correctly on iPad.

Action:
- test the existing Wine i386 DirectDraw path first
- capture exact missing API/rendering failure before changing architecture
- avoid writing a replacement renderer preemptively
- if presentation is the only blocker, investigate the smallest bridge from Wine's DirectDraw/wined3d behavior to an already-supported Madeira presentation path

DirectDraw is the most important unknown to collapse early.

#### Direct3D 8 / OpenGL / unknown

Treat as evidence-driven compatibility work. Do not assume a renderer replacement is required until the recovered EXE and device logs prove it.

## First Chicken Chase Madeira profile

Use the smallest number of overrides possible.

- Program: chicken_chase.exe
- Launch mode: direct game launch
- Windows screen: 800x600
- Aspect & scaling: Fit
- Pointer mode: Touch
- Relative pointer: off
- Desktop mode: off
- Pointer auto-lock: off
- FPS: 60
- CPU count: Automatic
- WoW64 switches: defaults
- sync engine: Madeira default
- D3D9 frontend: default, unless the executable actually uses D3D9 and evidence supports a comparison
- no speculative Winetricks-style dependency installation

The direct touch path already does the important mapping:

finger position
-> GameSurfaceLayout guest coordinate
-> Windows left-button down/up

For Chicken Chase this should feel like a native tap interface rather than a virtual trackpad.

## i386 farm gate

The repository intentionally does not commit the generated i386 Windows module farm. A clean source checkout can therefore contain only app/Madeira/i386-windows/.gitkeep.

Before calling an iPad build Chicken-Chase-ready, build the farm:

    build/wine-i386/build.sh

Then verify at least the modules reported by tools/chicken_chase_preflight.py.

Do not infer runtime readiness from source code existing in the repository.

## M4 / JIT gate

Madeira requires JIT for its fast x86 translation route.

Before every acceptance run:

1. use a current Madeira build
2. enable JIT through Madeira's supported JIT flow
3. confirm the app reports JIT ready
4. confirm Memory+ state when the current build exposes it
5. only then launch Chicken Chase

A launch failure without active JIT is not a Chicken Chase compatibility result.

Current Madeira M-series reports prove that the runtime and JIT can operate on recent M-series iPads. Separate reports also show that some managed runtimes or self-modifying workloads can hit executable-memory edge cases. Therefore the Chicken Chase preflight explicitly checks for:

- .NET/managed PE metadata
- writable+executable PE sections
- high-entropy executable sections that can indicate packing

For this project, a small native PE32 game with ordinary sections is a substantially better target than a managed or heavily self-modifying title.

## Acceptance gates

### IPAD-A — payload

A legitimate recovered game tree exists and contains the actual chicken_chase.exe.

Evidence:
- SHA-256
- complete file manifest
- source/provenance record

### IPAD-B — PE characterization

tools/chicken_chase_preflight.py reports:

- PE32 i386 confirmed
- renderer classified or explicitly unknown
- audio/input imports recorded
- managed status recorded
- section/JIT risk recorded

### IPAD-C — runtime farm

The required i386 Madeira modules are physically present in the built app tree.

No source-only claim counts.

### IPAD-D — process start

On iPad with JIT active:

- Chicken Chase process starts
- no immediate PE loader failure
- no missing critical module
- no immediate FEX/WoW64 exception

A surviving process alone does not pass graphics.

### IPAD-E — visible menu

The actual Chicken Chase title/menu is visible and updating.

Acceptance:
- correct orientation
- no severe cropping
- correct 4:3 behavior
- no black/blank-only frame
- touch coordinate mapping lines up with the visible menu

### IPAD-F — real level

A real gameplay level loads.

Acceptance:
- chickens/world render
- animation advances
- audio is audible when expected
- tap lands on the intended in-game object
- no trackpad-style cursor manipulation is required for normal play

### IPAD-G — interaction

Validate every core interaction observed in the original game:

- tap chickens/objects
- collect items
- feed/care actions
- raven/pest interaction
- menus
- any hold/drag behavior actually used by the game

If an operation does not exist in the original game, do not invent a touch gesture for it.

### IPAD-H — progression

Complete a level and transition to the next state.

### IPAD-I — persistence

Quit the game normally, relaunch, and confirm progression/settings survive.

Record exact save/config paths in the Madeira prefix.

### IPAD-J — sustained run

Play multiple levels without:

- growing memory failure
- stuck touch/button state
- recurring renderer corruption
- audio loss
- save corruption
- JIT/FEX crash

### IPAD-K — polished compatibility build

Only after the earlier gates pass:

- hide unnecessary runtime chrome
- use a Chicken Chase-specific library profile
- preserve 4:3 by default
- direct touch enabled by default
- add optional mouse/trackpad support
- make launch/resume predictable
- capture useful diagnostics behind developer controls rather than in the normal experience

## Failure decision tree

When a device run fails, classify before changing anything.

### Loader/module error

Action:
- identify the exact missing DLL/import
- verify whether build/wine-i386/build.sh produces it
- build the smallest missing Madeira/Wine component
- retry

### 32-bit WoW64/FEX exception

Action:
- run Madeira log triage
- capture the first exception, not just the final cascade
- compare against current upstream Madeira/Wine/FEX fixes
- sync current upstream before writing a Chicken Chase-specific workaround

### Black screen but process alive

Action order:
1. identify renderer from PE/runtime logs
2. confirm a real window/surface exists
3. confirm presents/flushes are occurring
4. inspect GDI/DirectDraw/D3D9 path-specific logs
5. only then patch presentation

Do not treat "black screen" as proof the CPU/runtime path failed.

### Input offset

Action:
- verify 800x600 guest mode
- verify display mode = Fit/Aspect
- inspect GameSurfaceLayout output
- do not add coordinate fudge factors before proving the game/render rectangle differs from the touch rectangle

Madeira deliberately maps display and touch through the same rectangle, so offset is more likely to indicate a mode/window mismatch than a generic touch bug.

### Audio missing

Action:
- identify imported audio API
- capture Wine/Madeira audio initialization result
- validate the smallest missing API bridge/dependency
- do not install unrelated runtime packages

### Packed/self-modifying-code failure

Action:
- compare Mac Wine behavior and iPad FEX logs
- determine whether the behavior belongs to a distributor wrapper rather than the actual game core
- prefer the cleanest legitimate distribution/game executable
- do not bypass licensing

## Native/no-JIT endgame lane

Madeira is the fastest path to a playable original build, but it requires a sideloaded/JIT-capable environment.

A native iPad recreation remains a secondary long-term option if one of these becomes true:

- DirectDraw compatibility is disproportionately difficult
- JIT requirements make the desired final distribution unacceptable
- the game data/assets/levels prove simple enough to reimplement cleanly
- preservation goals favor a small purpose-built runtime

Do not begin a full rewrite merely because it sounds cleaner.

First recover and characterize the real game. A working Madeira run gives us an executable behavioral oracle for rendering, timing, input, audio and saves, dramatically reducing native-recreation risk.

## Parallel work that is worth doing now

While CenlumaCore recovers the payload:

1. keep the Madeira fork synchronized with current upstream runtime fixes
2. keep the i386 farm build reproducible
3. run Madeira's existing host checks
4. preserve M4/iPad diagnostic tooling
5. prepare a Chicken Chase-specific library profile once the imports are known
6. avoid game-specific runtime patches until there is a reproducible device failure

The fastest route is to reuse the platform work Madeira already solved and spend project-specific effort only on compatibility facts unique to Chicken Chase.
