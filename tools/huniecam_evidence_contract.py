#!/usr/bin/env python3
"""Validate that HunieCam evidence files belong to one coherent device run.

Contract V4 validates Run Context V2 hashes for session, run record, guard,
performance, owned-EXE import audit and owned native-module audit. Cycle 8 also
requires the current final context to expose the input mode already sealed inside
its hashed run profile. Legacy artifacts remain readable for diagnosis.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib
from typing import Any
SCHEMA="MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4"
SUPPORTED={"preflight":{"MADEIRA_HUNIECAM_PROBE_V3","MADEIRA_HUNIECAM_PROBE_V4"},"session":{"MADEIRA_HUNIECAM_SESSION_V2","MADEIRA_HUNIECAM_SESSION_V3"},"guard":{"MADEIRA_HUNIECAM_CONFIG_GUARD_V1","MADEIRA_HUNIECAM_CONFIG_GUARD_V2"},"performance":{"MADEIRA_HUNIECAM_PERFORMANCE_V1","MADEIRA_HUNIECAM_PERFORMANCE_V2"},"run_record":{"MADEIRA_HUNIECAM_RUN_RECORD_V1"},"run_context":{"MADEIRA_HUNIECAM_RUN_CONTEXT_V1","MADEIRA_HUNIECAM_RUN_CONTEXT_V2"},"pe_imports":{"MADEIRA_HUNIECAM_PE_IMPORTS_V1"},"native_modules":{"MADEIRA_HUNIECAM_NATIVE_MODULES_V1"},"acceptance":{"MADEIRA_HUNIECAM_ACCEPTANCE_V2","MADEIRA_HUNIECAM_ACCEPTANCE_V3","MADEIRA_HUNIECAM_ACCEPTANCE_V4","MADEIRA_HUNIECAM_ACCEPTANCE_V5","MADEIRA_HUNIECAM_ACCEPTANCE_V6","MADEIRA_HUNIECAM_ACCEPTANCE_V7","MADEIRA_HUNIECAM_ACCEPTANCE_V8","MADEIRA_HUNIECAM_ACCEPTANCE_V9","MADEIRA_HUNIECAM_ACCEPTANCE_V10"}}
def load(path:pathlib.Path|None)->dict[str,Any]|None: return None if path is None else json.loads(path.read_text(encoding="utf-8"))
def _sha_json(value:Any)->str: return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")).hexdigest()
def _exe_hash(preflight:dict[str,Any]|None)->str|None:
    if not preflight:return None
    identity=preflight.get("identity") if isinstance(preflight.get("identity"),dict) else {}; return identity.get("exe_sha256")

def validate(preflight:dict[str,Any]|None,session:dict[str,Any]|None=None,guard:dict[str,Any]|None=None,performance:dict[str,Any]|None=None,run_record:dict[str,Any]|None=None,acceptance:dict[str,Any]|None=None,run_context:dict[str,Any]|None=None,pe_imports:dict[str,Any]|None=None,native_modules:dict[str,Any]|None=None)->dict[str,Any]:
    artifacts={"preflight":preflight,"session":session,"guard":guard,"performance":performance,"run_record":run_record,"run_context":run_context,"pe_imports":pe_imports,"native_modules":native_modules,"acceptance":acceptance}; errors=[]; warnings=[]; schemas={}
    if not preflight: errors.append("Preflight is required to anchor evidence to the owned game binary.")
    for name,value in artifacts.items():
        if value is None: continue
        schema=value.get("schema"); schemas[name]=schema; allowed=SUPPORTED.get(name,set())
        if allowed and schema not in allowed: errors.append(f"Unsupported {name} schema: {schema!r}; supported: {sorted(allowed)}")
    owned_hash=_exe_hash(preflight)
    if preflight and not owned_hash: errors.append("Preflight is missing identity.exe_sha256.")
    if session:
        embedded=session.get("preflight") if isinstance(session.get("preflight"),dict) else {}; ident=embedded.get("identity") if isinstance(embedded.get("identity"),dict) else {}; sh=ident.get("exe_sha256")
        if sh and owned_hash and sh!=owned_hash: errors.append("Session embedded executable hash does not match the supplied preflight.")
        ev=session.get("evidence") if isinstance(session.get("evidence"),dict) else {}
        if not ev.get("madeira_log_present",False): warnings.append("Session report does not prove a Madeira log was present.")
    if guard:
        if guard.get("status")=="FAIL": errors.append("Config guard rejected the recorded launch profile; do not promote this run as valid evidence.")
        elif guard.get("status")=="WARN": warnings.append("Config guard contains warnings/unreviewed variables.")
    record_build=record_profile=None
    if run_record:
        build=run_record.get("build") if isinstance(run_record.get("build"),dict) else {}; material=build.get("material") if isinstance(build.get("material"),dict) else {}; rh=material.get("exe_sha256"); record_build=build.get("fingerprint_sha256"); record_profile=run_record.get("profile_sha256")
        if rh and owned_hash and rh!=owned_hash: errors.append("Run record executable hash does not match preflight.")
        if not run_record.get("ready_for_comparison"): errors.append("Run record is not ready_for_comparison.")
        if session:
            rs=run_record.get("session") if isinstance(run_record.get("session"),dict) else {}
            if int(rs.get("deepest_stage",-1))!=int(session.get("deepest_stage",0)): errors.append("Run record deepest stage does not match session report.")
    context_v2=bool(run_context and run_context.get("schema")=="MADEIRA_HUNIECAM_RUN_CONTEXT_V2")
    if run_context:
        if not run_context.get("ready"): errors.append("Run context is not ready.")
        if run_record:
            if run_context.get("build_fingerprint_sha256")!=record_build: errors.append("Run context build fingerprint does not match run record.")
            if run_context.get("profile_sha256")!=record_profile: errors.append("Run context profile fingerprint does not match run record.")
            if run_context.get("run_record_sha256")!=_sha_json(run_record): errors.append("Run context does not hash the supplied run record; evidence may be mixed across launches.")
            profile=run_record.get("profile") if isinstance(run_record.get("profile"),dict) else {}
            if run_context.get("input_mode")!=profile.get("input_mode"): errors.append("Run context input mode does not match the input mode inside the hashed run profile.")
        if session and run_context.get("session_sha256")!=_sha_json(session): errors.append("Run context does not hash the supplied session report; evidence may be mixed across launches.")
        if context_v2:
            for label,value,key in (("config-guard",guard,"guard_sha256"),("performance",performance,"performance_sha256"),("PE import",pe_imports,"pe_imports_sha256"),("native-module",native_modules,"native_modules_sha256")):
                if value is not None and run_context.get(key)!=_sha_json(value): errors.append(f"Run context does not hash the supplied {label} report; evidence may be mixed across launches.")
                if value is None and run_context.get(key): errors.append(f"Run context seals a {label} report but none was supplied to the contract.")
            if native_modules is not None and run_context.get("native_module_set_sha256")!=native_modules.get("module_set_sha256"): errors.append("Run context native-module-set fingerprint does not match the supplied native-module audit.")
        else: warnings.append("Legacy Run Context V1 is readable but does not seal all current evidence.")
        logs=run_context.get("logs") if isinstance(run_context.get("logs"),dict) else {}; md=logs.get("madeira") if isinstance(logs.get("madeira"),dict) else {}
        if not md.get("present"): errors.append("Run context does not prove a Madeira log was present.")
    else: warnings.append("No per-launch run context supplied; final acceptance requires Context V2.")
    if pe_imports:
        if not pe_imports.get("valid"): errors.append("PE import audit is invalid.")
        ih=pe_imports.get("file_sha256")
        if ih and owned_hash and ih!=owned_hash: errors.append("PE import audit came from a different executable than preflight.")
    if native_modules and not native_modules.get("valid"): errors.append("Native-module audit is invalid; bundled dependency provenance is incomplete.")
    if performance:
        cap=performance.get("fps_cap") if isinstance(performance.get("fps_cap"),dict) else {}
        if cap and cap.get("expected") is not None and cap.get("effective") is False: warnings.append("The intended FPS cap was not proven effective.")
    complete=context_v2 and bool(run_context and all(run_context.get(k) for k in ("guard_sha256","performance_sha256","pe_imports_sha256","native_modules_sha256","native_module_set_sha256","input_mode")))
    if run_context and context_v2 and not run_context.get("input_mode"): warnings.append("Current Context V2 does not expose a sealed input mode. It is diagnostic-only for Cycle 8 final acceptance; regenerate with Pipeline V9+.")
    if acceptance and acceptance.get("accepted") is True:
        if errors: errors.append("Acceptance says ACCEPTED while contract has provenance/schema errors.")
        if performance and not performance.get("comparison_clean",False): errors.append("Acceptance says ACCEPTED but performance evidence is not clean.")
        if not complete: errors.append("Final acceptance requires fully sealed Run Context V2 including owned dependency audits and input mode.")
        if run_context and acceptance.get("run_id_sha256") and acceptance.get("run_id_sha256")!=run_context.get("run_id_sha256"): errors.append("Acceptance report run ID does not match run context.")
        if run_context and acceptance.get("accepted_touch_mode") and acceptance.get("accepted_touch_mode")!=run_context.get("input_mode"): errors.append("Acceptance touch mode does not match the sealed run-context input mode.")
    return {"schema":SCHEMA,"valid":not errors,"owned_executable_sha256":owned_hash,"run_id_sha256":run_context.get("run_id_sha256") if run_context else None,"sealed_input_mode":run_context.get("input_mode") if run_context else None,"run_context_v2_complete":complete,"artifact_schemas":schemas,"present_artifacts":[n for n,v in artifacts.items() if v is not None],"errors":errors,"warnings":warnings,"rule":"Final evidence must use Context V2 sealing guard, performance, PE imports, the owned native-module set and the selected input mode. Never mix evidence across run IDs or interaction modes."}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--preflight",type=pathlib.Path,required=True); p.add_argument("--session",type=pathlib.Path); p.add_argument("--guard",type=pathlib.Path); p.add_argument("--performance",type=pathlib.Path); p.add_argument("--run-record",type=pathlib.Path); p.add_argument("--run-context",type=pathlib.Path); p.add_argument("--pe-imports",type=pathlib.Path); p.add_argument("--native-modules",type=pathlib.Path); p.add_argument("--acceptance",type=pathlib.Path); p.add_argument("--json",dest="json_path",type=pathlib.Path); args=p.parse_args(); report=validate(load(args.preflight),load(args.session),load(args.guard),load(args.performance),load(args.run_record),load(args.acceptance),load(args.run_context),load(args.pe_imports),load(args.native_modules)); text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path: args.json_path.write_text(text+"\n",encoding="utf-8")
    print(text); return 0 if report["valid"] else 2
if __name__=="__main__": raise SystemExit(main())
