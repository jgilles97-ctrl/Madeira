# iPad / M-series log triage

This fork carries a small, offline helper for turning a Madeira diagnostic log into a compact list of high-signal compatibility markers. It is meant for repeatable iPad/M-series testing and does not diagnose root cause by itself.

## Run it

```sh
python3 tools/madeira_log_triage.py /path/to/madeira-log.txt
python3 tools/madeira_log_triage.py /path/to/madeira-log.txt --json madeira-triage.json
```

The helper is dependency-free, read-only, makes no network calls, and redacts common local container/user paths and secret-like values from the sample lines it prints.

## Signals currently recognized

- JIT/debugger missing when executable memory is requested;
- JIT pool/address-space failure;
- `[store-undecoded]`, especially important for Unity/Mono and other runtimes that write/patch JIT-backed memory;
- 32-bit WoW64 guest-window refusal on a small address map;
- the older DXMT Metal-language-version 4.1 incompatibility family;
- missing/imported Windows DLL failures;
- Windows `0xC0000005` access violations;
- Windows `0xC0000017` out-of-memory exits;
- historical M4 TEB/TSD-slot failure patterns;
- legacy/external StikDebug unexpected-PID responses;
- Steam refusal 29 / `invalid platform`;
- positive markers for JIT attachment, a clean x64 probe, and target-process launch.

A match is a pointer to inspect the surrounding lines, not proof of the cause. Prefer the earliest high-signal finding over a generic crash code that appears later.

## Current JIT note

Do not treat the old external-StikDebug flow as the only valid route. Current Madeira also has a built-in StikJIT helper, and on iOS 27 it can pair in-app. Use `docs/JIT.md` for the current setup. A title compatibility test is invalid if JIT/Memory+ was not ready before the launch.

## Recommended iPad report bundle

Record:

1. Madeira build SHA/version.
2. iPad model and iPadOS version.
3. JIT method and whether Settings shows JIT + Memory+ ready before launch.
4. Game/test executable and architecture (x86 or x86-64).
5. Original `madeira-log.txt`.
6. Triage text/JSON output.
7. Exact reproduction steps.
8. Per-game Madeira config, even when empty/default.
9. Whether the result repeats after a fresh Madeira launch.
10. The deepest proven stage: process start, splash, menu, gameplay, save/relaunch, sustained run.

Always preserve the original diagnostic log in addition to this summary. Do not attach pairing files, tokens, passwords, proprietary game binaries, or save data that contains sensitive information.

## HunieCam Studio

For the title-specific plan, preflight tool, 21-pass audit and acceptance gates, see `docs/HUNIECAM_STUDIO_IPAD.md` and `tools/huniecam_probe.py`.
