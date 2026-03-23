# UPDATED TVC KEY LOADER (PROMPT#09)

The TVC pipeline has been upgraded to utilize a **Dynamic Key Auto-Loader** standard in `tvc_vault.py`.

## Core Mechanics

### 1. In-Memory Sub-Probing
Instead of blindly returning the exact string match for `get_secret("Imperial Gemini")`, the updated loader:
*   Collects **all** keys belonging to the requested Provider (e.g., `Google Gemini` or `Runware`) from the vault.
*   Puts the explicit name match at index 0 (Highest priority).
*   Sequentially loops through the candidate array and fires a deterministic API probe.
*   Only returns the key when the probe returns an `ACTIVE` response payload.

### 2. Cache Routing
Once an ACTIVE key is validated, it is injected into the global `_ACTIVE_KEY_CACHE` dictionary. Subsequent calls to `get_secret` during the same Python runtime completely bypass the JSON disk I/O and API probing, achieving near-zero latency for subsequent retrievals.

### 3. Graceful Failure
If an API key expires mid-development, the system inherently knows that the `imperial_gemini.json` key (for example) is inactive, and will simply fall back to parsing the next Google Gemini key in the vault list without crashing the overall app layer with `400 INVALID_ARGUMENT` during video production.
