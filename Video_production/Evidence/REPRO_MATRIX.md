# REPRO MATRIX

| Flow Name | Steps | Expected | Actual | Result |
| :--- | :--- | :--- | :--- | :--- |
| Verify Recent Fixes | `python verify_fixes.py` | All 8 checks PASS | All 8 checks PASS | **PASS** |
| Simple Creation | `python run_test.py "red cube" ...` | Create video | Hangs at Harvester stage | **FAIL** |
| Telemetry Check | Inspect `verification_report.json` | Word count match | 76% error (280 vs 159) | **FAIL** |
| Security Check | Inspect `supreme_commander.py` | No plain-text keys | Found `IMPERIAL_API_KEY` | **FAIL** |
| UI Launch | `python tvc_launcher.py` | Window opens | Window opens | **PASS** |

## Evidence References
- **Log**: `tvc_multi_agent_db/pipeline_run.log` shows hang at Harvester.
- **JSON**: `tvc_multi_agent_db/verification_report.json` shows word count mismatch.
- **Code**: `supreme_commander.py:42` shows hardcoded key.
