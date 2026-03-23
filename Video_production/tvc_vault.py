import os
import json
import sys
import requests

# Cache for active keys to prevent re-probing on every get_secret call
_ACTIVE_KEY_CACHE = {}

def probe_fireworks(key: str) -> bool:
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": "accounts/fireworks/models/kimi-k2p5",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }
        resp = requests.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception:
        return False

def get_secret(secret_name):
    """
    Standardized secret loader for the TVC Pipeline.
    Loads secrets from the vault_dump.json, probes for an ACTIVE key, and caches it.
    """
    global _ACTIVE_KEY_CACHE

    if secret_name in _ACTIVE_KEY_CACHE:
        key = _ACTIVE_KEY_CACHE[secret_name]
        print(f"[VAULT] Loaded CACHED {secret_name} from vault (len={len(key)})")
        return key

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vault_path = os.path.join(current_dir, "vault_dump.json")
        
        if not os.path.exists(vault_path):
            print(f"[VAULT ERROR] Metadata index missing: {vault_path}")
            sys.exit(1)
            
        with open(vault_path, 'r', encoding='utf-8') as f:
            vault_index = json.load(f)
            
        # Group candidates by provider context
        target_provider = "Fireworks AI" if "key_HGmChvaB" in secret_name else None
        
        candidates = []
        for entry in vault_index:
            # First priority: direct name match
            if entry.get("name") == secret_name:
                candidates.insert(0, entry.get("key"))
            # Second priority: provider match
            elif target_provider and entry.get("provider") == target_provider:
                candidates.append(entry.get("key"))

        # Deduplicate candidates while preserving order
        seen = set()
        candidates = [x for x in candidates if not (x in seen or seen.add(x))]

        for key in candidates:
            if not key:
                continue
                
            is_active = False
            if target_provider == "Fireworks AI" or secret_name == "key_HGmChvaB":
                is_active = probe_fireworks(key)
            else:
                # If no probe configured, assume active if found
                is_active = True
                
            if is_active:
                _ACTIVE_KEY_CACHE[secret_name] = key
                print(f"[VAULT] Loaded ACTIVE {secret_name} from vault (len={len(key)})")
                return key
                
        print(f"[VAULT ERROR] No ACTIVE key found for '{secret_name}' in Vault candidates.")
        sys.exit(1)
        
    except Exception as e:
        print(f"[VAULT CRITICAL] System failure during secret retrieval: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Test loader
    test_key = get_secret("key_HGmChvaB")
    print("Vault loader functional.")

