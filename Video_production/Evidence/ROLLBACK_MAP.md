# Rollback Map: Fireworks AI Migration

## Scenario A: Undo Collateral (Keep Fireworks)
If you want the Fireworks migration but dislike the `sota_json_repair` or `duration_fail` logic:
1. Revert `tvc_langgraph_core.py` to use `json.loads`.
2. Remove the `if state.get("status") != "duration_fail"` check from `writer_node`.
**Warning**: This will likely cause the pipeline to fail on malformed JSON or infinite loops.

## Scenario B: Full Provider Reversion (Back to Gemini)
1. Revert `supreme_commander.py` API keys and imports.
2. Revert `tvc_langgraph_core.py` to use `google.generativeai` client calls.
3. Revert `vault_dump.json` to include Gemini keys.
**Warning**: Runware/Gemini preview keys are currently disabled/purged.

## Dangerous Partial Rollbacks
- **DO NOT** revert `tvc_vault.py` while keeping Fireworks code; the app will fail to load secrets.
- **DO NOT** revert LLM but keep Fireworks images; cross-provider latency may increase (INFERENCE).
