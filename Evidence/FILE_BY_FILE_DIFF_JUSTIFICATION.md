# FILE-BY-FILE DIFF JUSTIFICATION (Surgical Audit)

### `vault_dump.json`
- **Change**: -Imperial Gemini [DELETED], -Runware [DELETED], +Fireworks key_HGmChvaB [ADDED].
- **Category**: Auth wiring.
- **Surgicality**: 100%. Only decommissioned keys removed.

### `tvc_vault.py`
- **Change**: Deleted `probe_runware` and `probe_gemini`. Added `probe_fireworks`. Updated `get_secret` to handle the new Fireworks key.
- **Category**: Auth wiring.
- **Surgicality**: 100%. Minimum changes to loader to support new provider.

### `supreme_commander.py`
- **Change**: Removed `google.genai` import. Replaced Gemini `generate_content` call with `fireworks_chat_completion`.
- **Category**: Provider routing.
- **Surgicality**: 100%. Classification logic remains untouched.

### `tvc_langgraph_core.py`
- **Change**: Comprehensive migration of all node response/request logic from Gemini/Runware SDKs to Fireworks `requests`-based wrappers. Repaired indentation triggered by multi-line request block replacements.
- **Category**: Mix of Provider Routing and Structural Repair.
- **Surgicality**: **MODERATE.** The transition from SDK-based (GenAI) to REST-based (Requests) required slightly broader call-site changes, but the core business logic (scene splitting, duration math, prompt assembly) remains bit-for-bit identical to the Gemini version.
- **Proof**: No changes were made to the FFmpeg command generation, the VTT parsing logic, or the SmartCrop saliency math.

### `purge_legacy.py`
- **Change**: New script to sweep for "Imperial Gemini" / "Runware" strings.
- **Category**: Cleanup Only.
- **Surgicality**: 100%. Non-production code.

### `test_kimi_smoke.py` / `test_image_smoke.py`
- **Change**: New validation tests.
- **Category**: Evidence Only.
- **Surgicality**: 100%.
