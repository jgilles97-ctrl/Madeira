#!/usr/bin/env python3
"""Fail fast when HunieCam evidence-tool schemas or input-mode contracts drift.

Cycle 8 tracks Pipeline V9, Acceptance V10, Manifest V7, Acceptance Bundle V4,
Runtime Bundle Audit V1, and Attempt Ledger V4. It also verifies that the
producer, run-profile, pipeline, acceptance and manifest all agree on the same
touch/diagnostic input-mode vocabulary.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import huniecam_acceptance as acceptance
import huniecam_acceptance_bundle as acceptance_bundle
import huniecam_attempt_ledger as attempt_ledger
import huniecam_config_guard as config_guard
import huniecam_device_evidence as device_evidence
import huniecam_evidence_contract as evidence_contract
import huniecam_evidence_manifest as evidence_manifest
import huniecam_native_modules as native_modules
import huniecam_pe_imports as pe_imports
import huniecam_performance as performance
import huniecam_pipeline as pipeline
import huniecam_probe as probe
import huniecam_repeatability as repeatability
import huniecam_run_context as run_context
import huniecam_run_record as run_record
import huniecam_runtime_bundle_audit as runtime_bundle_audit
import huniecam_save_probe as save_probe
import huniecam_session_triage as session_triage

SCHEMA = "MADEIRA_HUNIECAM_SCHEMA_AUDIT_V2"
CURRENT = {
    "preflight": probe.SCHEMA,
    "session": session_triage.SCHEMA,
    "guard": config_guard.SCHEMA,
    "performance": performance.SCHEMA,
    "run_record": run_record.SCHEMA,
    "run_context": run_context.SCHEMA,
    "pe_imports": pe_imports.SCHEMA,
    "native_modules": native_modules.SCHEMA,
    "runtime_bundle": runtime_bundle_audit.SCHEMA,
    "attempt_ledger": attempt_ledger.SCHEMA,
    "device_evidence": device_evidence.SCHEMA,
    "save_snapshot": save_probe.SNAPSHOT_SCHEMA,
    "save_compare": save_probe.COMPARE_SCHEMA,
    "save_verify": save_probe.VERIFY_SCHEMA,
    "repeatability": repeatability.SCHEMA,
    "contract": evidence_contract.SCHEMA,
    "acceptance": acceptance.SCHEMA,
    "manifest": evidence_manifest.SCHEMA,
    "pipeline": pipeline.SCHEMA,
    "acceptance_bundle": acceptance_bundle.SCHEMA,
}
EXPECTED_CURRENT = {
    "preflight": "MADEIRA_HUNIECAM_PROBE_V4",
    "session": "MADEIRA_HUNIECAM_SESSION_V3",
    "guard": "MADEIRA_HUNIECAM_CONFIG_GUARD_V2",
    "performance": "MADEIRA_HUNIECAM_PERFORMANCE_V2",
    "run_record": "MADEIRA_HUNIECAM_RUN_RECORD_V1",
    "run_context": "MADEIRA_HUNIECAM_RUN_CONTEXT_V2",
    "pe_imports": "MADEIRA_HUNIECAM_PE_IMPORTS_V1",
    "native_modules": "MADEIRA_HUNIECAM_NATIVE_MODULES_V1",
    "runtime_bundle": "MADEIRA_HUNIECAM_RUNTIME_BUNDLE_AUDIT_V1",
    "attempt_ledger": "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V4",
    "device_evidence": "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3",
    "save_snapshot": "MADEIRA_HUNIECAM_SAVE_SNAPSHOT_V2",
    "save_compare": "MADEIRA_HUNIECAM_SAVE_COMPARE_V2",
    "save_verify": "MADEIRA_HUNIECAM_SAVE_VERIFY_V2",
    "repeatability": "MADEIRA_HUNIECAM_REPEATABILITY_V3",
    "contract": "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4",
    "acceptance": "MADEIRA_HUNIECAM_ACCEPTANCE_V10",
    "manifest": "MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V7",
    "pipeline": "MADEIRA_HUNIECAM_PIPELINE_V9",
    "acceptance_bundle": "MADEIRA_HUNIECAM_ACCEPTANCE_BUNDLE_V4",
}

def audit() -> dict[str, Any]:
    errors=[]
    for name,expected in EXPECTED_CURRENT.items():
        actual=CURRENT.get(name)
        if actual!=expected:errors.append(f"Current {name} schema is {actual!r}; Cycle 8 expects {expected!r}. Update the version matrix deliberately rather than allowing silent drift.")
    contract_current={k:CURRENT[k] for k in ("preflight","session","guard","performance","run_record","run_context","pe_imports","native_modules","acceptance")}
    for kind,schema in contract_current.items():
        allowed=evidence_contract.SUPPORTED.get(kind,set())
        if schema not in allowed:errors.append(f"Evidence Contract {evidence_contract.SCHEMA} does not support current {kind} schema {schema}.")
    if repeatability.REQUIRED_CONTEXT_SCHEMA!=run_context.SCHEMA:errors.append(f"Repeatability requires {repeatability.REQUIRED_CONTEXT_SCHEMA}, but current run context is {run_context.SCHEMA}.")
    if getattr(acceptance,"DEVICE_SCHEMA",None)!=device_evidence.SCHEMA:errors.append(f"Acceptance requires device schema {getattr(acceptance,'DEVICE_SCHEMA',None)}, but current producer is {device_evidence.SCHEMA}.")
    if getattr(attempt_ledger,"RUNTIME_SCHEMA",None)!=runtime_bundle_audit.SCHEMA:errors.append(f"Attempt Ledger requires runtime schema {getattr(attempt_ledger,'RUNTIME_SCHEMA',None)}, but current runtime audit producer is {runtime_bundle_audit.SCHEMA}.")

    producer_touch=set(getattr(device_evidence,"TOUCH_INPUT_MODES",set()))
    acceptance_touch=set(getattr(acceptance,"TOUCH_INPUT_MODES",set()))
    manifest_touch=set(getattr(evidence_manifest,"TOUCH_INPUT_MODES",set()))
    repeat_touch=set(getattr(repeatability,"FINAL_TOUCH_MODES",set()))
    if not producer_touch:errors.append("Device evidence producer exposes no touch input-mode vocabulary.")
    if not (producer_touch==acceptance_touch==manifest_touch==repeat_touch):errors.append(f"Touch-mode vocabulary drift: producer={sorted(producer_touch)}, acceptance={sorted(acceptance_touch)}, manifest={sorted(manifest_touch)}, repeatability={sorted(repeat_touch)}.")
    run_modes=set(getattr(run_record,"INPUT_MODES",set()))
    pipeline_modes=set(getattr(pipeline,"INPUT_MODES",()))
    diagnostic_modes=set(getattr(device_evidence,"DIAGNOSTIC_INPUT_MODES",set()))
    ledger_modes=set(getattr(attempt_ledger,"INPUT_MODES",set()))
    if not (run_modes==pipeline_modes==diagnostic_modes==ledger_modes):errors.append(f"All input-mode vocabulary drift: run_record={sorted(run_modes)}, pipeline={sorted(pipeline_modes)}, device={sorted(diagnostic_modes)}, ledger={sorted(ledger_modes)}.")
    if not producer_touch.issubset(run_modes):errors.append("Touch acceptance modes are not all valid sealed run-profile modes.")

    return {"schema":SCHEMA,"passed":not errors,"current":CURRENT,"expected_current":EXPECTED_CURRENT,"contract_supported":{k:sorted(v) for k,v in evidence_contract.SUPPORTED.items()},"input_modes":{"touch":sorted(producer_touch),"all":sorted(run_modes)},"errors":errors,"rule":"A producer schema bump, runtime-ledger contract change, or input-mode vocabulary change must update this explicit matrix and every consumer. Silent schema, runtime-audit, ledger-provenance or interaction-profile drift is a CI failure."}
def main()->int:
    p=argparse.ArgumentParser(description="Audit HunieCam evidence schema/input-mode synchronization");p.add_argument("--json",dest="json_path");args=p.parse_args();report=audit();text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path:
        from pathlib import Path
        Path(args.json_path).write_text(text+"\n",encoding="utf-8")
    print(text);return 0 if report["passed"] else 2
if __name__=="__main__":raise SystemExit(main())
