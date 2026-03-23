# TVC Forensic Debug Report: USER_CONTEXT Stand-up Session

## Audit Target
- Final successful artifact: `D:\AI-Apps-In-Drive\App_Station\Video_production\emperor_output_1772988849.mp4`
- Scoped run sequence: `20260308_220539` through `20260308_222406`
- Evidence roots:
  - `D:\AI-Apps-In-Drive\App_Station\Video_production\Evidence\user_context_runs`
  - `D:\AI-Apps-In-Drive\App_Station\Video_production\tvc_multi_agent_db`
  - `D:\AI-Apps-In-Drive\App_Station\Video_production\tvc_langgraph_core.py`
  - `D:\AI-Apps-In-Drive\App_Station\Video_production\supreme_commander.py`

## Method (Systematic Debugging)
1. Root-cause investigation first: extract deterministic timeline and exact failure signatures from each run log.
2. Pattern analysis: compare repeated failure modes across attempts and identify where fallback/repair paths were required.
3. Hypothesis validation: verify root-cause consistency against source code and runtime artifacts.
4. Fix attribution: separate permanent fixes, temporary workarounds, and unresolved defects.

## Deterministic Timeline

| Attempt | Run ID | Stage Reached | Hard Failure / Outcome | Workaround/Fix Used | Final Status |
|---|---|---|---|---|---|
| A1 | `20260308_220539` | Commander argument parsing | `FileNotFoundError: ... '\\'` | Corrected shell quoting for `--context-file` | Failed |
| A2 | `20260308_220602` | Writer | `Writer quality gate failed ... meta_prompt_leak,low_request_alignment` | Prompt wording changed; retried | Failed |
| A3 | `20260308_220856` | Writer | `Writer quality gate failed ... meta_prompt_leak` | Prompt wording tightened; retry loop started | Failed |
| A4 | `20260308_221149_retry1` | Writer | Same meta-leak hard stop | Retry only | Failed |
| A5 | `20260308_221417_retry2` | Writer | Same meta-leak hard stop | Retry only | Failed |
| A6 | `20260308_221701_retry3` | Writer | Same meta-leak hard stop | Retry only | Failed |
| A7 | `20260308_221937_retry4` | Writer | Same meta-leak hard stop | Retry only | Failed |
| A8 | `20260308_222406` | Full pipeline | Writer meta-leak persisted but USER_CONTEXT direct-script fallback activated; TopicExtractor/SceneDirector required repair/fallback; render + verify passed | Added Writer USER_CONTEXT deterministic fallback | Success |

## Stage-by-Stage Pipeline Audit Map (Successful Run A8)

| Stage | Observed Behavior | Evidence | Risk Note |
|---|---|---|---|
| Commander | Request recognized as USER_CONTEXT; no YouTube path selected | `...\\20260308_222406\\terminal.log:204` | Log ordering confusion (header appears late). |
| Harvester | Correctly skipped YouTube in USER_CONTEXT mode | `...\\20260308_222406\\terminal.log:6` | Expected behavior. |
| Writer | 2 quality-gate rejections on `meta_prompt_leak`; deterministic fallback used | `...\\20260308_222406\\terminal.log:12,15,17`; `writer_quality_report.json` | Core instability remained; success depended on fallback. |
| DurationGate | Passed at 124s for 120s target | `...\\20260308_222406\\terminal.log:18` | Within configured tolerance. |
| TopicExtractor | Primary malformed output; strict repair retry succeeded | `...\\20260308_222406\\terminal.log:20` | Model-output fragility. |
| SceneDirector | Primary path under-segmented; cardinality guard forced deterministic fallback | `...\\20260308_222406\\terminal.log:24`; `scene_audio_prompt_report.json` | Prevented one-image collapse. |
| Audio | Neural CPP rejected; local CPP used. Primary and repair VTT mapping failed; local deterministic mapper used | `audio_stage_report.json` | Strong fallback dependence for sync path. |
| PromptArchitect | Primary path succeeded with 14 prompt/QA pairs | `scene_audio_prompt_report.json` | Stable in this run. |
| SotaForge | 14/14 epochs generated and QA-passed | `...\\20260308_222406\\terminal.log:85-176` | Stable in this run. |
| Editor | Render complete | `...\\20260308_222406\\terminal.log:181` | Stable in this run. |
| Verifier | PASS (`drift=0.0`, telemetry pass) | `...\\20260308_222406\\terminal.log:184,187`; `verification_report.json` | Final artifact valid. |

## Structured Issue Log (10-Field Cards)

### TVC-UC-001
1. **Issue title:** USER_CONTEXT CLI quoting produced invalid context path  
2. **Description:** First launch passed a malformed `--context-file` token (`'\\'`) and aborted before entering the pipeline.  
3. **Where:** Commander parsing (`parse_narrate_context_flags`)  
4. **Symptoms/impact:** Immediate `FileNotFoundError`; zero pipeline progress.  
5. **Probable root cause:** Shell escaping/quoting mismatch when building command string.  
6. **How confirmed:** `...\\20260308_220539\\terminal.log:19`; parser path handling in `supreme_commander.py:337-379`.  
7. **Best permanent fix:** Move to explicit argv parsing with robust path normalization and reject bare-slash tokens with clearer diagnostics.  
8. **Temporary workaround used:** Re-ran command with corrected quoting.  
9. **Severity/priority:** High / P1  
10. **Resolution state:** **Partially resolved** (operator fixed invocation; parser still brittle to malformed path tokenization).

### TVC-UC-002
1. **Issue title:** Writer repeatedly generated meta-reasoning text in USER_CONTEXT mode  
2. **Description:** Writer output repeatedly tripped `meta_prompt_leak` validation and hard-stopped pipeline.  
3. **Where:** Writer generation + validation (`writer_node`, `_validate_writer_script`)  
4. **Symptoms/impact:** 6 consecutive failed runs (`A2-A7`) with same hard-stop reason.  
5. **Probable root cause:** LLM draft path not reliably constrained by strict retry prompt; model drift toward instruction/meta text.  
6. **How confirmed:** `...\\220856\\terminal.log:12-17`; `...\\221937_retry4\\terminal.log:12-17`; `writer_quality_report.json` meta hit patterns.  
7. **Best permanent fix:** Make USER_CONTEXT script-authoritative mode first-class (optional bypass of generative rewrite) or enforce structured output schema with hard parser instead of free-form prose.  
8. **Temporary workaround used:** Added USER_CONTEXT deterministic fallback (direct script sanitization + local CPP) after two meta-leak retries.  
9. **Severity/priority:** Critical / P0  
10. **Resolution state:** **Partially resolved** (mitigated by fallback; root LLM leakage persists).

### TVC-UC-003
1. **Issue title:** USER_CONTEXT request-alignment gate produced a false negative  
2. **Description:** First writer failure included `low_request_alignment` even though user-provided context was valid.  
3. **Where:** Writer quality gate thresholding (`_validate_writer_script`)  
4. **Symptoms/impact:** Early abort in `A2` with compound failure reason; increased retry churn.  
5. **Probable root cause:** Alignment gate weights request wording heavily even in USER_CONTEXT workflows where context should dominate.  
6. **How confirmed:** `...\\220602\\terminal.log:13,16-18`; quality gate logic in `tvc_langgraph_core.py:2136-2139`.  
7. **Best permanent fix:** In USER_CONTEXT mode, shift primary alignment metric to `context_overlap`; treat request overlap as secondary informational metric.  
8. **Temporary workaround used:** Rephrased request prompt with more overlap terms.  
9. **Severity/priority:** Medium / P2  
10. **Resolution state:** **Partially resolved** (did not recur after prompt shift + fallback, but gate design remains mode-insensitive).

### TVC-UC-004
1. **Issue title:** Neural CPP frequently ballooned scripts, causing clamp churn  
2. **Description:** Writer repeatedly produced massive post-CPP expansions (2.4k-3k words) requiring clamp and/or revert.  
3. **Where:** Writer prosody pass (`apply_cpp_and_clamp`)  
4. **Symptoms/impact:** Extra latency, unstable draft quality, repeated rejection loops.  
5. **Probable root cause:** Neural CPP LLM response not constrained tightly enough; over-generation despite prosody-only intent.  
6. **How confirmed:** `...\\220602\\terminal.log:11-12`; `...\\221701_retry3\\terminal.log:11,14`; writer report word counts.  
7. **Best permanent fix:** Replace neural CPP with deterministic local CPP for USER_CONTEXT, or enforce strict max-token schema and exact echo-transform validation.  
8. **Temporary workaround used:** Existing overshoot guard, length clamp, and local CPP fallback in downstream audio.  
9. **Severity/priority:** High / P1  
10. **Resolution state:** **Partially resolved** (guardrails prevent hard failure, but pathological CPP output remains common).

### TVC-UC-005
1. **Issue title:** Text sanitization strips non-ASCII punctuation, degrading narration text fidelity  
2. **Description:** Apostrophes and smart quotes from user script became split forms (`I m`, `don t`, `you ve`).  
3. **Where:** `_sanitize_tts_script`  
4. **Symptoms/impact:** Reduced linguistic fidelity and potential pronunciation quality drift.  
5. **Probable root cause:** Non-ASCII purge regex replaces all non-ASCII chars with spaces.  
6. **How confirmed:** `master_script.txt` final content; sanitizer regex in `tvc_langgraph_core.py:1904`.  
7. **Best permanent fix:** Normalize smart punctuation to ASCII equivalents (`’ -> '`, `“/” -> "`) before ASCII filtering.  
8. **Temporary workaround used:** None.  
9. **Severity/priority:** Medium / P2  
10. **Resolution state:** **Unresolved**.

### TVC-UC-006
1. **Issue title:** TopicExtractor primary output malformed; repair retry required  
2. **Description:** Primary extraction failed JSON parse (`primary_parse_error`), then strict repair path recovered.  
3. **Where:** TopicExtractor  
4. **Symptoms/impact:** Added latency and dependence on secondary path.  
5. **Probable root cause:** Unstructured LLM response occasionally violates JSON schema contract.  
6. **How confirmed:** `...\\222406\\terminal.log:20`; extraction/repair logic `tvc_langgraph_core.py:1681-1700`.  
7. **Best permanent fix:** Enforce function-calling/JSON schema mode; reject non-JSON at API level.  
8. **Temporary workaround used:** Built-in strict repair retry.  
9. **Severity/priority:** Medium / P2  
10. **Resolution state:** **Partially resolved** (runtime recovered; upstream output fragility remains).

### TVC-UC-007
1. **Issue title:** SceneDirector primary result under-segmented (single scene), risking visual collapse  
2. **Description:** Scene payload had only 1 scene for long narration and triggered cardinality guard fallback.  
3. **Where:** SceneDirector  
4. **Symptoms/impact:** Without guard, output risked one-image video; fallback prevented regression.  
5. **Probable root cause:** Model segmentation failure / schema insufficiency under this script style.  
6. **How confirmed:** `...\\222406\\terminal.log:24`; `scene_audio_prompt_report.json` shows `scene_cardinality_low:1<6`; guard logic at `tvc_langgraph_core.py:2437-2443`.  
7. **Best permanent fix:** Stronger scene schema with minimum-cardinality enforced in primary model contract + deterministic segmentation first for long monologues.  
8. **Temporary workaround used:** Deterministic cardinality fallback.  
9. **Severity/priority:** High / P1  
10. **Resolution state:** **Partially resolved** (fallback works; primary path still unstable).

### TVC-UC-008
1. **Issue title:** Audio epoch mapping failed in primary and repair passes; local deterministic mapping used  
2. **Description:** Both LLM mapping passes failed (`epochs_not_list`, `epoch_missing_for_scene_9`), then local mapper recovered.  
3. **Where:** Audio Engineer VTT->epoch mapping  
4. **Symptoms/impact:** Additional recovery path needed for sync integrity; potential drift risk if local mapper degraded.  
5. **Probable root cause:** LLM mapping output shape inconsistency against strict epoch schema.  
6. **How confirmed:** `audio_stage_report.json` stages `vtt_map_primary` failed, `vtt_map_repair` failed, `vtt_map_local` used.  
7. **Best permanent fix:** Prefer deterministic mapper as primary; use LLM mapping only for optional enhancements with strict post-validators.  
8. **Temporary workaround used:** Existing deterministic local mapper fallback.  
9. **Severity/priority:** High / P1  
10. **Resolution state:** **Partially resolved** (recoverable path exists; primary+repair remain brittle).

### TVC-UC-009
1. **Issue title:** Shared mutable runtime artifacts overwrite per-attempt evidence  
2. **Description:** `tvc_multi_agent_db` reports (e.g., `writer_quality_report.json`) reflect latest run only; earlier attempt detail is lost unless separately captured.  
3. **Where:** Observability / evidence persistence layer  
4. **Symptoms/impact:** Forensic analysis required reconstructing from terminal logs; reduced traceability and slower root-cause closure.  
5. **Probable root cause:** Single global artifact paths without run-ID namespacing.  
6. **How confirmed:** Only latest `writer_quality_report.json` present despite multiple attempts; timeline needs `user_context_runs/*/terminal.log` to reconstruct.  
7. **Best permanent fix:** Namespace all reports under per-run directory and emit run manifest linking every node artifact path.  
8. **Temporary workaround used:** Manual per-run terminal log capture in `Evidence/user_context_runs/<run_id>/terminal.log`.  
9. **Severity/priority:** Medium / P2  
10. **Resolution state:** **Unresolved**.

### TVC-UC-010
1. **Issue title:** Log ordering inversion causes orchestration/commander chronology confusion  
2. **Description:** In logs, node-level orchestrator output appears before commander headers/context lines.  
3. **Where:** Logging/streaming boundary between commander and orchestrator stdout  
4. **Symptoms/impact:** Debuggers can misread sequence, delaying root-cause attribution.  
5. **Probable root cause:** Mixed buffered streams and/or delayed flush ordering across nested calls.  
6. **How confirmed:** `...\\222406\\terminal.log` shows commander banner/context lines after mission completion block.  
7. **Best permanent fix:** Structured logging with monotonic timestamps and explicit component tags; force flush order at boundaries.  
8. **Temporary workaround used:** Manual line-pattern extraction and timeline reconstruction.  
9. **Severity/priority:** Low / P3  
10. **Resolution state:** **Unresolved**.

## Master List of Issues Discovered
- `TVC-UC-001` CLI quoting/path parsing failure
- `TVC-UC-002` Writer meta-leak hard-stops
- `TVC-UC-003` USER_CONTEXT request-alignment false negative
- `TVC-UC-004` Writer neural CPP over-generation/clamp churn
- `TVC-UC-005` Unicode punctuation sanitization quality loss
- `TVC-UC-006` TopicExtractor primary parse failure
- `TVC-UC-007` SceneDirector cardinality collapse
- `TVC-UC-008` Audio mapping primary+repair failure
- `TVC-UC-009` Per-attempt evidence overwrite
- `TVC-UC-010` Log chronology inversion

## Ranked by Importance (Scoring Rubric)
Rubric (1-5 each): `Impact`, `Frequency`, `Blast Radius`, `Recovery Cost`  
Weighted score (0-100): `20 * (0.35*Impact + 0.20*Frequency + 0.25*Blast + 0.20*Recovery)`

| Rank | Issue | Impact | Freq | Blast | Recovery | Score |
|---:|---|---:|---:|---:|---:|---:|
| 1 | TVC-UC-002 | 5 | 5 | 5 | 5 | 100 |
| 2 | TVC-UC-004 | 4 | 5 | 4 | 4 | 82 |
| 3 | TVC-UC-007 | 5 | 2 | 4 | 4 | 79 |
| 4 | TVC-UC-008 | 4 | 2 | 4 | 4 | 72 |
| 5 | TVC-UC-009 | 3 | 5 | 3 | 3 | 66 |
| 6 | TVC-UC-005 | 3 | 4 | 3 | 2 | 62 |
| 7 | TVC-UC-006 | 3 | 2 | 3 | 2 | 54 |
| 8 | TVC-UC-003 | 3 | 1 | 2 | 2 | 43 |
| 9 | TVC-UC-001 | 3 | 1 | 2 | 2 | 43 |
| 10 | TVC-UC-010 | 2 | 4 | 1 | 1 | 39 |

## Best Fix Order

### Now (highest reliability return)
1. `TVC-UC-002` Harden USER_CONTEXT writer path so script-authoritative mode does not depend on generative rewrite.
2. `TVC-UC-004` Make deterministic/local CPP primary for USER_CONTEXT to remove over-generation churn.
3. `TVC-UC-007` Strengthen SceneDirector primary cardinality constraints to reduce fallback dependence.
4. `TVC-UC-008` Promote deterministic VTT mapper to primary path, keep LLM as optional enhancer.

### Next (stability + forensic quality)
5. `TVC-UC-009` Run-ID namespacing for all node artifacts.
6. `TVC-UC-005` Smart punctuation normalization in sanitizer.
7. `TVC-UC-006` Schema-first TopicExtractor output contract.

### Later (friction cleanup)
8. `TVC-UC-001` Harden commander CLI parsing and path diagnostics.
9. `TVC-UC-003` Rebalance USER_CONTEXT alignment scoring.
10. `TVC-UC-010` Normalize log stream ordering/format.

## Highest-Leverage Improvements (Reliability, Speed, Cleanliness)
1. Add a **USER_CONTEXT deterministic fast lane** (script-in -> local prosody -> downstream), bypassing risky writer generation where unnecessary.
2. Introduce **run-scoped artifact directories** with immutable manifests to eliminate evidence overwrite.
3. Use **strict structured outputs** (JSON schema/function-calling) for TopicExtractor/SceneDirector/Audio mapping.
4. Make **deterministic fallbacks primary** for scene splitting and epoch mapping in long monologues.
5. Add **failure-signature circuit breaker** (e.g., 2 identical writer meta-leak failures auto-switch to deterministic mode).
6. Standardize **component-tagged, timestamped logging** across Commander and node runtime for cleaner debugging.

## Residual Risks
- The final successful run still required multiple fallback/repair paths; core LLM output fragility remains.
- Without per-run artifact namespacing, future forensic investigations will continue to lose detail.
- Writer meta-leak remains a live failure mode if deterministic fallback is disabled/regressed.
