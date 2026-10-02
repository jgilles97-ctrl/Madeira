#!/usr/bin/env python3
"""Read-only Windows/Unity game fingerprinting for the House Party port.

The source tree is never modified. The report separates directly observed facts
from inferences so later sessions can compare manifests without rediscovering
the same architecture.
"""
from __future__ import annotations
import argparse, hashlib, json, re, struct
from datetime import datetime, timezone
from pathlib import Path

PE_MACHINE = {0x014c: "x86", 0x8664: "x86_64", 0xAA64: "arm64", 0xA641: "arm64ec"}
MEDIA_EXTS = {".mp4", ".mov", ".webm", ".wmv", ".avi", ".m4v", ".mp3", ".wav", ".ogg", ".wma"}
PLUGIN_EXTS = {".dll", ".bundle", ".so"}
UNITY_VERSION_RE = re.compile(rb"(?<!\d)(20\d{2}\.\d+\.\d+[fpab]\d+(?:c\d+)?)")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def pe_info(path: Path) -> dict | None:
    """Return PE machine/import DLLs without loading or executing the binary."""
    try:
        with path.open("rb") as f:
            head = f.read(0x1000)
            if len(head) < 0x40 or head[:2] != b"MZ":
                return None
            peoff = struct.unpack_from("<I", head, 0x3C)[0]
            f.seek(peoff)
            sig = f.read(24)
            if len(sig) < 24 or sig[:4] != b"PE\0\0":
                return None
            machine, nsec, _, _, _, opt_size, _ = struct.unpack_from("<HHIIIHH", sig, 4)
            opt = f.read(opt_size)
            if len(opt) < opt_size:
                return None
            magic = struct.unpack_from("<H", opt, 0)[0]
            dd = 112 if magic == 0x20B else 96 if magic == 0x10B else None
            if dd is None:
                return {"machine": PE_MACHINE.get(machine, hex(machine)), "imports": []}
            imp_rva, imp_size = struct.unpack_from("<II", opt, dd + 8)
            sections = []
            for _ in range(nsec):
                sh = f.read(40)
                if len(sh) < 40:
                    break
                vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", sh, 8)
                sections.append((va, max(vsize, raw_size), raw_ptr, raw_size))

            def rva_off(rva: int):
                for va, span, raw, raw_size in sections:
                    if va <= rva < va + span:
                        delta = rva - va
                        return raw + delta if delta < raw_size else None
                return rva if rva < len(head) else None

            imports = []
            if imp_rva and imp_size:
                imp_off = rva_off(imp_rva)
                if imp_off is not None:
                    f.seek(imp_off)
                    table = f.read(min(imp_size, 1024 * 1024))
                    for pos in range(0, len(table) - 19, 20):
                        orig, ts, chain, name_rva, thunk = struct.unpack_from("<IIIII", table, pos)
                        if not any((orig, ts, chain, name_rva, thunk)):
                            break
                        noff = rva_off(name_rva)
                        if noff is None:
                            continue
                        cur = f.tell()
                        f.seek(noff)
                        raw = bytearray()
                        while len(raw) < 512:
                            b = f.read(1)
                            if not b or b == b"\0":
                                break
                            raw += b
                        f.seek(cur)
                        try:
                            name = raw.decode("ascii").lower()
                        except UnicodeDecodeError:
                            continue
                        if name and name not in imports:
                            imports.append(name)
            return {"machine": PE_MACHINE.get(machine, hex(machine)), "imports": sorted(imports)}
    except (OSError, struct.error, ValueError):
        return None

def find_unity_version(paths: list[Path]):
    candidates = sorted(paths, key=lambda p: (p.name.lower() != "globalgamemanagers",
                                               p.name.lower() != "unityplayer.dll"))
    for p in candidates:
        if p.name.lower() not in {"globalgamemanagers", "unityplayer.dll", "data.unity3d"}:
            continue
        try:
            with p.open("rb") as f:
                data = f.read(8 * 1024 * 1024)
        except OSError:
            continue
        match = UNITY_VERSION_RE.search(data)
        if match:
            return match.group().decode(), str(p)
    return None, None

def evidence(value, source=None, confidence="observed"):
    out = {"value": value, "confidence": confidence}
    if source:
        out["source"] = source
    return out

def read_scripting_assemblies(path: Path | None) -> list[str]:
    if not path:
        return []
    try:
        obj = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    values = obj.get("names", []) if isinstance(obj, dict) else []
    return sorted({str(x) for x in values if isinstance(x, str)})

def il2cpp_metadata_version(path: Path | None):
    if not path:
        return None
    try:
        head = path.read_bytes()[:8]
        if len(head) == 8 and struct.unpack_from("<I", head, 0)[0] == 0xFAB11BAF:
            return struct.unpack_from("<I", head, 4)[0]
    except (OSError, struct.error):
        pass
    return None

def read_boot_config(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    out = {}
    try:
        for raw in path.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip()
            else:
                out[line] = ""
    except OSError:
        return {}
    return dict(sorted(out.items()))

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="Read-only extracted Windows game directory")
    ap.add_argument("-o", "--output", help="JSON output path (default: stdout)")
    ap.add_argument("--hash-all", action="store_true", help="SHA-256 every regular file (slow)")
    args = ap.parse_args(argv)

    root = Path(args.source).expanduser().resolve()
    if not root.is_dir():
        ap.error(f"not a directory: {root}")
    files = [p for p in root.rglob("*") if p.is_file()]
    low = {p.name.lower(): p for p in files}
    exes = [p for p in files if p.suffix.lower() == ".exe"]
    main_exe = next((p for p in exes if p.stem.lower().replace(" ", "").replace("-", "") == "houseparty"),
                    exes[0] if exes else None)
    gameassembly = low.get("gameassembly.dll")
    unityplayer = low.get("unityplayer.dll")
    metadata = next((p for p in files if p.as_posix().lower().endswith(
        "il2cpp_data/metadata/global-metadata.dat")), None)
    mono_dir = next((p for p in root.rglob("MonoBleedingEdge") if p.is_dir()), None)
    assembly_csharp = next((p for p in files if p.name.lower() == "assembly-csharp.dll"
                            and "managed" in p.as_posix().lower()), None)
    scripting_json = next((p for p in files if p.name.lower() == "scriptingassemblies.json"), None)
    boot_config = next((p for p in files if p.name.lower() == "boot.config"
                        and "_data" in p.as_posix().lower()), None)
    managed_assemblies = read_scripting_assemblies(scripting_json)
    metadata_version = il2cpp_metadata_version(metadata)
    boot_values = read_boot_config(boot_config)

    if gameassembly and metadata:
        scripting = evidence("IL2CPP", f"{gameassembly}; {metadata}")
    elif mono_dir or assembly_csharp:
        scripting = evidence("Mono", str(assembly_csharp or mono_dir))
    else:
        scripting = evidence("unknown", confidence="unverified")

    unity_ver, unity_src = find_unity_version(files)
    pe_files, dll_imports = [], set()
    for p in files:
        if p.suffix.lower() not in {".exe", ".dll"}:
            continue
        info = pe_info(p)
        if info:
            pe_files.append({"path": str(p.relative_to(root)), **info})
            dll_imports.update(info["imports"])

    graphics = []
    for dll, api in [("d3d11.dll", "Direct3D 11"), ("d3d12.dll", "Direct3D 12"),
                     ("d3d9.dll", "Direct3D 9"), ("vulkan-1.dll", "Vulkan"),
                     ("opengl32.dll", "OpenGL"), ("dxgi.dll", "DXGI")]:
        if dll in dll_imports:
            graphics.append({"api": api, "evidence": f"PE import {dll}"})

    plugins = sorted(str(p.relative_to(root)) for p in files
                     if p.suffix.lower() in PLUGIN_EXTS
                     and "/plugins/" in ("/" + p.relative_to(root).as_posix().lower()))
    plugin_details = sorted(
        ({"path": row["path"], "machine": row["machine"], "imports": row["imports"]}
         for row in pe_files if row["path"] in plugins),
        key=lambda row: row["path"].lower())
    launchers = sorted({"path": str(p.relative_to(root)), **(pe_info(p) or {})}
                       for p in exes)
    media = sorted(str(p.relative_to(root)) for p in files if p.suffix.lower() in MEDIA_EXTS)
    steam = sorted(str(p.relative_to(root)) for p in files
                   if p.name.lower() in {"steam_api.dll", "steam_api64.dll", "steam_appid.txt"})
    vc = sorted(x for x in dll_imports if re.match(r"(vcruntime|msvcp|concrt|vcomp|ucrtbase).*\.dll$", x))
    input_apis = sorted(x for x in dll_imports if re.match(r"(xinput.*|dinput8?|user32|gameinput)\.dll$", x))
    audio_apis = sorted(x for x in dll_imports if re.match(r"(xaudio.*|x3daudio.*|dsound|winmm|fmod.*)\.dll$", x))
    network_apis = sorted(x for x in dll_imports if x in {"ws2_32.dll", "winhttp.dll", "wininet.dll", "urlmon.dll"})

    important = {x for x in [main_exe, gameassembly, unityplayer, metadata] if x}
    important.update(p for p in files if p.name.lower() in {"steam_api64.dll", "steam_api.dll", "steam_appid.txt"})
    important.update(p for p in files if str(p.relative_to(root)) in plugins)
    important.update(p for p in [scripting_json, boot_config] if p)
    hashes = {}
    for p in (files if args.hash_all else sorted(important)):
        try:
            hashes[str(p.relative_to(root))] = sha256(p)
        except OSError as exc:
            hashes[str(p.relative_to(root))] = f"ERROR: {exc}"

    main_info = pe_info(main_exe) if main_exe else None
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(root),
        "source_policy": "read-only",
        "game": {
            "main_executable": evidence(str(main_exe.relative_to(root)) if main_exe else None,
                                        str(main_exe) if main_exe else None,
                                        "observed" if main_exe else "unverified"),
            "architecture": evidence(main_info["machine"] if main_info else None,
                                     str(main_exe) if main_exe else None,
                                     "observed" if main_info else "unverified"),
            "exact_build_version": evidence(None, confidence="unverified"),
        },
        "engine": {
            "family": evidence("Unity" if unityplayer or gameassembly or metadata or mono_dir else "unknown",
                               str(unityplayer or gameassembly or metadata or mono_dir or ""),
                               "observed" if (unityplayer or gameassembly or metadata or mono_dir) else "unverified"),
            "unity_version": evidence(unity_ver, unity_src, "observed" if unity_ver else "unverified"),
            "scripting_backend": scripting,
            "unity_player": str(unityplayer.relative_to(root)) if unityplayer else None,
            "game_assembly": str(gameassembly.relative_to(root)) if gameassembly else None,
            "global_metadata": str(metadata.relative_to(root)) if metadata else None,
            "il2cpp_metadata_version": evidence(metadata_version, str(metadata) if metadata else None,
                                                "observed" if metadata_version is not None else "unverified"),
            "scripting_assemblies": managed_assemblies,
            "scripting_assemblies_source": str(scripting_json.relative_to(root)) if scripting_json else None,
            "boot_config": {
                "path": str(boot_config.relative_to(root)) if boot_config else None,
                "values": boot_values,
            },
        },
        "compatibility": {
            "graphics_apis": graphics,
            "pe_imports": sorted(dll_imports),
            "vc_runtime_imports": vc,
            "steam_files": steam,
            "input_api_imports": input_apis,
            "audio_api_imports": audio_apis,
            "network_api_imports": network_apis,
            "registry_dependency": evidence("advapi32.dll" in dll_imports,
                                            "PE import advapi32.dll" if "advapi32.dll" in dll_imports else None,
                                            "inferred" if "advapi32.dll" in dll_imports else "unverified"),
            "save_location": evidence(None, confidence="unverified"),
            "native_plugins": plugin_details,
            "launcher_executables": launchers,
            "media_files": media,
            "unity_video_module": evidence(
                any(name.lower().endswith("unityengine.videomodule.dll") for name in managed_assemblies),
                str(scripting_json.relative_to(root)) if scripting_json else None,
                "inferred" if managed_assemblies else "unverified"),
        },
        "hashes": {"mode": "all" if args.hash_all else "important", "sha256": hashes},
        "pe_files": pe_files,
        "notes": [
            "A missing import is not proof an API is unused; Unity/plugins may load DLLs dynamically.",
            "Save location and exact game build version remain unverified until runtime/config evidence identifies them.",
        ],
    }
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
        print(out)
    else:
        print(text)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
