#!/usr/bin/env python3
"""Run the HunieCam compatibility analysis pipeline without touching game files.

Cycle 7 Pipeline V8 preserves the sealed build/profile/session/log/guard/
performance/dependency chain and now emits Device Evidence V3, whose physical
iPad form includes HunieCam-specific gameplay drag/release trials.
"""
from __future__ import annotations
import argparse, json, pathlib
from typing import Any
import huniecam_config_guard as config_guard
import huniecam_dependency_plan as dependency_plan_tool
import huniecam_device_evidence as device_evidence_tool
import huniecam_evidence_contract as evidence_contract
import huniecam_evidence_manifest as evidence_manifest
import huniecam_failure_capsule as failure_capsule_tool
import huniecam_issue_matcher as issue_matcher
import huniecam_native_modules as native_modules_tool
import huniecam_next_run as next_run
import huniecam_pe_imports as pe_imports_tool
import huniecam_performance as performance_tool
import huniecam_probe as probe
import huniecam_registry_snapshot as registry_snapshot_tool
import huniecam_run_context as run_context_tool
import huniecam_run_record as run_record_tool
import huniecam_session_triage as session_triage
import huniecam_storage_guard as storage_guard
SCHEMA="MADEIRA_HUNIECAM_PIPELINE_V8"

def read_text(path:pathlib.Path|None)->str: return path.read_text(encoding="utf-8",errors="replace") if path else ""
def write_json(path:pathlib.Path,data:dict[str,Any])->None: path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def run(install:pathlib.Path,madeira_log:pathlib.Path,unity_log:pathlib.Path|None,out_dir:pathlib.Path,*,config_text:str="",arguments:str="",ledger:dict[str,Any]|None=None,storage_root:pathlib.Path|None=None,registry_text:str="",launch_mode:str="direct",resolution:str="1280x720",display:str="fit",fps:int=60,bits:int=32,relative_executable:str|None=None)->dict[str,Any]:
    out_dir.mkdir(parents=True,exist_ok=True)
    pre=probe.probe_install(install); guard=config_guard.inspect(config_text,arguments); madeira_text=read_text(madeira_log); unity_text=read_text(unity_log); combined=madeira_text+"\n"+unity_text
    session=session_triage.analyze(madeira_text,unity_text,pre); issues=issue_matcher.match(combined,pre); perf=performance_tool.analyze(combined,expected_fps=fps); capsule=failure_capsule_tool.extract(combined)
    profile={"launch_mode":launch_mode,"resolution":resolution,"display":display,"fps":fps,"bits":bits,"config":config_text.strip(),"arguments":arguments.strip(),"relative_executable":relative_executable}
    record=run_record_tool.build(pre,session,profile,perf)
    pe_imports=pe_imports_tool.parse(install/"HunieCamStudio.exe"); native_modules=native_modules_tool.scan(install)
    run_context=run_context_tool.build(record,session,madeira_text,unity_text,guard,perf,pe_imports,native_modules)
    dependency_plan=dependency_plan_tool.choose(pe_imports,session,native_modules)
    contract=evidence_contract.validate(pre,session,guard,perf,record,run_context=run_context,pe_imports=pe_imports,native_modules=native_modules)
    nxt=next_run.choose(session,issues,ledger,guard,perf,contract); registry=registry_snapshot_tool.snapshot(registry_text) if registry_text else None; device_template=device_evidence_tool.template(run_context)
    paths={"preflight":out_dir/"huniecam-preflight.json","guard":out_dir/"huniecam-guard.json","session":out_dir/"huniecam-session.json","issues":out_dir/"huniecam-issues.json","performance":out_dir/"huniecam-performance.json","failure_capsule":out_dir/"huniecam-failure-capsule.json","run_record":out_dir/"huniecam-run-record.json","run_context":out_dir/"huniecam-run-context.json","pe_imports":out_dir/"huniecam-pe-imports.json","native_modules":out_dir/"huniecam-native-modules.json","dependency_plan":out_dir/"huniecam-dependency-plan.json","contract":out_dir/"huniecam-evidence-contract.json","next":out_dir/"huniecam-next-run.json","device_template":out_dir/"huniecam-device-evidence-template.json"}
    for key,value in (("preflight",pre),("guard",guard),("session",session),("issues",issues),("performance",perf),("failure_capsule",capsule),("run_record",record),("run_context",run_context),("pe_imports",pe_imports),("native_modules",native_modules),("dependency_plan",dependency_plan),("contract",contract),("next",nxt),("device_template",device_template)): write_json(paths[key],value)
    registry_path=None
    if registry is not None: registry_path=out_dir/"huniecam-registry-snapshot.json"; write_json(registry_path,registry)
    storage=None; storage_path=None
    if storage_root: storage=storage_guard.scan(storage_root); storage_path=out_dir/"huniecam-storage.json"; write_json(storage_path,storage)
    manifest_inputs={"preflight":paths["preflight"],"session":paths["session"],"guard":paths["guard"],"issues":paths["issues"],"performance":paths["performance"],"failure_capsule":paths["failure_capsule"],"run_record":paths["run_record"],"run_context":paths["run_context"],"pe_imports":paths["pe_imports"],"native_modules":paths["native_modules"],"contract":paths["contract"],"device_template":paths["device_template"],"registry_snapshot":registry_path,"madeira_log":madeira_log,"unity_log":unity_log}
    manifest=evidence_manifest.build(manifest_inputs); manifest_path=out_dir/"huniecam-evidence-manifest.json"; write_json(manifest_path,manifest)
    output_names=[p.name for p in paths.values()]+[manifest_path.name]
    if registry_path: output_names.append(registry_path.name)
    if storage_path: output_names.append(storage_path.name)
    categories=pe_imports.get("categories") if isinstance(pe_imports.get("categories"),dict) else {}
    summary={"schema":SCHEMA,"output_directory":out_dir.name,"guard_status":guard.get("status"),"evidence_contract_valid":contract.get("valid"),"run_context_v2_complete":contract.get("run_context_v2_complete"),"run_record_ready":record.get("ready_for_comparison"),"run_context_ready":run_context.get("ready"),"run_id_sha256":run_context.get("run_id_sha256"),"native_module_set_sha256":run_context.get("native_module_set_sha256"),"device_template_schema":device_template.get("schema"),"device_template_linked":bool(device_template.get("run_id_sha256") and device_template.get("run_id_sha256")==run_context.get("run_id_sha256")),"owned_build_fingerprint":(record.get("build") or {}).get("fingerprint_sha256") if isinstance(record.get("build"),dict) else None,"deepest_stage":session.get("deepest_stage"),"deepest_stage_name":session.get("deepest_stage_name"),"best_upstream_issue_match":(issues.get("best_match") or {}).get("issue") if isinstance(issues.get("best_match"),dict) else None,"failure_capsule_signature":capsule.get("signature"),"performance_comparison_clean":perf.get("comparison_clean"),"fps_cap_effective":((perf.get("fps_cap") or {}).get("effective") if isinstance(perf.get("fps_cap"),dict) else None),"pe_import_audit_valid":pe_imports.get("valid"),"native_module_audit_valid":native_modules.get("valid"),"native_module_count":native_modules.get("module_count"),"pe_import_count":pe_imports.get("import_count"),"pe_dependency_categories":sorted(categories),"dependency_plan_status":dependency_plan.get("status"),"registry_configuration_found":registry.get("found") if registry else None,"next_run_status":nxt.get("status"),"next_run_priority":nxt.get("priority"),"next_run_profile":nxt.get("profile"),"storage_large_jit_dumps":storage.get("large_jit_dump_count") if storage else None,"evidence_manifest":manifest_path.name,"device_evidence_template":paths["device_template"].name,"outputs":output_names,"rule":"Do not run guard-rejected profiles, mix run IDs, reuse device forms across launches, or change dependencies without exact owned-module/runtime evidence. Physical acceptance must prove drag release in real HunieCam gameplay."}
    write_json(out_dir/"huniecam-pipeline-summary.json",summary); return summary

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--install",type=pathlib.Path,required=True); p.add_argument("--madeira-log",type=pathlib.Path,required=True); p.add_argument("--unity-log",type=pathlib.Path); p.add_argument("--registry",type=pathlib.Path); p.add_argument("--config",type=pathlib.Path); p.add_argument("--arguments",default=""); p.add_argument("--ledger",type=pathlib.Path); p.add_argument("--storage-root",type=pathlib.Path); p.add_argument("--launch-mode",choices=["direct","dock"],default="direct"); p.add_argument("--resolution",default="1280x720"); p.add_argument("--display",default="fit"); p.add_argument("--fps",type=int,default=60); p.add_argument("--bits",type=int,default=32); p.add_argument("--relative-executable"); p.add_argument("--out-dir",type=pathlib.Path,required=True); args=p.parse_args(); ledger=json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger else None
    summary=run(args.install,args.madeira_log,args.unity_log,args.out_dir,config_text=read_text(args.config),arguments=args.arguments,ledger=ledger,storage_root=args.storage_root,registry_text=read_text(args.registry),launch_mode=args.launch_mode,resolution=args.resolution,display=args.display,fps=args.fps,bits=args.bits,relative_executable=args.relative_executable); print(json.dumps(summary,indent=2,sort_keys=True)); return 0 if summary["guard_status"]!="FAIL" and summary["evidence_contract_valid"] else 2
if __name__=="__main__": raise SystemExit(main())
