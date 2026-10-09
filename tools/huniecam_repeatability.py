#!/usr/bin/env python3
"""Prove HunieCam cold-launch repeatability from sealed Run Context V2 files.

Cycle 6 V3 additionally requires the exact owned native-module set to remain
identical across launches, so a changed plugin DLL cannot hide behind an unchanged
main EXE/build fingerprint.
"""
from __future__ import annotations
import argparse, json, pathlib
from typing import Any
SCHEMA="MADEIRA_HUNIECAM_REPEATABILITY_V3"; REQUIRED_CONTEXT_SCHEMA="MADEIRA_HUNIECAM_RUN_CONTEXT_V2"

def analyze(contexts:list[dict[str,Any]],minimum_runs:int=3,minimum_stage:int=75)->dict[str,Any]:
    errors=[]; warnings=[]; rows=[]
    for index,ctx in enumerate(contexts,1):
        summary=ctx.get("session_summary") if isinstance(ctx.get("session_summary"),dict) else {}
        row={"index":index,"schema":ctx.get("schema"),"ready":bool(ctx.get("ready")),"run_id_sha256":ctx.get("run_id_sha256"),"build_fingerprint_sha256":ctx.get("build_fingerprint_sha256"),"profile_sha256":ctx.get("profile_sha256"),"native_module_set_sha256":ctx.get("native_module_set_sha256"),"guard_sha256":ctx.get("guard_sha256"),"performance_sha256":ctx.get("performance_sha256"),"pe_imports_sha256":ctx.get("pe_imports_sha256"),"native_modules_sha256":ctx.get("native_modules_sha256"),"deepest_stage":int(summary.get("deepest_stage",0)),"failure_codes":sorted(str(x) for x in summary.get("failure_codes",[]) if x)}; rows.append(row)
        if row["schema"]!=REQUIRED_CONTEXT_SCHEMA: errors.append(f"Run {index} must use {REQUIRED_CONTEXT_SCHEMA}; got {row['schema']!r}.")
        if not row["ready"] or not row["run_id_sha256"]: errors.append(f"Run {index} is not a sealed/ready launch context.")
        if not all(row[k] for k in ("guard_sha256","performance_sha256","pe_imports_sha256","native_modules_sha256","native_module_set_sha256")): errors.append(f"Run {index} does not seal guard, performance and owned native-module evidence.")
        if row["deepest_stage"]<minimum_stage: errors.append(f"Run {index} reached stage {row['deepest_stage']}, below required stage {minimum_stage}.")
        if row["failure_codes"]: errors.append(f"Run {index} contains triaged failure code(s): {', '.join(row['failure_codes'])}.")
    run_ids=[r["run_id_sha256"] for r in rows if r["run_id_sha256"]]; unique_ids=set(run_ids); builds={r["build_fingerprint_sha256"] for r in rows if r["build_fingerprint_sha256"]}; profiles={r["profile_sha256"] for r in rows if r["profile_sha256"]}; native_sets={r["native_module_set_sha256"] for r in rows if r["native_module_set_sha256"]}
    if len(rows)<minimum_runs: errors.append(f"Need at least {minimum_runs} sealed cold launches; received {len(rows)}.")
    if len(unique_ids)!=len(run_ids): errors.append("Duplicate run IDs were supplied; repeated copies of one launch do not prove cold-launch repeatability.")
    if len(unique_ids)<minimum_runs: errors.append(f"Need at least {minimum_runs} unique run IDs; found {len(unique_ids)}.")
    if len(builds)!=1: errors.append("Cold-launch contexts do not all use one identical owned-build fingerprint.")
    if len(profiles)!=1: errors.append("Cold-launch contexts do not all use one identical launch-profile fingerprint.")
    if len(native_sets)!=1: errors.append("Cold-launch contexts do not all use one identical owned native-module set.")
    if len(rows)>minimum_runs: warnings.append("More than the minimum number of launches were supplied; every supplied launch must still pass.")
    return {"schema":SCHEMA,"passed":not errors,"required_context_schema":REQUIRED_CONTEXT_SCHEMA,"minimum_runs":minimum_runs,"minimum_stage":minimum_stage,"run_count":len(rows),"unique_run_count":len(unique_ids),"build_fingerprint_sha256":next(iter(builds)) if len(builds)==1 else None,"profile_sha256":next(iter(profiles)) if len(profiles)==1 else None,"native_module_set_sha256":next(iter(native_sets)) if len(native_sets)==1 else None,"runs":rows,"errors":errors,"warnings":warnings,"rule":"Three cold launches means three distinct Context V2 IDs on the same build/profile/native-module set, with guard/performance/dependency evidence sealed and scene stage reached without fatal triage errors."}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("contexts",nargs="+",type=pathlib.Path); p.add_argument("--minimum-runs",type=int,default=3); p.add_argument("--minimum-stage",type=int,default=75); p.add_argument("--json",dest="json_path",type=pathlib.Path); args=p.parse_args()
    if args.minimum_runs<1 or args.minimum_stage<0: p.error("minimum-runs must be >=1 and minimum-stage must be >=0")
    report=analyze([json.loads(x.read_text(encoding="utf-8")) for x in args.contexts],args.minimum_runs,args.minimum_stage); text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path: args.json_path.write_text(text+"\n",encoding="utf-8")
    print(text); return 0 if report["passed"] else 2
if __name__=="__main__": raise SystemExit(main())
