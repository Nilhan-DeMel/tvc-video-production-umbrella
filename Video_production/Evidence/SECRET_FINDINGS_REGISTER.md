# SECRET FINDINGS REGISTER

| SECRET-ID | File path | Line | Type | Status | Plaintext? | Moved to Vault? | Vault Key Name | Rotation Required? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SEC-001 | `tvc_langgraph_core.py` | 47 | Runware API | CONFIRMED | Yes | No | Runware SOTA | **YES (SECURITY INCIDENT)** |
| SEC-002 | `list_models.py` | 5 | Gemini Env | CONFIRMED | No (Env) | No | Imperial Gemini | No |
| SEC-003 | `run_tvc_v5.py` | 5 | Gemini Env | CONFIRMED | No (Env) | No | Imperial Gemini | No |
| SEC-004 | `test_key.py` | 6 | Gemini Env | CONFIRMED | No (Env) | No | Imperial Gemini | No |

### Notes
- **SEC-001**: Hardcoded Runware key is a primary vulnerability. It will be moved to a new secret file `runware_sota.json` in the vault.
- **SEC-002-004**: These are "Soft Hardcodes" (using environment variables directly). These will be standardized to use the `tvc_vault` loader for consistency.
