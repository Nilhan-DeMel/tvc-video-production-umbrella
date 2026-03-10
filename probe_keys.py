import sys
import json
from google import genai
import requests

def probe_gemini(key: str, key_id: str):
    try:
        # MIGRATED TO FIREWORKS: client = genai.Client(api_key=key)
        # Minimal cost probe: list models
        models = list(client.models.list())
        if len(models) > 0:
            print(f"[PROBE-SUCCESS] Gemini Key ({key_id}) is ACTIVE.")
            return True
    except Exception as e:
        print(f"[PROBE-ERROR] Gemini Key ({key_id}) is INACTIVE. Error: {e}")
        return False

def probe_runware(key: str, key_id: str):
    try:
        # Minimal cost probe: ping models list via REST using the API key
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        test_payload = [
            {
                "taskType": "ping",
                "taskUUID": "test-uuid"
            }
        ]
        resp = requests.post("https://api.runware.ai/v1", headers=headers, json=test_payload, timeout=15)
        if resp.status_code == 200 and "error" not in resp.text.lower():
            print(f"[PROBE-SUCCESS] Runware Key ({key_id}) is ACTIVE.")
            return True
        else:
            print(f"[PROBE-ERROR] Runware Key ({key_id}) is INACTIVE. Code: {resp.status_code}, Body: {resp.text}")
            return False
    except Exception as e:
        print(f"[PROBE-ERROR] Runware Key ({key_id}) is INACTIVE. Error: {e}")
        return False

if __name__ == "__main__":
    with open("vault_dump.json", "r") as f:
        vault = json.load(f)

    # 1. Grab Gemini candidates
    gemini_keys = [k for k in vault if k.get("provider") == "Google Gemini"]
    print("--- PROBING GEMINI KEYS ---")
    for k in gemini_keys:
        key_val = k['key']
        key_id = k['filename'] + " (" + key_val[:4] + "..." + key_val[-4:] + ")"
        probe_gemini(key_val, key_id)

    # 2. Grab Runware candidates
    runware_keys = [k for k in vault if k.get("provider") == "Runware"]
    print("\n--- PROBING RUNWARE KEYS ---")
    for k in runware_keys:
        key_val = k['key']
        key_id = k['filename'] + " (" + key_val[:4] + "..." + key_val[-4:] + ")"
        probe_runware(key_val, key_id)
