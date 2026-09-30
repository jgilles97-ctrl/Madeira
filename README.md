# Madeira

Run Windows PC games on a non-jailbroken iPhone.

Madeira combines [Wine](https://www.winehq.org/) (ARM64EC),
[FEX-Emu](https://github.com/FEX-Emu/FEX) for x86-64 → ARM64 translation, and
[DXMT](https://github.com/3Shain/DXMT) for D3D11 → Metal, running as a single
Mach process on iOS with wineserver as a thread rather than a separate process.

## Status

Thumper and ULTRAKILL are playable. Marvel Cosmic Invasion has reached
gameplay, though a run has also ended in an unexplained termination and its
controls are not yet reliable. Others reach gameplay at low frame rates. This
is a research project, not a product: expect rough edges, per-title quirks and
breaking changes.

## Requirements

- A non-jailbroken iPhone or iPad. House Party is currently tuned for an iPad
  desktop window; development validation uses an iPad Pro (M4).
- JIT, which on iOS requires a debugger to attach —
  [StikDebug](https://github.com/0-Blu/StikJIT) is what this project uses.
- The StikJIT companion app and [StosVPN](https://apps.apple.com/us/app/stosvpn/id6744003051)
  installed on the device before pressing **Enable JIT**. Madeira only
  provides the URL-scheme integration; it does not bundle the companion.
  On iOS/iPadOS 26+, Madeira targets the current `stikdebug://` protocol with
  the running process PID and retains `stikjit://` only as a legacy fallback.
- An Apple ID for signing. A free account works; its provisioning profiles
  expire after 7 days, so the app must be rebuilt and reinstalled weekly. The
  app's container survives reinstall, so prefixes and saves are preserved.

Because JIT requires debugger attach, this app cannot be distributed through the
App Store. It is installed by sideloading.

On current StikJIT builds, the companion app requires StosVPN to connect the
device to itself. Pair the device in StikJIT, launch Madeira, press **Enable
JIT**, and wait for the JIT badge to turn green before launching House Party.

## Building

### Desktop JITserver on iOS 26+

Run `build/jitserver-macos.sh` after connecting and trusting the iPad by USB.
The helper installs/builds the host transport and copies a Madeira-specific
script into JITserver. Select the USB iPad, select Madeira, and choose
**Enable JIT via Script** with `madeira-jit.js`. This script omits the duplicate
`vAttach` because JITserver has already attached the process; the duplicate
command returns `E96` on iOS 27.

The build is split across several chains — the unix-side Wine libraries, the
ARM64EC PE modules, FEX, DXMT and the iOS app itself. `build/*/build.sh` covers
the native pieces; the app is built with `xcodebuild`.

```sh
git clone --recurse-submodules <this repo>
```

Note that `FEX`, `wine` and `research/dxmt` are submodules pointing at forks
containing the iOS work; upstream clones will not build here.

### House Party iPad build

The current House Party port is exercised as an arm64 device build. After the
toolchains and submodules are available, build the native pieces in this
order:

```sh
bash build/gnutls-ios/build.sh
bash build/freetype-ios/build.sh
bash build/ntdll-unix/build.sh
BUILD_WINESERVER_BASE_IOS=1 bash build/wineserver/build.sh
bash build/win32u-unix/build.sh
bash build/dxmt-ios/build.sh
xcodebuild -project app/Madeira.xcodeproj -scheme Madeira \
  -configuration Release -sdk iphoneos \
  -derivedDataPath ../DerivedData/Unsigned \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build
```

DXMT automatically combines its unix archive with the arm64 iOS LLVM 15
archives under `toolchains/llvm-ios-build/lib/`. The resulting app is an
unsigned development artifact: JIT still requires a debugger/sideload flow,
and a provisioning profile is required before installing it on an iPad.
House Party is available from the app's launch screen and uses DX11 in a
1024×768 desktop window.

For device-side launch experiments, create `house-party-args.txt` in the app's
Documents directory. A non-empty file replaces the default launch flags and
survives reinstall. The packaged runtime can be checked before installation:

```sh
build/check-house-party-inputs.sh
build/verify-house-party.sh
```

The preflight fails early if the twelve Microsoft VC runtime DLLs are absent.
They are intentionally not included in this repository; obtain them from
Microsoft's official redistributable and follow
[`tools/fetch-vcruntime.md`](tools/fetch-vcruntime.md).

To make a device build, open Xcode Settings → Apple Accounts and use
“Download Manual Profiles” for the connected development team first. Xcode’s
GUI account cache is authoritative; a shell-only `-allowProvisioningUpdates`
build can report “No Accounts” even when the account is connected.

Use the repeatable wrapper after the profile is downloaded:

```sh
MADEIRA_DEVICE_ID=<device-udid> build/ios-device.sh
```

If the active Personal Team only has a profile for another development app,
use build-time `DEVELOPMENT_TEAM=<team-id>` and
`PRODUCT_BUNDLE_IDENTIFIER=<profile-bundle-id>` overrides for a device smoke
test; this leaves the checked-in project identity unchanged.

## License

**GPL-3.0-or-later** — see [`LICENSE`](LICENSE). Derivatives that are
distributed must remain open source.

### Upstream licenses vs. this project's forks

Those are the licenses of the **upstream projects**: Wine and GnuTLS
LGPL-2.1-or-later, GMP and Nettle LGPL-3.0-or-later, FEX-Emu and DXMT MIT,
rpmalloc 0BSD. Their texts are in [`LICENSES/`](LICENSES), and upstream code
remains available under them **from upstream**.

**The forks used here are not licensed identically to their upstreams.** Each
carries its own `LICENSE-MADEIRA.md` saying exactly what applies:

| Fork | Terms |
|---|---|
| [`wine`](https://github.com/willfaust/wine) | relicensed to **GPL-3.0-or-later** under LGPL-2.1 §3 |
| [`FEX`](https://github.com/willfaust/FEX), [`dxmt`](https://github.com/willfaust/dxmt) | upstream MIT preserved; modifications **GPL-3.0-or-later** |
| [`rpmalloc`](https://github.com/willfaust/rpmalloc) | upstream 0BSD preserved; Will Faust's modifications **GPL-3.0-or-later** |

This is not retroactive: those forks were public beforehand, so anything
already obtained under a permissive license stays available under it.

[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) has the per-component
breakdown. Note in particular that the Microsoft Visual C++ runtime DLLs are
not distributed here and must be supplied yourself — see
[`tools/fetch-vcruntime.md`](tools/fetch-vcruntime.md).

## A note on upstream contributions

The forks here contain substantial AI-assisted work. FEX-Emu's contribution
policy states that AI must not be used to generate code for contributions to
that project, so **do not submit AI-generated changes from this fork upstream**.
The MIT license permits the fork itself; the policy governs contributions back.
Check each upstream's contribution policy before proposing changes to it.
