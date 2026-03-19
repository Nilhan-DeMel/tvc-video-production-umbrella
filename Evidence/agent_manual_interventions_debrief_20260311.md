# TVC Runtime Intervention Debrief (Agent-Facing)

Generated: 2026-03-11
Scope: Deterministic `USER_CONTEXT` NARRATE runs in `Video_production_agent`.

## TVC-INT-001 — Flux key alias drift (`BLF_FLUX2PRO` vs `BFL_API_KEY`)

- Symptom signature:
  - Runtime image stage reports missing Flux key while operator confirms key is present.
  - Key-audit entries show lookup misses for canonical alias despite env containing legacy alias.
- Primary files:
  - `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/tvc_vault.py`
- Root cause:
  - Secret resolution path treated `BLF_FLUX2PRO` as singleton canonical env var and did not normalize/accept the legacy alias `BFL_API_KEY`.
  - Result: false-negative key availability and avoidable runtime degradation/fallback.
- Hardening intervention:
  - Added alias set `_BFL_IMAGE_SECRET_ALIASES` = `{BLF_FLUX2PRO, BFL_API_KEY}`.
  - Added ordered env resolver `_load_env_key_any(secret_alias, env_var_names)` with deterministic precedence.
  - Added audit enrichment field `extra.resolved_env_var` to expose effective alias source in key logs.
- Expected behavior after fix:
  - Any run with either alias set resolves Flux key deterministically.
  - If both present, canonical alias (`BLF_FLUX2PRO`) wins.
- Verification evidence:
  - Unit tests:
    - `tests/test_api_key_audit.py::test_get_secret_blf_image_accepts_bfl_api_key_alias`
    - `tests/test_api_key_audit.py::test_get_secret_blf_image_prefers_blf_flux2pro_when_both_present`
  - Runtime smoke via preflight shows `flux=BFL_API_KEY` when canonical is absent.
- Residual risk:
  - External secret managers still need consistent alias metadata; resolver only guarantees local env-path compatibility.

## TVC-INT-002 — NARRATE flag parsing fragility for tokenized CLI input

- Symptom signature:
  - `--context-file` path parsing failures under quoted Windows paths.
  - Misparsed request fragments propagate downstream and can switch source mode unexpectedly.
- Primary files:
  - `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/supreme_commander.py`
- Root cause:
  - Legacy parser was regex/string-split oriented and assumed monolithic request string.
  - Shell tokenization edge-cases (escaping, quotes, drive-root paths) were not robustly validated.
- Hardening intervention:
  - Added token-native parsers:
    - `_parse_mode_duration_from_tokens(tokens)`
    - `parse_narrate_runtime_flags_from_tokens(tokens)`
  - Added `_normalize_context_file_path()` with explicit directory/drive-root rejection.
  - Maintained backward-compatible legacy parser for non-token callers.
- Expected behavior after fix:
  - Deterministic parse for explicit CLI tokens.
  - Fast-fail on malformed/unsafe context-file paths.
  - No silent fallback to ambiguous parsing mode when tokens are supplied.
- Verification evidence:
  - Unit tests:
    - `tests/test_commander_preflight_and_parse.py::test_parse_narrate_runtime_flags_from_tokens_windows_path`
    - `tests/test_commander_preflight_and_parse.py::test_parse_narrate_context_file_drive_root_rejected`
- Residual risk:
  - Callers that still pass only monolithic request strings remain on compatibility parser; migration to token flow recommended.

## TVC-INT-003 — Missing startup preflight caused late-stage key failure and wasted runtime

- Symptom signature:
  - Runs proceed into pipeline initialization and fail mid-run due to absent required keys.
  - Operator only discovers key-state issues after substantial elapsed time.
- Primary files:
  - `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/supreme_commander.py`
- Root cause:
  - No strict orchestrator preflight gate for required key set before dispatch.
  - Key checks were distributed/lazy inside downstream nodes, inflating blast radius of config faults.
- Hardening intervention:
  - Added `_startup_preflight_for_narrate(...)` before dispatch.
  - Added `_write_preflight_failure_artifact(payload)` to `Evidence/preflight_failures/`.
  - Added `run_attempt_id` + preflight metadata propagation into mission log.
  - CLI exits with code `2` on `preflight_failed` status.
  - `_ensure_fireworks_api_key()` now lazy-resolves from vault if env missing.
- Expected behavior after fix:
  - Missing keys fail-closed before expensive node execution.
  - Actionable artifact created with missing-key list and request hash for forensic grouping.
- Verification evidence:
  - Unit test:
    - `tests/test_commander_preflight_and_parse.py::test_startup_preflight_missing_keys_writes_artifact`
  - Runtime smoke:
    - missing-key run exits `2`, emits artifact in `Evidence/preflight_failures/`.
- Residual risk:
  - Preflight validates presence, not provider-side validity (revoked/expired tokens still fail at call time).

## Patch Surface Index

- `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/tvc_vault.py`
  - alias constants + multi-env resolver + audit enrichment.
- `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/supreme_commander.py`
  - tokenized parse path, context-file normalization, startup preflight, artifact emitter, lazy key resolution, CLI exit code gate.
- `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/tests/test_api_key_audit.py`
  - Flux alias compatibility tests.
- `D:/AI-Apps-In-Drive/App_Station/Video_production_agent/tests/test_commander_preflight_and_parse.py`
  - parser + preflight regression tests.

## Deterministic Verification Snapshot

- `python -m py_compile tvc_vault.py supreme_commander.py` -> PASS
- `pytest -q tests/test_api_key_audit.py tests/test_commander_preflight_and_parse.py` -> PASS (`10 passed`)

## Recommended Next Hardening (if needed)

1. Migrate all launcher entrypoints to token-first parser path and deprecate regex parser.
2. Add provider live-key handshake preflight (cheap auth probe) behind a short timeout.
3. Emit `live_status.txt` preflight stage records to improve operator observability before dispatch.
