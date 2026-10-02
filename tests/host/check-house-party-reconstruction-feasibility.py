#!/usr/bin/env python3
"""Regression checks for House Party reconstruction feasibility index."""
import importlib.util
from pathlib import Path

root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("rf",root/"tools/house-party/reconstruction-feasibility.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

base={
 "engine":{
   "family":{"value":"Unity"},
   "unity_version":{"value":"2021.3.33f1"},
   "scripting_backend":{"value":"IL2CPP"},
 },
 "compatibility":{
   "native_plugins":[],
   "managed_assemblies":["Assembly-CSharp.dll","UnityEngine.CoreModule.dll"],
 }
}
r=mod.score(base)
assert r["scripting_backend"]=="il2cpp"
assert r["band"] in {"poor","difficult","plausible","favorable"}
assert r["feasibility_index_0_to_10"] < 8
assert "scenes_recovered" in r["missing_recovery_evidence"]
assert "not a probability" in r["interpretation"]

mono={**base,"engine":{**base["engine"],"scripting_backend":{"value":"Mono"}}}
m=mod.score(mono,{"scenes_recovered":4,"prefabs_recovered":20,"serialized_data_recovered":10,"manual_recreation":"low"})
assert m["feasibility_index_0_to_10"] > r["feasibility_index_0_to_10"]
assert any(x["code"]=="mono-managed-logic" for x in m["reasons"])

hard=mod.score(base,{"unavailable_source_logic":20,"platform_specific_dependencies":12,"manual_recreation":"very-high"})
assert hard["feasibility_index_0_to_10"] < r["feasibility_index_0_to_10"]

print("PASS: reconstruction feasibility index is evidence-driven and not presented as a probability")
