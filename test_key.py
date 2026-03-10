import os
from google.genai import Client

def test_key():
    from tvc_vault import get_secret
    key = get_secret("key_HGmChvaB")
    print(f"Key loaded from vault (len={len(key)})")
    try:
        client = Client(api_key=key)
        res = client.models.generate_content(model="gemini-2.0-flash", contents="Hello")
        print(f"Success: {res.text[:20]}...")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    check_key()
