import os, re

def refactor_supreme_commander():
    with open('supreme_commander.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Imports
    content = content.replace('from google import genai\n', '')
    content = content.replace('IMPERIAL_API_KEY = get_secret("key_HGmChvaB")', 'FIREWORKS_API_KEY = get_secret("key_HGmChvaB")')
    content = content.replace('# MIGRATED TO FIREWORKS: client = genai.Client(api_key=IMPERIAL_API_KEY)\n', '')

    fireworks_chat_func = '''
import requests as _requests

class DummyRes:
    def __init__(self, text):
        self.text = text

def fireworks_chat_completion(contents):
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "accounts/fireworks/models/kimi-k2p5",
        "messages": [{"role": "user", "content": contents}],
        "max_tokens": 2000
    }
    resp = _requests.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return DummyRes(data["choices"][0]["message"]["content"])
'''
    if 'def fireworks_chat_completion' not in content:
        content = content.replace('def classify_job(', fireworks_chat_func + '\ndef classify_job(')

    # replace generation call
    pattern = re.compile(r'response = client\.models\.generate_content\(\s*model=GEMINI_BRAIN,\s*contents=(.*?)\n\s*\)', re.DOTALL)
    content = pattern.sub(r'response = fireworks_chat_completion(\1)', content)

    with open('supreme_commander.py', 'w', encoding='utf-8') as f:
        f.write(content)

refactor_supreme_commander()
print("supreme_commander.py refactored successfully.")
