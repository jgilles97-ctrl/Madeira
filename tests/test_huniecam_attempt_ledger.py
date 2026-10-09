import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("huniecam_attempt_ledger",ROOT/"tools"/"huniecam_attempt_ledger.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_attempt_ledger"]=mod;SPEC.loader.exec_module(mod)

def session(stage,failures=()):return {"deepest_stage":stage,"deepest_stage_name":f"stage {stage}","markers":[{"code":"target_started"}] if stage>=20 else [],"failures":[{"code":x} for x in failures],"next":{"priority":"test"}}
def run_record(stage,build="build-a",*,config="",arguments="",display="fit",resolution="1280x720",fps=60,launch_mode="direct",input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_RUN_RECORD_V1","ready_for_comparison":True,"build":{"fingerprint_sha256":build},"session":{"deepest_stage":stage},"profile":{"launch_mode":launch_mode,"resolution":resolution,"display":display,"fps":fps,"input_mode":input_mode,"config":config,"arguments":arguments}}

class HunieCamAttemptLedgerTests(unittest.TestCase):
    def add(self,ledger,stage,*,input_mode="direct_finger",run=None,purpose="diagnostic",config="",display="fit"):
        return mod.add_attempt(ledger,session(stage),{"status":"PASS","experiment":"test"},launch_mode="direct",resolution="1280x720",display=display,fps=60,input_mode=input_mode,config=config,arguments="",purpose=purpose,run_record=run or run_record(stage,input_mode=input_mode,config=config,display=display))
    def test_first_run_is_baseline_and_locks_build(self):
        ledger,summary=self.add(None,30);self.assertEqual(ledger["schema"],"MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V3");self.assertEqual(summary["attempt"]["movement"],"BASELINE");self.assertEqual(summary["attempt"]["profile"]["input_mode"],"direct_finger");self.assertEqual(ledger["owned_build_fingerprint"],"build-a")
    def test_input_mode_changes_profile_fingerprint_and_is_not_duplicate(self):
        ledger,_=self.add(None,75,input_mode="direct_finger",purpose="acceptance");ledger,summary=self.add(ledger,75,input_mode="touch_pointer");self.assertFalse(summary["attempt"]["duplicate_profile_before"]);self.assertNotEqual(ledger["attempts"][0]["profile_sha256"],ledger["attempts"][1]["profile_sha256"])
    def test_same_input_mode_profile_is_duplicate(self):
        ledger,_=self.add(None,30);_,summary=self.add(ledger,30);self.assertTrue(summary["attempt"]["duplicate_profile_before"]);self.assertTrue(summary["warnings"])
    def test_run_record_input_mode_must_match_ledger_attempt(self):
        with self.assertRaisesRegex(ValueError,"profile input_mode"):
            self.add(None,30,input_mode="direct_finger",run=run_record(30,input_mode="touch_pointer"))
    def test_invalid_input_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"input_mode"):
            mod.add_attempt(None,session(30),None,launch_mode="direct",resolution="1280x720",fps=60,input_mode="magic_touch",config="",arguments="")
    def test_different_build_is_rejected(self):
        ledger,_=self.add(None,30,run=run_record(30,"aaa"))
        with self.assertRaisesRegex(ValueError,"different owned HunieCam build"):self.add(ledger,75,run=run_record(75,"bbb"))
    def test_locked_ledger_requires_run_record(self):
        ledger,_=self.add(None,30)
        with self.assertRaisesRegex(ValueError,"run record is required"):mod.add_attempt(ledger,session(40),None,launch_mode="direct",resolution="1280x720",fps=60,input_mode="direct_finger",config="",arguments="")
    def test_run_record_stage_must_match_session(self):
        with self.assertRaisesRegex(ValueError,"deepest stage"):self.add(None,30,run=run_record(65))
    def test_run_record_display_must_match_ledger_attempt(self):
        with self.assertRaisesRegex(ValueError,"profile display"):self.add(None,30,display="fit",run=run_record(30,display="stretch"))
    def test_display_mode_changes_profile_fingerprint(self):
        a={"launch_mode":"direct","resolution":"1280x720","display":"fit","fps":60,"input_mode":"direct_finger","config":"","arguments":""};b=dict(a);b["display"]="stretch";self.assertNotEqual(mod.profile_fingerprint(a),mod.profile_fingerprint(b))
    def test_deeper_run_is_improvement_same_build(self):
        ledger,_=self.add(None,30);cfg="env.MADEIRA_WOW_RWX_PLAIN = 1";ledger,summary=self.add(ledger,65,config=cfg);self.assertEqual(summary["attempt"]["movement"],"IMPROVED");self.assertEqual(ledger["best_stage"],65)
    def test_regression_warns_against_promotion(self):
        ledger,_=self.add(None,65);ledger,summary=self.add(ledger,45,config="d3d9 = native",run=run_record(45,config="d3d9 = native"));self.assertEqual(summary["attempt"]["movement"],"REGRESSED_VS_BEST");self.assertTrue(summary["warnings"])
    def test_repeatability_duplicate_is_not_warned_as_waste(self):
        ledger,_=self.add(None,75,purpose="acceptance");_,summary=self.add(ledger,75,purpose="repeatability");self.assertFalse(any("already tried" in w for w in summary["warnings"]))
    def test_legacy_v2_migrates_with_unknown_input_mode(self):
        legacy={"schema":"MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V2","title":"HunieCam Studio","steam_app_id":426000,"attempts":[{"profile":{"launch_mode":"direct","resolution":"1280x720","display":"fit","fps":60,"config":"","arguments":""}}],"best_stage":0,"best_attempt":None,"owned_build_fingerprint":None};out=mod._migrate(legacy);self.assertEqual(out["schema"],"MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V3");self.assertEqual(out["attempts"][0]["profile"]["input_mode"],"unknown-legacy")
    def test_guard_failure_blocks_recording(self):
        with self.assertRaises(ValueError):mod.add_attempt(None,session(20),{"status":"FAIL"},launch_mode="direct",resolution="1280x720",fps=60,input_mode="direct_finger",config="d3d9=native",arguments="-force-d3d9")

if __name__=="__main__":unittest.main()
