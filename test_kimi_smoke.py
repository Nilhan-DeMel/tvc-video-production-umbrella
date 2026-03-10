from tvc_vault import get_secret
import requests

key = get_secret("key_HGmChvaB")
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}
payload = {
    "model": "accounts/fireworks/models/kimi-k2p5",
    "messages": [{"role": "user", "content": "Explain the concept of an AI Agent in exactly one sentence."}],
    "max_tokens": 100
}
try:
    resp = requests.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    print("KIMI K2.5 SMOKE TEST PASSED.")
    print("Response:", resp.json()["choices"][0]["message"]["content"])
except Exception as e:
    print("KIMI K2.5 SMOKE TEST FAILED.")
    err_msg = str(e)
    if hasattr(e, 'response') and e.response is not None:
         err_msg += f". Response: {e.response.text}"
    print(err_msg)
