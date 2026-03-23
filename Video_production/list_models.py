import os
from google.genai import Client

def list_models():
    from tvc_vault import get_secret
    key = get_secret("key_HGmChvaB")
    client = Client(api_key=key)
    try:
        models = client.models.list()
        for m in models:
            print(m.name)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models()
