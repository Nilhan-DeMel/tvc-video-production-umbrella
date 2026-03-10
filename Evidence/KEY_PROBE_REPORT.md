# SOTA API Key Probe Report (PROMPT#09)

## Probe Methodology
*   **Google Gemini**: Evaluated via the `client.models.list()` SDK method. Valid configurations return a model list. Invalid configurations return HTTP 400 (API_KEY_INVALID).
*   **Runware**: Evaluated via REST POST to `https://api.runware.ai/v1` with the `ping` payload. Valid configurations return HTTP 200. Invalid configurations return HTTP 400/401/403.

## Results Matrix

| Provider | Key Identifier | Status | Diagnosis | Proof File |
| :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** | `imperial_gemini.json` (`AIza...N_S4`) | **ACTIVE** | Returns valid model definitions | `PROBE_KEYS_EXECUTION.txt` |
| **Google Gemini** | `1772209608994.json` (`AIza...pC6c`) | **INACTIVE** | HTTP 400 API_KEY_INVALID (Expired) | `PROBE_KEYS_EXECUTION.txt` |
| **Runware** | `runware_sota.json` (`p2KW...KZmd`) | **ACTIVE** | HTTP 200 standard ping response | `PROBE_KEYS_EXECUTION.txt` |

## Conclusion
The system successfully identified valid, active keys for *both* required providers out of the Vault's overall inventory. The dynamic key loader will now be configured to prioritize evaluating and caching these keys.
