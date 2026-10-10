#!/usr/bin/env python3
"""Generate and normalize structured on-device evidence for HunieCam acceptance.

Device Evidence V3 includes the title-specific drag/release test. Cycle 8 now
prefills every drag trial from the input mode sealed in Run Context V2 so a user
cannot accidentally record touch observations under a different interaction
profile. Unknown observations remain null; hardware pointer remains diagnostic.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA="MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3"
POINTER_POINTS=("top_left","top_center","top_right","middle_left","center","middle_right","bottom_left","bottom_center","bottom_right")
DRAG_RELEASE_TRIALS=3
TOUCH_INPUT_MODES={"direct_finger","touch_pointer"}
DIAGNOSTIC_INPUT_MODES=TOUCH_INPUT_MODES|{"hardware_mouse","hardware_trackpad"}

def _link(run_context:dict[str,Any]|None)->dict[str,Any]:
    context=run_context or {};ready=bool(context.get("ready") and context.get("run_id_sha256"));return {"run_id_sha256":context.get("run_id_sha256") if ready else None,"build_fingerprint_sha256":context.get("build_fingerprint_sha256") if ready else None,"profile_sha256":context.get("profile_sha256") if ready else None,"sealed_input_mode":context.get("input_mode") if ready and context.get("input_mode") in DIAGNOSTIC_INPUT_MODES else None}
def template(run_context:dict[str,Any]|None=None)->dict[str,Any]:
    link=_link(run_context);sealed_mode=link.get("sealed_input_mode")
    return {"schema":SCHEMA,**link,"jit_memory_ready":None,"real_gameplay":None,"rendering_correct":None,"audio_correct":None,"save_progress_visible_after_relaunch":None,"performance_acceptable":None,"repeatable_profile":None,"stable_minutes":0,"pointer_grid":[{"point":point,"passed":None,"note":""} for point in POINTER_POINTS],"drag_release_trials":[{"trial":i,"input_mode":sealed_mode,"press_registered":None,"movement_registered":None,"release_registered":None,"game_response_registered":None,"note":""} for i in range(1,DRAG_RELEASE_TRIALS+1)],"cold_launch_trials":[{"trial":1,"success":None,"note":""},{"trial":2,"success":None,"note":""},{"trial":3,"success":None,"note":""}],"suspend_resume_trials":[{"trial":1,"success":None,"note":""},{"trial":2,"success":None,"note":""}],"gameplay_notes":"","drag_release_notes":"","rendering_notes":"","audio_notes":"","performance_notes":"","rule":"This form is bound to one sealed run. Its drag input_mode is prefilled from that run and should not be changed in-place; testing another mode requires a separate Pipeline V9 run/context. Use true/false only after observing the iPad result. Hardware mouse/trackpad is diagnostic only."}
def _bool(value:Any)->bool|None:return value if isinstance(value,bool) else None
def _drag_trial_state(item:dict[str,Any])->bool|None:
    values=[_bool(item.get("press_registered")),_bool(item.get("movement_registered")),_bool(item.get("release_registered")),_bool(item.get("game_response_registered"))]
    if any(v is False for v in values):return False
    if any(v is None for v in values):return None
    return True
def _drag_mode(item:dict[str,Any])->str|None:
    value=item.get("input_mode");return value if isinstance(value,str) and value in DIAGNOSTIC_INPUT_MODES else None
def summarize(data:dict[str,Any])->dict[str,Any]:
    warnings=[]
    if data.get("schema") not in {"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V1","MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V2",SCHEMA}:warnings.append(f"Unexpected device-evidence schema: {data.get('schema')!r}")
    points=data.get("pointer_grid") if isinstance(data.get("pointer_grid"),list) else [];point_map={};duplicates=set()
    for item in points:
        if not isinstance(item,dict):continue
        name=str(item.get("point",""));
        if name in point_map:duplicates.add(name)
        point_map[name]=_bool(item.get("passed"))
    missing=[p for p in POINTER_POINTS if p not in point_map];unknown=[p for p in POINTER_POINTS if point_map.get(p) is None];failed=[p for p in POINTER_POINTS if point_map.get(p) is False];passed=[p for p in POINTER_POINTS if point_map.get(p) is True]
    if duplicates:warnings.append("Duplicate pointer-grid point(s): "+", ".join(sorted(duplicates)))
    if missing:warnings.append("Missing pointer-grid point(s): "+", ".join(missing))
    drag_rows=[x for x in (data.get("drag_release_trials") if isinstance(data.get("drag_release_trials"),list) else []) if isinstance(x,dict)];drag_states=[_drag_trial_state(x) for x in drag_rows];drag_modes=[_drag_mode(x) for x in drag_rows];drag_tested=sum(1 for x in drag_states if x is not None);drag_passed=sum(1 for x in drag_states if x is True);required_states=drag_states[:DRAG_RELEASE_TRIALS];required_modes=drag_modes[:DRAG_RELEASE_TRIALS];one_touch_mode=len(required_modes)>=DRAG_RELEASE_TRIALS and None not in required_modes and len(set(required_modes))==1 and required_modes[0] in TOUCH_INPUT_MODES;drag_complete=len(required_states)>=DRAG_RELEASE_TRIALS and all(x is True for x in required_states) and one_touch_mode;modes_seen=sorted({x for x in drag_modes if x});sealed_mode=data.get("sealed_input_mode") if isinstance(data.get("sealed_input_mode"),str) else None
    if sealed_mode and any(mode is not None and mode!=sealed_mode for mode in required_modes):warnings.append("One or more drag trials use an input mode different from the run-linked sealed_input_mode. Do not edit the form to switch modes; generate a separate Pipeline V9 run for that A/B.")
    if len(required_states)>=DRAG_RELEASE_TRIALS and all(x is True for x in required_states) and not one_touch_mode:warnings.append("Drag/release mechanics passed, but the first three trials do not prove one consistent finger-based Madeira mode. Hardware mouse/trackpad or mixed modes cannot satisfy touch-first acceptance.")
    if data.get("schema")!=SCHEMA:warnings.append("Legacy device evidence does not prove the current HunieCam drag-release gate.")
    cold=data.get("cold_launch_trials") if isinstance(data.get("cold_launch_trials"),list) else [];cold_values=[_bool(x.get("success")) for x in cold if isinstance(x,dict)];suspend=data.get("suspend_resume_trials") if isinstance(data.get("suspend_resume_trials"),list) else [];suspend_values=[_bool(x.get("success")) for x in suspend if isinstance(x,dict)]
    normalized=dict(data);normalized["schema"]=SCHEMA;normalized["pointer_points_tested"]=len(passed)+len(failed);normalized["pointer_points_passed"]=len(passed);normalized["drag_release_trials_tested"]=drag_tested;normalized["drag_release_trials_passed"]=drag_passed;normalized["drag_release_input_modes_seen"]=modes_seen;normalized["drag_release_touch_mode"]=required_modes[0] if drag_complete else None;normalized["cold_launches"]=sum(1 for x in cold_values if x is True);normalized["suspend_resume_cycles"]=sum(1 for x in suspend_values if x is True)
    complete_pointer=not missing and not unknown and not failed and len(passed)==len(POINTER_POINTS);cold_complete=len(cold_values)>=3 and all(x is True for x in cold_values[:3]);suspend_complete=len(suspend_values)>=2 and all(x is True for x in suspend_values[:2]);run_link_ready=all(bool(normalized.get(k)) for k in ("run_id_sha256","build_fingerprint_sha256","profile_sha256"));mode_link_ready=bool(sealed_mode and len(required_modes)>=DRAG_RELEASE_TRIALS and all(mode==sealed_mode for mode in required_modes))
    if not run_link_ready:warnings.append("Device observations are not linked to a sealed run ID/build/profile; final acceptance must remain unproven.")
    if sealed_mode and not mode_link_ready:warnings.append("Device drag trials are not consistently bound to the sealed run input mode.")
    return {"schema":SCHEMA,"normalized":normalized,"derived":{"pointer_grid_complete":complete_pointer,"pointer_missing":missing,"pointer_unknown":unknown,"pointer_failed":failed,"drag_release_trials_complete":drag_complete,"drag_release_trials_tested":drag_tested,"drag_release_trials_passed":drag_passed,"drag_release_input_modes_seen":modes_seen,"drag_release_touch_mode":required_modes[0] if drag_complete else None,"sealed_input_mode":sealed_mode,"input_mode_link_ready":mode_link_ready,"cold_launch_trials_complete":cold_complete,"suspend_resume_trials_complete":suspend_complete,"run_link_ready":run_link_ready},"warnings":warnings,"rule":"Structured trial details are authoritative. A mode switch is a separate sealed run, never an edit to this run-linked form. Final touch acceptance requires three real HunieCam gameplay drags in one consistent finger-based mode matching the sealed profile."}
def _load(path:pathlib.Path|None)->dict[str,Any]|None:return json.loads(path.read_text(encoding="utf-8")) if path else None
def main()->int:
    p=argparse.ArgumentParser(description="Generate/normalize HunieCam iPad device evidence");sub=p.add_subparsers(dest="command",required=True);make=sub.add_parser("template");make.add_argument("--run-context",type=pathlib.Path);make.add_argument("--json",dest="json_path",type=pathlib.Path);norm=sub.add_parser("normalize");norm.add_argument("input",type=pathlib.Path);norm.add_argument("--json",dest="json_path",type=pathlib.Path);args=p.parse_args();report=template(_load(args.run_context)) if args.command=="template" else summarize(json.loads(args.input.read_text(encoding="utf-8")));text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path:args.json_path.write_text(text+"\n",encoding="utf-8")
    print(text);return 0
if __name__=="__main__":raise SystemExit(main())
