#!/usr/bin/env python3
"""Hard acceptance gates for the HunieCam iPad/Madeira port.

Cycle 8 Acceptance V10 keeps the complete sealed evidence chain and closes an
interaction-profile provenance gap: the touch mode that passes real HunieCam
drag/release gameplay must be the same input mode sealed into the primary run
profile and the three-launch repeatability report. Unknown is never pass.
"""
from __future__ import annotations
import argparse, json, pathlib
from typing import Any

SCHEMA="MADEIRA_HUNIECAM_ACCEPTANCE_V10"
DEVICE_SCHEMA="MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3"
TOUCH_INPUT_MODES={"direct_finger","touch_pointer"}
POINTER_POINTS={"top_left","top_center","top_right","middle_left","center","middle_right","bottom_left","bottom_center","bottom_right"}
DRAG_RELEASE_TRIALS=3

def load(path:pathlib.Path|None)->dict[str,Any]|None:return None if path is None else json.loads(path.read_text(encoding="utf-8"))
def _manual_payload(manual):
    if not manual:return None
    n=manual.get("normalized");return n if isinstance(n,dict) else manual
def manual_bool(manual,key):
    p=_manual_payload(manual)
    if not p or key not in p:return None
    v=p[key];return v if isinstance(v,bool) else None
def number(manual,key):
    p=_manual_payload(manual)
    if not p or key not in p:return None
    v=p[key];return None if isinstance(v,bool) or not isinstance(v,(int,float)) else float(v)
def threshold_or_legacy(manual,numeric_key,minimum,legacy_key):
    v=number(manual,numeric_key);return v>=minimum if v is not None else manual_bool(manual,legacy_key)
def pointer_gate(manual):
    p=_manual_payload(manual)
    if p and isinstance(p.get("pointer_grid"),list):
        seen={}
        for item in p["pointer_grid"]:
            if not isinstance(item,dict):continue
            v=item.get("passed");seen[str(item.get("point",""))]=v if isinstance(v,bool) else None
        if not POINTER_POINTS.issubset(seen):return None
        vals=[seen[x] for x in POINTER_POINTS]
        if any(v is False for v in vals):return False
        if any(v is None for v in vals):return None
        return True
    tested=number(p,"pointer_points_tested");passed=number(p,"pointer_points_passed")
    if tested is not None or passed is not None:return None if tested is None or passed is None else tested>=9 and passed==tested
    return manual_bool(p,"pointer_aligned")
def _drag_trial(item):
    if not isinstance(item,dict):return None
    vals=[]
    for key in ("press_registered","movement_registered","release_registered","game_response_registered"):
        v=item.get(key);vals.append(v if isinstance(v,bool) else None)
    if any(v is False for v in vals):return False
    if any(v is None for v in vals):return None
    return True
def accepted_touch_mode(manual):
    p=_manual_payload(manual)
    if not p or p.get("schema")!=DEVICE_SCHEMA:return None
    rows=p.get("drag_release_trials") if isinstance(p.get("drag_release_trials"),list) else []
    if len(rows)<DRAG_RELEASE_TRIALS:return None
    rows=rows[:DRAG_RELEASE_TRIALS];vals=[_drag_trial(x) for x in rows]
    if not all(v is True for v in vals):return None
    modes=[x.get("input_mode") if isinstance(x,dict) else None for x in rows]
    if any(m is None for m in modes) or len(set(modes))!=1:return None
    return modes[0] if modes[0] in TOUCH_INPUT_MODES else None
def drag_release_gate(manual):
    p=_manual_payload(manual)
    if not p or p.get("schema")!=DEVICE_SCHEMA:return None
    rows=p.get("drag_release_trials") if isinstance(p.get("drag_release_trials"),list) else []
    if len(rows)<DRAG_RELEASE_TRIALS:return None
    rows=rows[:DRAG_RELEASE_TRIALS];vals=[_drag_trial(x) for x in rows]
    if any(v is False for v in vals):return False
    if any(v is None for v in vals):return None
    modes=[x.get("input_mode") if isinstance(x,dict) else None for x in rows]
    if any(m is None for m in modes):return None
    return len(set(modes))==1 and modes[0] in TOUCH_INPUT_MODES
def trial_gate(manual,list_key,minimum,numeric_key,legacy_key):
    p=_manual_payload(manual)
    if p and isinstance(p.get(list_key),list):
        vals=[]
        for item in p[list_key]:
            if not isinstance(item,dict):continue
            v=item.get("success");vals.append(v if isinstance(v,bool) else None)
        if len(vals)<minimum:return None
        vals=vals[:minimum]
        if any(v is False for v in vals):return False
        if any(v is None for v in vals):return None
        return True
    return threshold_or_legacy(p,numeric_key,minimum,legacy_key)
def context_gate(ctx):
    if ctx is None:return None
    required=("run_id_sha256","guard_sha256","performance_sha256","pe_imports_sha256","native_modules_sha256","native_module_set_sha256","input_mode")
    return bool(ctx.get("schema")=="MADEIRA_HUNIECAM_RUN_CONTEXT_V2" and ctx.get("ready") and all(ctx.get(k) for k in required))
def device_schema_gate(manual):
    p=_manual_payload(manual)
    if p is None:return None
    return p.get("schema")==DEVICE_SCHEMA
def device_run_link(manual,ctx):
    p=_manual_payload(manual)
    if not p or not ctx:return None
    expected=(ctx.get("run_id_sha256"),ctx.get("build_fingerprint_sha256"),ctx.get("profile_sha256"));observed=(p.get("run_id_sha256"),p.get("build_fingerprint_sha256"),p.get("profile_sha256"))
    if any(not x for x in expected) or any(not x for x in observed):return None
    return observed==expected
def input_mode_provenance_gate(manual,ctx,rep):
    if not manual or not ctx or not rep:return None
    device_mode=accepted_touch_mode(manual);context_mode=ctx.get("input_mode");repeat_mode=rep.get("input_mode")
    if not device_mode or not context_mode or not repeat_mode:return None
    return device_mode==context_mode==repeat_mode and device_mode in TOUCH_INPUT_MODES
def save_v2_gate(save):
    if save is None:return None
    return bool(save.get("schema")=="MADEIRA_HUNIECAM_SAVE_VERIFY_V2" and save.get("same_source_directory_proven") and save.get("expected_save_folder_proven") and save.get("machine_gate_pass") and not save.get("errors"))
def repeatability_gate(rep,ctx):
    if not rep or not ctx:return None
    if rep.get("schema")!="MADEIRA_HUNIECAM_REPEATABILITY_V3" or not rep.get("passed"):return False
    if rep.get("build_fingerprint_sha256")!=ctx.get("build_fingerprint_sha256") or rep.get("profile_sha256")!=ctx.get("profile_sha256") or rep.get("native_module_set_sha256")!=ctx.get("native_module_set_sha256") or rep.get("input_mode")!=ctx.get("input_mode"):return False
    runs=rep.get("runs") if isinstance(rep.get("runs"),list) else [];ids={r.get("run_id_sha256") for r in runs if isinstance(r,dict) and r.get("run_id_sha256")};primary=ctx.get("run_id_sha256")
    return None if not primary else primary in ids and len(ids)>=3
def gate(name,value,evidence):return {"name":name,"status":"PASS" if value is True else "FAIL" if value is False else "UNKNOWN","required":True,"evidence":evidence}
def evaluate(preflight,session,save_verification,manual,performance=None,evidence_contract=None,run_context=None,repeatability=None):
    gates=[];owned=None
    if preflight:
        pe=preflight.get("identity",{}).get("pe",{});owned=bool(preflight.get("exe_found")) and bool(pe.get("valid_pe")) and bool(preflight.get("identity",{}).get("exe_sha256"))
    gates.append(gate("owned_game_identity",owned,"Preflight proved a real owned Windows PE executable and SHA-256."));gates.append(gate("evidence_contract_valid",None if evidence_contract is None else bool(evidence_contract.get("valid") and evidence_contract.get("schema")=="MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4" and evidence_contract.get("run_context_v2_complete")),"Contract V4 must validate the fully sealed primary launch."));gates.append(gate("run_context_v2_ready",context_gate(run_context),"Context V2 must seal guard, performance, dependency evidence and the selected input mode."));gates.append(gate("device_evidence_v3_current",device_schema_gate(manual),"Final acceptance requires current Device Evidence V3."));gates.append(gate("device_evidence_same_run",device_run_link(manual,run_context),"Primary device observations must carry the same run ID/build/profile."));gates.append(gate("input_mode_provenance",input_mode_provenance_gate(manual,run_context,repeatability),"The touch mode that passed gameplay must equal the input mode sealed in the primary run and all three repeatability contexts."));gates.append(gate("jit_and_memory_ready",manual_bool(manual,"jit_memory_ready"),"JIT and Memory+ were ready before launch."))
    stage=int(session.get("deepest_stage",0)) if session else 0;gates.append(gate("windows_launch",stage>=20 if session else None,"Windows executable stage reached."));gates.append(gate("game_managed_code",stage>=65 if session else None,"Game managed-code stage reached."));gates.append(gate("real_gameplay",manual_bool(manual,"real_gameplay"),"Real management gameplay was interactive."));gates.append(gate("rendering_correct",manual_bool(manual,"rendering_correct"),"Text/sprites/panels/effects rendered correctly."));gates.append(gate("pointer_grid",pointer_gate(manual),"All nine pointer targets passed."));gates.append(gate("drag_release_gameplay",drag_release_gate(manual),"Three real gameplay drags must each prove press, movement, release and game response using the same finger-based Madeira mode."));gates.append(gate("audio_correct",manual_bool(manual,"audio_correct"),"Music/effects were present and stable."))
    write=persist=machine=None
    if save_verification:
        if "progress_write_detected" in save_verification:write=bool(save_verification.get("progress_write_detected"))
        if "save_tree_survived_relaunch" in save_verification:persist=bool(save_verification.get("save_tree_survived_relaunch"))
        if "machine_gate_pass" in save_verification:machine=bool(save_verification.get("machine_gate_pass"))
    gates.append(gate("save_write_detected",write,"BEFORE→AFTER save tree changed."));gates.append(gate("save_survives_relaunch",persist,"Post-progress save tree survived relaunch."));gates.append(gate("save_verify_v2_exact_folder",save_v2_gate(save_verification),"Save Verify V2 proves one exact expected HunieCam save folder."));gates.append(gate("save_machine_verification",machine,"Machine save gate passed."));gates.append(gate("save_progress_visible_after_relaunch",manual_bool(manual,"save_progress_visible_after_relaunch"),"Relaunched game visibly restored progress."))
    clean=None if performance is None else bool(performance.get("comparison_clean"));gates.append(gate("performance_measurement_clean",clean,"Measured performance proved cap/device state."));gates.append(gate("performance_acceptable",manual_bool(manual,"performance_acceptable"),"Busy play remained acceptably responsive."));gates.append(gate("stable_30_minutes",threshold_or_legacy(manual,"stable_minutes",30,"stable_30_minutes"),">=30 stable minutes."));gates.append(gate("three_cold_launches_observed",trial_gate(manual,"cold_launch_trials",3,"cold_launches","three_cold_launches"),"Three cold launches were visibly successful."));gates.append(gate("three_sealed_cold_launches",repeatability_gate(repeatability,run_context),"Repeatability V3 proves >=3 unique Context V2 runs on identical build/profile/native modules and input mode, including primary."));gates.append(gate("two_suspend_resume_cycles",trial_gate(manual,"suspend_resume_trials",2,"suspend_resume_cycles","two_suspend_resume_cycles"),"Two suspend/resume cycles succeeded."));gates.append(gate("repeatable_profile",manual_bool(manual,"repeatable_profile"),"Documented final profile reproduced from a clean Madeira start."))
    counts={s:sum(1 for g in gates if g["status"]==s) for s in ("PASS","FAIL","UNKNOWN")};complete=counts["FAIL"]==0 and counts["UNKNOWN"]==0;overall="NOT_READY_FAILED_GATE" if counts["FAIL"] else "NOT_READY_MISSING_EVIDENCE" if counts["UNKNOWN"] else "ACCEPTED";next_gate=next((g for g in gates if g["status"]!="PASS"),None);touch_mode=accepted_touch_mode(manual)
    return {"schema":SCHEMA,"overall":overall,"accepted":complete,"run_id_sha256":run_context.get("run_id_sha256") if run_context else None,"accepted_touch_mode":touch_mode if complete else None,"sealed_input_mode":run_context.get("input_mode") if run_context else None,"counts":counts,"next_unproven_gate":next_gate,"gates":gates,"thresholds":{"pointer_points":9,"drag_release_trials":DRAG_RELEASE_TRIALS,"drag_release_touch_modes":sorted(TOUCH_INPUT_MODES),"stable_minutes":30,"cold_launches":3,"sealed_cold_launches":3,"suspend_resume_cycles":2},"rule":"Unknown is never pass. Final acceptance requires the exact touch mode proven by real gameplay to match the input mode sealed into the primary run profile and all three repeatable launches."}
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--preflight",type=pathlib.Path);p.add_argument("--session",type=pathlib.Path);p.add_argument("--save-verification",type=pathlib.Path);p.add_argument("--manual",type=pathlib.Path);p.add_argument("--performance",type=pathlib.Path);p.add_argument("--evidence-contract",type=pathlib.Path);p.add_argument("--run-context",type=pathlib.Path);p.add_argument("--repeatability",type=pathlib.Path);p.add_argument("--json",dest="json_path",type=pathlib.Path);args=p.parse_args();report=evaluate(load(args.preflight),load(args.session),load(args.save_verification),load(args.manual),load(args.performance),load(args.evidence_contract),load(args.run_context),load(args.repeatability));text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path:args.json_path.write_text(text+"\n",encoding="utf-8")
    print(text);return 0 if report["accepted"] else 2
if __name__=="__main__":raise SystemExit(main())
