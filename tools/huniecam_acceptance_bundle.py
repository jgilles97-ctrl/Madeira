#!/usr/bin/env python3
"""Assemble final HunieCam Cycle 7 acceptance evidence in one read-only workflow.

Inputs are existing evidence only: a primary Pipeline V8 directory, filled
run-linked Device Evidence V3 (including three drag/release trials), Save Verify
V2, and at least three sealed Run Context V2 files. The tool derives
Repeatability V3 and Acceptance V9, re-validates Contract V4, and writes a
privacy-minimal Manifest V6. It never launches the game or invents evidence.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import huniecam_acceptance as acceptance_tool
import huniecam_device_evidence as device_tool
import huniecam_evidence_contract as contract_tool
import huniecam_evidence_manifest as manifest_tool
import huniecam_repeatability as repeatability_tool

SCHEMA = "MADEIRA_HUNIECAM_ACCEPTANCE_BUNDLE_V2"

REQUIRED_PRIMARY = {
    "preflight": "huniecam-preflight.json",
    "session": "huniecam-session.json",
    "guard": "huniecam-guard.json",
    "performance": "huniecam-performance.json",
    "run_record": "huniecam-run-record.json",
    "run_context": "huniecam-run-context.json",
    "pe_imports": "huniecam-pe-imports.json",
    "native_modules": "huniecam-native-modules.json",
}

def _load(path:pathlib.Path)->dict[str,Any]:return json.loads(path.read_text(encoding="utf-8"))
def _write(path:pathlib.Path,data:dict[str,Any])->None:path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def run_bundle(primary_dir:pathlib.Path,device_path:pathlib.Path,save_verify_path:pathlib.Path,context_paths:list[pathlib.Path],out_dir:pathlib.Path)->dict[str,Any]:
    out_dir.mkdir(parents=True,exist_ok=True);errors=[];primary_paths={kind:primary_dir/filename for kind,filename in REQUIRED_PRIMARY.items()}
    for kind,path in primary_paths.items():
        if not path.is_file():errors.append(f"Primary pipeline evidence is missing {kind}: {path.name}")
    if errors:
        report={"schema":SCHEMA,"accepted":False,"errors":errors,"rule":"Missing source evidence is never synthesized."};_write(out_dir/"huniecam-final-summary.json",report);return report
    primary={kind:_load(path) for kind,path in primary_paths.items()};raw_device=_load(device_path)
    if isinstance(raw_device.get("normalized"),dict):device_report=raw_device;device_payload=raw_device
    else:device_report=device_tool.summarize(raw_device);device_payload=device_report
    device_out=out_dir/"huniecam-device-evidence-normalized.json";_write(device_out,device_report)
    save_verify=_load(save_verify_path);contexts=[_load(path) for path in context_paths];repeatability=repeatability_tool.analyze(contexts);repeat_path=out_dir/"huniecam-repeatability.json";_write(repeat_path,repeatability)
    initial_contract=contract_tool.validate(primary["preflight"],primary["session"],primary["guard"],primary["performance"],primary["run_record"],run_context=primary["run_context"],pe_imports=primary["pe_imports"],native_modules=primary["native_modules"])
    acceptance=acceptance_tool.evaluate(primary["preflight"],primary["session"],save_verify,device_payload,primary["performance"],initial_contract,primary["run_context"],repeatability);acceptance_path=out_dir/"huniecam-acceptance.json";_write(acceptance_path,acceptance)
    final_contract=contract_tool.validate(primary["preflight"],primary["session"],primary["guard"],primary["performance"],primary["run_record"],acceptance=acceptance,run_context=primary["run_context"],pe_imports=primary["pe_imports"],native_modules=primary["native_modules"]);contract_path=out_dir/"huniecam-final-evidence-contract.json";_write(contract_path,final_contract)
    manifest_inputs={"preflight":primary_paths["preflight"],"session":primary_paths["session"],"guard":primary_paths["guard"],"performance":primary_paths["performance"],"run_record":primary_paths["run_record"],"run_context":primary_paths["run_context"],"pe_imports":primary_paths["pe_imports"],"native_modules":primary_paths["native_modules"],"contract":contract_path,"device_template":device_out,"repeatability":repeat_path,"save_verification":save_verify_path,"acceptance":acceptance_path}
    madeira_log=primary_dir/"madeira-log.txt";unity_log=primary_dir/"output_log.txt"
    if madeira_log.is_file():manifest_inputs["madeira_log"]=madeira_log
    if unity_log.is_file():manifest_inputs["unity_log"]=unity_log
    manifest=manifest_tool.build(manifest_inputs);manifest_path=out_dir/"huniecam-final-manifest.json";_write(manifest_path,manifest)
    final_accepted=bool(acceptance.get("accepted") and final_contract.get("valid") and repeatability.get("passed") and manifest.get("drag_release_evidence_complete"))
    summary={"schema":SCHEMA,"accepted":final_accepted,"acceptance_overall":acceptance.get("overall"),"acceptance_schema":acceptance.get("schema"),"device_evidence_schema":device_report.get("schema"),"primary_run_id_sha256":primary["run_context"].get("run_id_sha256"),"repeatability_passed":repeatability.get("passed"),"repeatability_unique_runs":repeatability.get("unique_run_count"),"final_contract_valid":final_contract.get("valid"),"drag_release_evidence_complete":manifest.get("drag_release_evidence_complete"),"save_verify_schema":save_verify.get("schema"),"next_unproven_gate":acceptance.get("next_unproven_gate"),"outputs":[device_out.name,repeat_path.name,acceptance_path.name,contract_path.name,manifest_path.name,"huniecam-final-summary.json"],"errors":errors,"rule":"Final accepted=true only when current hard acceptance, provenance, three-launch repeatability, exact save persistence and the HunieCam drag-release gate all pass. Missing evidence is never invented."};_write(out_dir/"huniecam-final-summary.json",summary);return summary
def main()->int:
    p=argparse.ArgumentParser(description="Assemble HunieCam Cycle 7 final acceptance bundle");p.add_argument("--primary-dir",type=pathlib.Path,required=True);p.add_argument("--device-evidence",type=pathlib.Path,required=True);p.add_argument("--save-verification",type=pathlib.Path,required=True);p.add_argument("--run-context",dest="contexts",action="append",type=pathlib.Path,required=True,help="Repeat at least three times for distinct cold launches");p.add_argument("--out-dir",type=pathlib.Path,required=True);args=p.parse_args();report=run_bundle(args.primary_dir,args.device_evidence,args.save_verification,args.contexts,args.out_dir);print(json.dumps(report,indent=2,sort_keys=True));return 0 if report.get("accepted") else 2
if __name__=="__main__":raise SystemExit(main())
