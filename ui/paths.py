import os


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXPECTED_ROOT_NAME = "video_production_agent"
COMMANDER_PATH = os.path.join(APP_ROOT, "supreme_commander.py")
DB_ROOT = os.path.join(APP_ROOT, "tvc_multi_agent_db")
RUNS_ROOT = os.path.join(DB_ROOT, "runs")
EVIDENCE_ROOT = os.path.join(APP_ROOT, "Evidence")
UI_PAYLOAD_ROOT = os.path.join(EVIDENCE_ROOT, "ui_launch_payloads")
UI_STATE_PATH = os.path.join(EVIDENCE_ROOT, "ui_state.json")

