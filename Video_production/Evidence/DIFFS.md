# DIFFS: Security Sweep & Vault Standardization

All modified files now use `from tvc_vault import get_secret`. Plaintext remains are 0.

## [MODIFY] tvc_langgraph_core.py
```diff
-# ==============================================================
-# PHASE 20: API KEYS & IMAGE GENERATION MODE
-# ==============================================================
-RUNWARE_API_KEY = "p2KW...Zmd"
+from tvc_vault import get_secret
+
+# SEC-001: Moved to vault (D:\AI\API\Secrets\runware_sota.json)
+RUNWARE_API_KEY = get_secret("Runware SOTA")
```

## [MODIFY] supreme_commander.py
```diff
-def load_imperial_key():
-    # ... ad-hoc loading logic ...
-IMPERIAL_API_KEY = load_imperial_key()
+from tvc_vault import get_secret
+
+IMPERIAL_API_KEY = get_secret("Imperial Gemini")
```

## [MODIFY] run_tvc_v5.py / list_models.py / test_key.py
- Replaced `os.environ.get("GEMINI_API_KEY")` with `get_secret("Imperial Gemini")`.
- Standardized to vault-first loading even for env-backed secrets.

## [MODIFY] imagen_forge.py / create_video.py / harvest_7min_script.py / forge_fallbacks.py / batch_semantic_images.py
- Removed all duplicated vault-loading chunks (10-20 lines per file).
- Standardized to: `from tvc_vault import get_secret; key = get_secret("Imperial Gemini")`.
