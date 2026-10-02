# iPad / M-series log triage

This fork includes a small, offline helper for turning a Madeira diagnostic log
into a compact list of high-signal compatibility markers.

The helper is intended for repeatable device testing, especially on iPad and
M-series hardware. It does **not** diagnose root cause by itself and does not
replace the original log in a bug report.

## Run it

Export `madeira-log.txt` from Madeira, then run:

```sh
python3 tools/madeira_log_triage.py /path/to/madeira-log.txt
```

To also save a machine-readable report:

```sh
python3 tools/madeira_log_triage.py /path/to/madeira-log.txt \
  --json madeira-triage.json
```

The script is dependency-free, read-only, makes no network calls, and redacts
common local container/user paths and secret-like values from the sample lines
it prints.

## What it currently recognizes

The rules deliberately stay narrow and correspond to signals already used by
Madeira or documented in its issue/debug history:

- missing debugger attachment at the JIT pool request
- JIT pool address-space failures
- Windows `0xC0000005` access violations
- Windows `0xC0000017` out-of-memory exits
- recurrence of the historical M4 TEB/TSD-slot failure pattern
- StikDebug launch responses that do not contain the expected integer PID
- Steam refusal 29 / `invalid platform`
- positive markers for debugger attachment at the pool request and clean x64
  probe output

If a rule matches, treat it as a pointer to inspect the surrounding lines, not
as proof of a specific bug.

## Recommended M4/iPad report bundle

For a reproducible compatibility report, record:

1. Madeira build SHA/version.
2. iPad model and iPadOS version.
3. Whether Settings shows JIT and Memory+ as available before launch.
4. The game/test executable and architecture (x86 or x86-64).
5. The original `madeira-log.txt`.
6. The triage output from this tool.
7. Exact reproduction steps and whether the result repeats after a fresh app
   launch.

The upstream project already targets both iPhone and iPad
(`TARGETED_DEVICE_FAMILY = "1,2"`). M4-specific failures should therefore be
reported as runtime compatibility problems rather than assumed to be an
unsupported-device-family build issue.

## Relevant upstream reports

- `willfaust/Madeira#6` — M4/M-series iPad support
- `willfaust/Madeira#94` — unexpected PID response while enabling JIT
- `willfaust/Madeira#102` — iPad Pro M4 diagnostic logs

When filing upstream, attach the original diagnostic log in addition to this
summary so maintainers can inspect evidence the heuristic rules do not cover.
