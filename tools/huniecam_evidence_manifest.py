#!/usr/bin/env python3
"""Create a privacy-minimal manifest for one HunieCam/Madeira evidence set.

Manifest V6 records the fully sealed launch, dependency audits, run-linked
Device Evidence V3 including the HunieCam drag/release touch gate, current
repeatability/save evidence, and final Acceptance V9. Raw logs, saves, binaries
and credentials are never embedded in the manifest body.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib
from typing import Any

SCHEMA="MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V6"
TOUCH_INPUT_MODES={"direct_finger","touch_pointer"}

def sha256(path:pathlib.Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def descriptor(path:pathlib.Path|None,kind:str)->dict[str,Any]|None:
    if path is None:return None
    st=path.stat();return {"kind":kind,"name":path.name,"bytes":st.st_size,"sha256":sha256(path)}
def load_json(path:pathlib.Path|None)->dict[str,Any]|None:return None if path is None else json.loads(path.read_text(encoding="utf-8"))
def _drag_state(item:dict[str,Any])->bool|None:
    vals=[]
    for key in ("press_registered","movement_registered","release_registered","game_response_registered"):
        v=item.get(key);vals.append(v if isinstance(v,bool) else None)
    if any(v is False for v in vals):return False
    if any(v is None for v in vals):return None
    return True
def _drag_summary(payload:dict[str,Any])->dict[str,Any]:
    rows=[x for x in (payload.get("drag_release_trials") if isinstance(payload.get("drag_release_trials"),list) else []) if isinstance(x,dict)];vals=[_drag_state(x) for x in rows];modes=[x.get("input_mode") if isinstance(x.get("input_mode"),str) else None for x in rows];required_vals=vals[:3];required_modes=modes[:3];one_touch_mode=len(required_modes)>=3 and None not in required_modes and len(set(required_modes))==1 and required_modes[0] in TOUCH_INPUT_MODES;complete=len(required_vals)>=3 and all(x is True for x in required_vals) and one_touch_mode
    return {"drag_release_trials_tested":sum(1 for x in vals if x is not None),"drag_release_trials_passed":sum(1 for x in vals if x is True),"drag_release_input_modes_seen":sorted({x for x in modes if x}),"drag_release_touch_mode":required_modes[0] if complete else None,"drag_release_trials_complete":complete}
def summary(kind:str,data:dict[str,Any]|None)->dict[str,Any]|None:
    if data is None:return None
    if kind=="preflight":
        ident=data.get("identity",{});runtime=data.get("runtime_signals",{});return {"schema":data.get("schema"),"exe_found":data.get("exe_found"),"exe_sha256":ident.get("exe_sha256"),"architecture":ident.get("pe",{}).get("architecture") if isinstance(ident.get("pe"),dict) else None,"runtime_family":runtime.get("runtime_family"),"unity_versions_seen":runtime.get("unity_versions_seen"),"depot_shape":data.get("depot_shape")}
    if kind=="session":return {"schema":data.get("schema"),"deepest_stage":data.get("deepest_stage"),"deepest_stage_name":data.get("deepest_stage_name"),"marker_codes":[m.get("code") for m in data.get("markers",[])],"failure_codes":[f.get("code") for f in data.get("failures",[])],"next_priority":data.get("next",{}).get("priority") if isinstance(data.get("next"),dict) else None}
    if kind=="guard":return {"schema":data.get("schema"),"status":data.get("status"),"experiment":data.get("experiment"),"changes":data.get("changes")}
    if kind=="issues":return {"schema":data.get("schema"),"best_match":data.get("best_match"),"explicit_nonmatches":data.get("explicit_nonmatches")}
    if kind=="ledger":
        attempts=data.get("attempts",[]);return {"schema":data.get("schema"),"attempt_count":len(attempts),"best_stage":data.get("best_stage"),"best_attempt":data.get("best_attempt")}
    if kind=="run_record":
        build=data.get("build") if isinstance(data.get("build"),dict) else {};return {"schema":data.get("schema"),"ready_for_comparison":data.get("ready_for_comparison"),"build_fingerprint_sha256":build.get("fingerprint_sha256"),"profile_sha256":data.get("profile_sha256")}
    if kind=="run_context":return {"schema":data.get("schema"),"ready":data.get("ready"),"run_id_sha256":data.get("run_id_sha256"),"build_fingerprint_sha256":data.get("build_fingerprint_sha256"),"profile_sha256":data.get("profile_sha256"),"native_module_set_sha256":data.get("native_module_set_sha256"),"session_summary":data.get("session_summary")}
    if kind=="pe_imports":return {"schema":data.get("schema"),"valid":data.get("valid"),"file_sha256":data.get("file_sha256"),"import_count":data.get("import_count"),"categories":sorted((data.get("categories") or {}).keys()) if isinstance(data.get("categories"),dict) else []}
    if kind=="native_modules":return {"schema":data.get("schema"),"valid":data.get("valid"),"module_count":data.get("module_count"),"valid_module_count":data.get("valid_module_count"),"module_set_sha256":data.get("module_set_sha256")}
    if kind=="contract":return {"schema":data.get("schema"),"valid":data.get("valid"),"run_id_sha256":data.get("run_id_sha256"),"run_context_v2_complete":data.get("run_context_v2_complete"),"errors":data.get("errors"),"warnings":data.get("warnings")}
    if kind=="device_template":
        payload=data.get("normalized") if isinstance(data.get("normalized"),dict) else data;return {"schema":payload.get("schema",data.get("schema")),"run_id_sha256":payload.get("run_id_sha256"),"build_fingerprint_sha256":payload.get("build_fingerprint_sha256"),"profile_sha256":payload.get("profile_sha256"),**_drag_summary(payload)}
    if kind=="repeatability":return {"schema":data.get("schema"),"passed":data.get("passed"),"run_count":data.get("run_count"),"unique_run_count":data.get("unique_run_count"),"build_fingerprint_sha256":data.get("build_fingerprint_sha256"),"profile_sha256":data.get("profile_sha256"),"native_module_set_sha256":data.get("native_module_set_sha256")}
    if kind=="save_verification":return {"schema":data.get("schema"),"progress_write_detected":data.get("progress_write_detected"),"save_tree_survived_relaunch":data.get("save_tree_survived_relaunch"),"same_source_directory_proven":data.get("same_source_directory_proven"),"expected_save_folder_proven":data.get("expected_save_folder_proven"),"machine_gate_pass":data.get("machine_gate_pass"),"after_tree_sha256":data.get("after_tree_sha256"),"relaunch_tree_sha256":data.get("relaunch_tree_sha256")}
    if kind.startswith("save"):return {"schema":data.get("schema"),"tree_sha256":data.get("tree_sha256"),"file_count":data.get("file_count"),"progress_write_detected":data.get("progress_write_detected")}
    if kind=="acceptance":return {"schema":data.get("schema"),"overall":data.get("overall"),"accepted":data.get("accepted"),"counts":data.get("counts"),"next_unproven_gate":data.get("next_unproven_gate"),"run_id_sha256":data.get("run_id_sha256")}
    return {"schema":data.get("schema")}
def build(inputs:dict[str,pathlib.Path|None])->dict[str,Any]:
    structured={"preflight","session","guard","issues","ledger","run_record","run_context","pe_imports","native_modules","contract","device_template","repeatability","save_before","save_after","save_relaunch","save_verification","acceptance"};files=[];summaries={}
    for kind,path in inputs.items():
        if path is None:continue
        files.append(descriptor(path,kind))
        if kind in structured:summaries[kind]=summary(kind,load_json(path))
    present={f["kind"] for f in files};pre=summaries.get("preflight") or {};context=summaries.get("run_context") or {};contract=summaries.get("contract") or {};imports=summaries.get("pe_imports") or {};native=summaries.get("native_modules") or {};device=summaries.get("device_template") or {};repeat=summaries.get("repeatability") or {};save_verify=summaries.get("save_verification") or {};acceptance=summaries.get("acceptance") or {}
    minimum_review={"preflight","session"}.issubset(present) and ("madeira_log" in present or bool(context.get("run_id_sha256")));sealed=bool(context.get("schema")=="MADEIRA_HUNIECAM_RUN_CONTEXT_V2" and context.get("ready") and context.get("run_id_sha256") and contract.get("schema")=="MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4" and contract.get("valid") and contract.get("run_context_v2_complete") and contract.get("run_id_sha256")==context.get("run_id_sha256"));dependency=bool(imports.get("valid") and imports.get("file_sha256") and imports.get("file_sha256")==pre.get("exe_sha256"));native_ok=bool(native.get("valid") and native.get("module_set_sha256") and native.get("module_set_sha256")==context.get("native_module_set_sha256"));device_linked=bool(device.get("schema")=="MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3" and device.get("run_id_sha256") and device.get("run_id_sha256")==context.get("run_id_sha256") and device.get("build_fingerprint_sha256")==context.get("build_fingerprint_sha256") and device.get("profile_sha256")==context.get("profile_sha256"));drag_complete=bool(device_linked and device.get("drag_release_trials_complete"));repeat_ok=bool(repeat.get("schema")=="MADEIRA_HUNIECAM_REPEATABILITY_V3" and repeat.get("passed") and int(repeat.get("unique_run_count") or 0)>=3 and repeat.get("build_fingerprint_sha256")==context.get("build_fingerprint_sha256") and repeat.get("profile_sha256")==context.get("profile_sha256") and repeat.get("native_module_set_sha256")==context.get("native_module_set_sha256"));save_ok=bool(save_verify.get("schema")=="MADEIRA_HUNIECAM_SAVE_VERIFY_V2" and save_verify.get("same_source_directory_proven") and save_verify.get("expected_save_folder_proven") and save_verify.get("machine_gate_pass"));acceptance_ok=bool(acceptance.get("schema")=="MADEIRA_HUNIECAM_ACCEPTANCE_V9" and acceptance.get("accepted") and acceptance.get("run_id_sha256")==context.get("run_id_sha256"))
    warnings=[];guard=summaries.get("guard") or {};session=summaries.get("session") or {}
    if guard.get("status")=="FAIL":warnings.append("The config guard rejected this run profile; do not promote it as valid evidence.")
    if pre and not pre.get("exe_sha256"):warnings.append("Preflight lacks executable SHA-256 identity.")
    if session and not session.get("deepest_stage") and "madeira_log" in present:warnings.append("Madeira evidence is present but the structured session proves no game stage.")
    if "run_context" in present and not sealed:warnings.append("Primary launch is not fully sealed to current Contract V4/Context V2 evidence.")
    if "pe_imports" in present and not dependency:warnings.append("PE dependency audit does not validate against the owned executable identity.")
    if "native_modules" in present and not native_ok:warnings.append("Native-module audit does not match the primary run's sealed native-module-set fingerprint.")
    if "device_template" in present and not device_linked:warnings.append("Device evidence is not current V3 or is not linked to the sealed primary launch identity.")
    if "device_template" in present and device_linked and not drag_complete:warnings.append("Current device evidence does not prove three successful HunieCam gameplay drag/releases in one consistent finger-based Madeira mode.")
    if "repeatability" in present and not repeat_ok:warnings.append("Repeatability does not prove three unique current Context V2 launches on the same build/profile/native-module set.")
    if "save_verification" in present and not save_ok:warnings.append("Save evidence does not satisfy current exact-folder Save Verify V2.")
    if "acceptance" in present and acceptance.get("accepted") and not acceptance_ok:warnings.append("Acceptance claims success but does not match current Acceptance V9 primary-run requirements.")
    return {"schema":SCHEMA,"title":"HunieCam Studio","steam_app_id":426000,"files":sorted(files,key=lambda x:x["kind"]),"summaries":summaries,"minimum_review_bundle_complete":minimum_review,"sealed_launch_identity_complete":sealed,"pe_dependency_audit_complete":dependency,"native_module_audit_complete":native_ok,"device_template_linked_to_primary_run":device_linked,"drag_release_evidence_complete":drag_complete,"cold_launch_repeatability_complete":repeat_ok,"save_machine_verification_complete":save_ok,"device_acceptance_complete":acceptance_ok,"integrity_warnings":warnings,"privacy":{"raw_logs_embedded":False,"save_contents_embedded":False,"absolute_paths_embedded":False,"credentials_embedded":False,"proprietary_binaries_embedded":False},"rule":"Final Cycle 7 manifest completion requires current sealed formats, three successful gameplay drag/releases in one consistent finger-based Madeira mode, exact save persistence and three distinct cold launches. Missing evidence is never inferred."}
def main()->int:
    p=argparse.ArgumentParser(description="Build a HunieCam/Madeira evidence manifest")
    for name in ("preflight","session","guard","issues","ledger","run-record","run-context","pe-imports","native-modules","contract","device-template","repeatability","save-before","save-after","save-relaunch","save-verification","acceptance","madeira-log","unity-log"):p.add_argument(f"--{name}",dest=name.replace("-","_"),type=pathlib.Path)
    p.add_argument("--json",dest="json_path",type=pathlib.Path,required=True);args=p.parse_args();inputs={"preflight":args.preflight,"session":args.session,"guard":args.guard,"issues":args.issues,"ledger":args.ledger,"run_record":args.run_record,"run_context":args.run_context,"pe_imports":args.pe_imports,"native_modules":args.native_modules,"contract":args.contract,"device_template":args.device_template,"repeatability":args.repeatability,"save_before":args.save_before,"save_after":args.save_after,"save_relaunch":args.save_relaunch,"save_verification":args.save_verification,"acceptance":args.acceptance,"madeira_log":args.madeira_log,"unity_log":args.unity_log};report=build(inputs);args.json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(report,indent=2,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
