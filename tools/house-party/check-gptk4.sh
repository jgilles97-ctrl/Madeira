#!/bin/bash
# Read-only environment probe for Apple's current Game Porting Toolkit 4 workflow.
# It does not install or change anything.
set -euo pipefail

pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
    warn "not running on macOS; Apple GPU tools cannot be validated here"
    exit 0
fi

arch="$(uname -m)"
[[ "$arch" == "arm64" ]] && pass "Apple silicon ($arch)" || warn "architecture is $arch, expected arm64"

major="$(sw_vers -productVersion | cut -d. -f1)"
if [[ "$major" =~ ^[0-9]+$ ]] && (( major >= 27 )); then
    pass "macOS $(sw_vers -productVersion) supports the current gpucapture/gpudebug workflow"
else
    warn "macOS $(sw_vers -productVersion); current GPTK 4 agent workflow expects macOS 27+"
fi

if command -v xcodebuild >/dev/null 2>&1; then
    xv="$(xcodebuild -version | tr '\n' ' ')"
    pass "$xv"
else
    warn "xcodebuild not found"
fi

for tool in gpucapture gpudebug; do
    if xcrun -f "$tool" >/dev/null 2>&1; then
        pass "$tool: $(xcrun -f "$tool")"
    else
        warn "$tool not found through xcrun"
    fi
done

if command -v codex >/dev/null 2>&1; then
    pass "Codex CLI found: $(command -v codex)"
    plugins="$(codex plugin list 2>&1 || true)"
    if grep -qi 'game-porting-skills' <<<"$plugins"; then
        pass "Apple game-porting-skills plugin is installed"
    else
        warn "Apple game-porting-skills not visible in 'codex plugin list'"
        printf '%s\n' "      Official install:"
        printf '%s\n' "      codex plugin marketplace add https://github.com/apple/game-porting-toolkit"
        printf '%s\n' "      codex plugin add game-porting-skills@game-porting-toolkit"
    fi
else
    warn "Codex CLI not found"
fi

# Common GPTK installation markers. Absence is only a warning because Apple may
# change package locations; xcrun/tool discovery above is stronger evidence.
found=0
for p in \
    "/Library/Apple/usr/libexec/oah" \
    "/Applications/Game Porting Toolkit.app" \
    "$HOME/Game Porting Toolkit"; do
    if [[ -e "$p" ]]; then
        pass "GPTK-related installation marker: $p"
        found=1
    fi
done
(( found )) || warn "no common GPTK installation marker found; verify GPTK 4 in Apple developer downloads"

echo
echo "Probe only: no packages, plugins, repositories, or settings were changed."
