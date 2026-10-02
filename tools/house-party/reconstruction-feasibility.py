#!/usr/bin/env python3
"""Evidence-based House Party Unity reconstruction feasibility index.

This is a prioritization heuristic, not a completion percentage or success
probability. It consumes the compatibility manifest and an optional private
asset-recovery inventory, then explains every point/penalty.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

def val(node, default=None):
    return node.get("value", default) if isinstance(node, dict) else node if node is not None else default

def score(manifest: dict, recovered: dict | None = None) -> dict:
    recovered = recovered or {}
    engine = manifest.get("engine", {})
    compat = manifest.get("compatibility", {})
    backend = str(val(engine.get("scripting_backend"), "unknown")).lower()
    unity = str(val(engine.get("family"), "unknown")).lower()
    unity_version = val(engine.get("unity_version"))
    plugins = compat.get("native_plugins") or []
    assemblies = compat.get("managed_assemblies") or []
    if isinstance(assemblies, dict):
        assemblies = assemblies.get("files") or []

    points = 0.0
    reasons = []

    def add(delta: float, code: str, detail: str):
        nonlocal points
        points += delta
        reasons.append({"code": code, "points": delta, "detail": detail})

    if unity == "unity":
        add(1.0, "unity-confirmed", "Unity engine evidence is present.")
    else:
        add(-2.0, "engine-unknown", "Unity engine is not confirmed; reconstruction tooling cannot be selected reliably.")

    if unity_version:
        add(1.0, "unity-version-known", f"Unity version observed: {unity_version}.")
    else:
        add(-0.5, "unity-version-unknown", "Exact Unity version is not yet observed.")

    if backend == "mono":
        add(3.0, "mono-managed-logic", "Mono preserves managed assemblies, materially improving private script reconstruction.")
    elif backend == "il2cpp":
        add(-2.0, "il2cpp-native-logic", "IL2CPP converts managed gameplay code to native code; source-level reconstruction is substantially harder.")
    else:
        add(-1.0, "scripting-backend-unknown", "Mono vs IL2CPP is still unverified.")

    if assemblies:
        add(1.0, "assembly-metadata", f"{len(assemblies)} managed/scripting assembly entries were inventoried.")
    elif backend == "mono":
        add(-1.0, "mono-assemblies-missing", "Mono was detected but managed assembly inventory is empty.")

    pcount = len(plugins)
    if pcount == 0:
        add(1.0, "no-native-plugins", "No native plugin files were inventoried.")
    elif pcount <= 3:
        add(0.0, "few-native-plugins", f"{pcount} native plugin(s) need platform-by-platform review.")
    else:
        add(-1.0, "many-native-plugins", f"{pcount} native plugins increase manual replacement/porting work.")

    asset_fields = {
        "scenes_recovered": (1.0, "scenes"),
        "prefabs_recovered": (1.0, "prefabs"),
        "serialized_data_recovered": (1.0, "serialized data"),
        "animations_recovered": (0.5, "animations"),
        "shaders_recovered": (0.5, "shaders"),
    }
    for key, (weight, label) in asset_fields.items():
        n = int(recovered.get(key) or 0)
        if n > 0:
            add(weight, key, f"Recovered {n} {label} item(s).")

    missing_logic = int(recovered.get("unavailable_source_logic") or 0)
    if missing_logic:
        add(-min(2.0, 0.25 * missing_logic), "unavailable-source-logic",
            f"{missing_logic} known gameplay/source-logic gaps require manual recreation.")

    platform_deps = int(recovered.get("platform_specific_dependencies") or 0)
    if platform_deps:
        add(-min(1.5, 0.25 * platform_deps), "platform-specific-dependencies",
            f"{platform_deps} platform-specific dependencies need replacement or abstraction.")

    manual = recovered.get("manual_recreation")
    if manual in {"high", "very-high"}:
        add(-2.0 if manual == "very-high" else -1.0, "manual-recreation", f"Manual recreation estimate: {manual}.")
    elif manual == "low":
        add(0.5, "manual-recreation", "Manual recreation estimate: low.")

    index = max(0.0, min(10.0, points + 3.0))
    if index >= 8:
        band = "favorable"
    elif index >= 6:
        band = "plausible"
    elif index >= 3:
        band = "difficult"
    else:
        band = "poor"

    missing = []
    for key in ("scenes_recovered","prefabs_recovered","serialized_data_recovered","animations_recovered","shaders_recovered"):
        if key not in recovered:
            missing.append(key)

    return {
        "schema_version": 1,
        "feasibility_index_0_to_10": round(index, 1),
        "band": band,
        "interpretation": "Prioritization heuristic only; not a probability, ETA, legal conclusion, or completion percentage.",
        "scripting_backend": backend,
        "reasons": reasons,
        "missing_recovery_evidence": missing,
        "recommended_next_evidence": (
            "Run private AssetRipper/UnityPy inventory against a derived copy; use current Cpp2IL development only if IL2CPP is reconfirmed."
            if backend == "il2cpp" else
            "Inventory managed gameplay assemblies and recovered scenes/prefabs before committing to a true-native reconstruction."
        ),
    }

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--recovered", help="Optional private recovery inventory JSON")
    ap.add_argument("-o","--output")
    ns=ap.parse_args(argv)
    manifest=json.loads(Path(ns.manifest).read_text())
    recovered=json.loads(Path(ns.recovered).read_text()) if ns.recovered else None
    result=score(manifest,recovered)
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if ns.output:
        Path(ns.output).write_text(text)
    else:
        print(text,end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
