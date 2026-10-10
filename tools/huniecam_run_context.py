#!/usr/bin/env python3
"""Create a deterministic identity for one HunieCam/Madeira launch evidence set.

Run Context V2 seals the exact build/profile, session, run record, config guard,
performance report, owned-EXE import audit, owned native-module audit, and
Madeira/Unity log contents. Cycle 8 also exposes the input mode already contained
inside the hashed run profile so final acceptance can prove the physical touch
mode matches the repeatable sealed profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_RUN_CONTEXT_V2"

def _sha_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _sha_json(value: Any) -> str: return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
def text_descriptor(text: str, kind: str) -> dict[str, Any]:
    encoded=text.encode("utf-8",errors="replace"); return {"kind":kind,"present":bool(text.strip()),"chars":len(text),"lines":len(text.splitlines()),"text_sha256":_sha_bytes(encoded)}

def build(run_record: dict[str, Any] | None, session: dict[str, Any] | None, madeira_text: str, unity_text: str, guard: dict[str, Any] | None = None, performance: dict[str, Any] | None = None, pe_imports: dict[str, Any] | None = None, native_modules: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str]=[]; record=run_record or {}; sess=session or {}; guard_data=guard or {}; perf=performance or {}; pe=pe_imports or {}; native=native_modules or {}
    build_obj=record.get("build") if isinstance(record.get("build"),dict) else {}; build_fp=build_obj.get("fingerprint_sha256"); profile_fp=record.get("profile_sha256"); profile=record.get("profile") if isinstance(record.get("profile"),dict) else {}; input_mode=profile.get("input_mode")
    if record.get("schema")!="MADEIRA_HUNIECAM_RUN_RECORD_V1": errors.append(f"Unsupported/missing run record schema: {record.get('schema')!r}")
    if not record.get("ready_for_comparison"): errors.append("Run record is not provenance-ready.")
    if not str(sess.get("schema","")).startswith("MADEIRA_HUNIECAM_SESSION_V"): errors.append(f"Unsupported/missing HunieCam session schema: {sess.get('schema')!r}")
    if guard_data and not str(guard_data.get("schema","")).startswith("MADEIRA_HUNIECAM_CONFIG_GUARD_V"): errors.append(f"Unsupported guard schema: {guard_data.get('schema')!r}")
    if perf and not str(perf.get("schema","")).startswith("MADEIRA_HUNIECAM_PERFORMANCE_V"): errors.append(f"Unsupported performance schema: {perf.get('schema')!r}")
    if pe and pe.get("schema")!="MADEIRA_HUNIECAM_PE_IMPORTS_V1": errors.append(f"Unsupported PE import schema: {pe.get('schema')!r}")
    if native and native.get("schema")!="MADEIRA_HUNIECAM_NATIVE_MODULES_V1": errors.append(f"Unsupported native-module schema: {native.get('schema')!r}")
    if not build_fp: errors.append("Owned-build fingerprint is missing.")
    if not profile_fp: errors.append("Launch-profile fingerprint is missing.")
    madeira=text_descriptor(madeira_text,"madeira_log"); unity=text_descriptor(unity_text,"unity_log")
    if not madeira["present"]: errors.append("Madeira log is required to identify a launch.")
    session_sha=_sha_json(sess) if sess else None; record_sha=_sha_json(record) if record else None; guard_sha=_sha_json(guard_data) if guard_data else None; perf_sha=_sha_json(perf) if perf else None; pe_sha=_sha_json(pe) if pe else None; native_sha=_sha_json(native) if native else None
    native_set=native.get("module_set_sha256") if native else None
    material={"build_fingerprint_sha256":build_fp,"profile_sha256":profile_fp,"session_sha256":session_sha,"run_record_sha256":record_sha,"guard_sha256":guard_sha,"performance_sha256":perf_sha,"pe_imports_sha256":pe_sha,"native_modules_sha256":native_sha,"native_module_set_sha256":native_set,"madeira_log_text_sha256":madeira["text_sha256"],"unity_log_text_sha256":unity["text_sha256"] if unity["present"] else None}
    run_id=_sha_json(material) if build_fp and profile_fp and session_sha and record_sha and madeira["present"] else None
    failures=sorted({str(x.get("code")) for x in sess.get("failures",[]) if isinstance(x,dict) and x.get("code")}); markers=sorted({str(x.get("code")) for x in sess.get("markers",[]) if isinstance(x,dict) and x.get("code")})
    return {"schema":SCHEMA,"title":"HunieCam Studio","steam_app_id":426000,"run_id_sha256":run_id,"build_fingerprint_sha256":build_fp,"profile_sha256":profile_fp,"input_mode":input_mode,"session_sha256":session_sha,"run_record_sha256":record_sha,"guard_sha256":guard_sha,"performance_sha256":perf_sha,"pe_imports_sha256":pe_sha,"native_modules_sha256":native_sha,"native_module_set_sha256":native_set,"session_summary":{"schema":sess.get("schema"),"deepest_stage":int(sess.get("deepest_stage",0)) if sess else 0,"deepest_stage_name":sess.get("deepest_stage_name"),"failure_codes":failures,"marker_codes":markers},"profile_summary":{"input_mode":input_mode,"launch_mode":profile.get("launch_mode"),"resolution":profile.get("resolution"),"display":profile.get("display"),"fps":profile.get("fps")},"guard_summary":{"schema":guard_data.get("schema"),"status":guard_data.get("status"),"experiment":guard_data.get("experiment")} if guard_data else None,"performance_summary":{"schema":perf.get("schema"),"comparison_clean":perf.get("comparison_clean"),"fps_cap":perf.get("fps_cap")} if perf else None,"owned_native_summary":{"pe_import_audit_valid":pe.get("valid") if pe else None,"native_module_audit_valid":native.get("valid") if native else None,"native_module_count":native.get("module_count") if native else None},"logs":{"madeira":madeira,"unity":unity},"material":material,"ready":not errors,"errors":errors,"privacy":{"raw_log_text_embedded":False,"absolute_paths_embedded":False,"credentials_embedded":False,"binary_contents_embedded":False},"rule":"The run ID seals this launch's exact session/profile/guard/performance/logs and owned native dependency audits. The exposed input_mode comes from the hashed profile, so a different Madeira interaction mode changes the profile/run identity rather than being hidden."}

def _read(path: pathlib.Path | None)->str: return path.read_text(encoding="utf-8",errors="replace") if path else ""
def _load(path: pathlib.Path | None)->dict[str,Any]|None: return json.loads(path.read_text(encoding="utf-8")) if path else None

def main()->int:
    p=argparse.ArgumentParser(description="Create one sealed HunieCam launch run context"); p.add_argument("--run-record",type=pathlib.Path,required=True); p.add_argument("--session",type=pathlib.Path,required=True); p.add_argument("--guard",type=pathlib.Path); p.add_argument("--performance",type=pathlib.Path); p.add_argument("--pe-imports",type=pathlib.Path); p.add_argument("--native-modules",type=pathlib.Path); p.add_argument("--madeira-log",type=pathlib.Path,required=True); p.add_argument("--unity-log",type=pathlib.Path); p.add_argument("--json",dest="json_path",type=pathlib.Path); args=p.parse_args(); report=build(_load(args.run_record),_load(args.session),_read(args.madeira_log),_read(args.unity_log),_load(args.guard),_load(args.performance),_load(args.pe_imports),_load(args.native_modules)); text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path: args.json_path.write_text(text+"\n",encoding="utf-8")
    print(text); return 0 if report["ready"] else 2

if __name__=="__main__": raise SystemExit(main())
