# TVC System Notes (Master + Snapshot Linked)

```yaml
meta:
  document: tvc_system_notes.md
  role: canonical_system_memory_for_tvc_narrate
  location: D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/tvc_system_notes.md
  mode_focus: MODE_NARRATE
  update_policy: update_after_every_node_refinement_cycle
  current_baseline_snapshot: D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_124725
```

## 00-SYSTEM-INTENT
- TVC NARRATE must produce a single coherent video where narration, scene timing, rendered image sequence, subtitles, topic cards, and verifier telemetry remain synchronized.
- Current user priority: perfect 20-second target is non-blocking; synchronization and image coverage for the full narration runtime are blocking.
- Node changes must be made with full system awareness, not isolated assumptions.
- Paid API policy for NARRATE: Fireworks only.
- Dual-source routing is now first-class:
  - `USER_CONTEXT`: user-supplied `context_summary` is authoritative source text (non-YouTube path).
  - `YOUTUBE_HARVEST`: Harvester acquires YouTube transcript intelligence and feeds Writer.
- Source ambiguity is not allowed in explicit modes. Mixed source payloads are fail-closed by design.
- Prompt/API observability is mandatory: every Fireworks text/image call writes trace rows and policy audit artifacts.
- This document is the required boot artifact for any stateless agent touching TVC.

## 01-PIPELINE-GRAPH
```text
Entry: execute_multi_agent_narrator(user_prompt, final_output, api_key, target_duration, context_summary=None, input_source=YOUTUBE_HARVEST, narration_style=documentary, context_rewrite=off)

Harvester -> Writer -> DurationGate
                        |\
                        | duration_pass
                        v
                  TopicExtractor -> SceneDirector -> Audio -> PromptArchitect -> SotaForge -> Editor -> Verifier -> END
                        ^
                        |
                        duration_fail from DurationGate routes back to Writer
```

```yaml
graph_contract:
  node_order:
    - Harvester
    - Writer
    - DurationGate
    - TopicExtractor
    - SceneDirector
    - Audio
    - PromptArchitect
    - SotaForge
    - Editor
    - Verifier
  conditional_edge:
    node: DurationGate
    route_fn: route_duration
    pass_value: duration_pass
    pass_target: TopicExtractor
    fail_target: Writer
  source_mode_behavior:
    USER_CONTEXT:
      Harvester: skip_youtube_and_return_status_only
      Writer_source: context_summary_only
    YOUTUBE_HARVEST:
      Harvester: youtube_adaptive_multi_pass_with_strict_relevance_halt
      Writer_source: harvested_intelligence_only
```

## 02-STATE-CONTRACTS

### 02.1 Global AgentState Keys (active NARRATE path)
```yaml
agent_state_keys:
  - request_prompt
  - input_source
  - context_summary
  - narration_style
  - context_rewrite
  - target_output
  - target_duration
  - api_key
  - harvested_intelligence
  - script
  - duration_attempts
  - topic_callouts
  - audio_path
  - vtt_path
  - epochs
  - visual_scenes
  - style_dna
  - meta_context
  - character_manifest
  - sota_prompts
  - qa_targets
  - images_forged
  - total_epochs
  - qa_scores
  - final_video
  - verification_report
  - errors
  - status
```

### 02.2 Node I/O Contracts
| Node | Consumes | Produces | Primary Artifacts |
|---|---|---|---|
| Harvester | `request_prompt`, optional `input_source`/`context_summary` | `harvested_intelligence` + `status` (YouTube mode), `status=harvest_skipped_user_context` (user-context mode), or hard-stop on insufficient relevance | `tvc_multi_agent_db/yt_harvest/*.vtt`, `harvested_intelligence.txt`, `harvester_run_report.json`, `harvester_quality_report.json` |
| Writer | `request_prompt`, `target_duration`, `input_source`, source text (`context_summary` or `harvested_intelligence`), `status`, `duration_attempts` | `script`, `status`, `duration_attempts` | `master_script.txt` |
| DurationGate | `script`, `target_duration`, `duration_attempts` | `status` and optional `script` (forced truncation path) | `master_script.txt` |
| TopicExtractor | `script` | `topic_callouts`, `status` | `topic_callouts.json` |
| SceneDirector | `script` | `visual_scenes`, `style_dna`, `meta_context`, `character_manifest`, optional `epochs`, `status` | `scene_manifest.json` |
| Audio | `script`, `visual_scenes` | `audio_path`, `vtt_path`, `epochs`, sometimes `total_epochs`, `status` | `master_narration.mp3`, `narration.vtt`, `vtt_matrix.json` |
| PromptArchitect | `epochs`, `script`, `total_epochs`, optional `style_dna`/`meta_context`/`character_manifest` | `sota_prompts`, `qa_targets`, `status` | `master_prompts.json` |
| SotaForge | `epochs`, `sota_prompts`, `total_epochs`, optional `qa_targets` | `status`, `qa_scores`, `images_forged`, `epochs` (with `image_path`) | `tvc_multi_agent_db/assets/epoch_*.png` |
| Editor | `audio_path`, `epochs`, `target_output`, optional `topic_callouts` | `status`, `final_video` or `errors` | `typography.ass`, `filter.txt`, output `.mp4` |
| Verifier | `target_output`, `audio_path`, `script`, `vtt_path` | `verification_report`, `status` | `verification_report.json` |

Run-scope note:
Current runtime writes operational artifacts into `tvc_multi_agent_db/runs/<run_id>/...`.
Legacy root mirroring is opt-in via `TVC_LEGACY_MIRROR=1` (default `0`).
Realtime observability now includes `live_status.txt` + `live_status.json` in each run folder for heartbeat visibility (current node, retries, elapsed, ETA).

### 02.3 Source-Routing Contract (Authoritative)
```yaml
source_routing_contract:
  mode: MODE_NARRATE
  input_flags:
    - --context-file <path>
    - --context "<text>"
    - --narration-style documentary|sales_saas|human_story
    - --context-rewrite off|force
    - --watermark-mode on|off
  precedence:
    - context_file
    - context_inline
    - youtube_default
  resolved_input_source:
    context_present: USER_CONTEXT
    context_absent: YOUTUBE_HARVEST
  narration_style_defaults:
    narration_style: documentary
    context_rewrite: off
    watermark_mode: on
  fail_closed_rules:
    - USER_CONTEXT forbids harvested_intelligence
    - USER_CONTEXT requires non-empty context_summary
    - YOUTUBE_HARVEST forbids context_summary
    - YOUTUBE_HARVEST requires non-empty harvested_intelligence
  backward_compatibility:
    when_input_source_missing: legacy_writer_fallback_allowed
```

### 02.4 Narration Mode Matrix (Writer + Audio + Visual Tone)
```yaml
narration_modes:
  documentary:
    intent: neutral_authoritative_cinematic
    writer_profile: cinematic_documentary
    audio_tts:
      voice: en-GB-RyanNeural
      rate: "+0%"
      pitch: "+0Hz"
      volume: "+0%"
    scene_defaults:
      style_dna: "Cinematic documentary palette, grounded realism, natural contrast, controlled camera language"
      meta_context: "Documentary-style narrative sequence"

  sales_saas:
    intent: polished_persuasive_product_marketing
    writer_profile: saas_sales
    audio_tts:
      voice: en-GB-RyanNeural
      rate: "+12%"
      pitch: "+6Hz"
      volume: "+8%"
    scene_defaults:
      style_dna: "Premium SaaS campaign look, clean modern gradients, high-contrast product lighting, polished commercial framing"
      meta_context: "High-energy SaaS value story from pain point to outcome"

  human_story:
    intent: warm_empathetic_human_connection
    writer_profile: human_story
    audio_tts:
      voice: en-GB-RyanNeural
      rate: "-12%"
      pitch: "-2Hz"
      volume: "+0%"
    scene_defaults:
      style_dna: "Warm cinematic realism, soft natural light, intimate close framing, emotional texture"
      meta_context: "Human-centered emotional narrative with empathy and connection"
```

## 03-SYNC-CRITICAL-INVARIANTS
```yaml
invariants:
  - id: I01_vtt_scene_epoch_mapping
    rule: Audio node must map VTT boundaries onto SceneDirector scenes and produce epoch start/end timing.
    evidence: vtt_matrix.json + narration.vtt
    fail_signal: empty/malformed epochs or scene/epoch mismatch

  - id: I02_transition_offsets
    rule: Editor xfade offsets must match epoch start_time for epoch index >= 2.
    evidence: filter.txt + vtt_matrix.json
    fail_signal: offset_count_mismatch or offset drift

  - id: I03_subtitle_window
    rule: ASS subtitle layer windows must remain within each epoch start/end.
    evidence: typography.ass + vtt_matrix.json
    fail_signal: subtitle timings outside epoch range

  - id: I04_callout_window
    rule: Topic cards must use valid after_sentence index and card windows bounded by target epoch.
    evidence: topic_callouts.json + typography.ass + vtt_matrix.json
    fail_signal: after_sentence out of range, topic card count mismatch, overflow window

  - id: I05_epoch_asset_coverage
    rule: Every epoch used by Editor must resolve to an image file.
    evidence: epochs.image_path or assets glob
    fail_signal: missing image asset for any epoch

  - id: I06_verifier_consensus
    rule: Verifier must report pass with low drift and telemetry agreement.
    threshold: drift <= 1.0 and telemetry_pass == true
    evidence: verification_report.json
    fail_signal: verified false, drift high, telemetry mismatch

  - id: I07_source_exclusivity
    rule: Explicit source mode must carry exactly one upstream writing context.
    evidence: pipeline_run.log + run_assertions.json
    fail_signal: mixed source payload accepted, or declared source payload missing

  - id: I08_prompt_trace_completeness
    rule: Every Fireworks model call in run path emits node + template_id + endpoint host trace.
    evidence: api_call_trace.jsonl + trace_summary.json
    fail_signal: missing trace rows, missing template tags, or unmapped node calls

  - id: I09_paid_host_allowlist
    rule: Paid model endpoints in NARRATE must be Fireworks-only.
    evidence: paid_api_policy_check.json
    fail_signal: policy passed == false or non-Fireworks paid hosts present
```

## 04-API-BOUNDARY
```yaml
policy:
  mode: MODE_NARRATE
  paid_api_allowed:
    - Fireworks Chat Completions (https://api.fireworks.ai/inference/v1/chat/completions)
    - Fireworks FLUX image workflow (https://api.fireworks.ai/inference/v1/workflows/.../text_to_image)
  paid_api_disallowed:
    - Any non-Fireworks paid model provider in NARRATE execution path
  free_services_allowed:
    - YouTube subtitle retrieval via yt-dlp
    - edge_tts for speech/VTT generation
    - ffmpeg and ffprobe local media processing
    - local Python scripts, caches, and JSON artifacts
```

### 04.2 Prompt/API Map (locked)
```yaml
prompt_api_map:
  prompt_a_harvester_query_optimizer:
    node: Harvester
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_A_HARVESTER_QUERY_OPTIMIZER
    purpose: derive optimized YouTube query from request_prompt
  prompt_b_harvester_synthetic_pivot:
    node: Harvester
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_B_HARVESTER_SYNTHETIC_PIVOT
    purpose: legacy fallback prompt (disabled for default YOUTUBE_HARVEST strict mode)
  prompt_c_harvester_degraded_brief:
    node: Harvester
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_C_HARVESTER_DEGRADED_BRIEF
    purpose: legacy degraded fallback prompt (disabled for default YOUTUBE_HARVEST strict mode)
  prompt_d_writer_script_draft:
    node: Writer
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_D_WRITER_SCRIPT_DRAFT
    purpose: create narration script from request + selected context source
  prompt_e_writer_cpp_prosody:
    node: Writer
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_E_WRITER_CPP_PROSODY
    purpose: punctuation/prosody optimization for TTS
  prompt_topic_extractor_callouts:
    node: TopicExtractor
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_TOPIC_EXTRACTOR_CALLOUTS
    purpose: extract bounded on-screen callout topics from script
  prompt_topic_extractor_repair:
    node: TopicExtractor
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_TOPIC_EXTRACTOR_REPAIR
    purpose: strict one-shot repair retry when primary callout JSON is malformed/unusable
  prompt_f_scene_director_segmentation:
    node: SceneDirector
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_F_SCENE_DIRECTOR_SEGMENTATION
    purpose: scene JSON segmentation from script
  prompt_f_scene_director_repair:
    node: SceneDirector
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_F_SCENE_DIRECTOR_REPAIR
    purpose: strict repair retry for malformed scene payloads
  prompt_ga_audio_neural_cpp_refinement:
    node: Audio
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT
    purpose: pre-edge_tts neural prosody refinement with acceptance guard
  prompt_g_audio_vtt_to_epoch_mapping:
    node: Audio
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING
    purpose: map VTT timing onto fixed scenes
  prompt_g_audio_vtt_to_epoch_repair:
    node: Audio
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_G_AUDIO_VTT_TO_EPOCH_REPAIR
    purpose: strict repair retry for malformed epoch mappings
  prompt_h_prompt_architect_image_snippets:
    node: PromptArchitect
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS
    purpose: create per-epoch cinematic image prompt snippets and QA targets
  prompt_h_prompt_architect_repair:
    node: PromptArchitect
    api: Fireworks Chat
    endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    model: accounts/fireworks/models/kimi-k2p5
    template_id: PROMPT_H_PROMPT_ARCHITECT_REPAIR
    purpose: strict repair retry when architect JSON is malformed
  prompt_i_sotaforge_final_image_prompt:
    node: SotaForge
    api: Fireworks Image
    endpoint: https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-1-schnell-fp8/text_to_image
    model: accounts/fireworks/models/flux-1-schnell-fp8
    template_id: PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT
    purpose: render final epoch image
artifacts:
  - tvc_multi_agent_db/api_call_trace.jsonl
  - tvc_multi_agent_db/paid_api_policy_check.json
```

### 04.1 Mandatory Policy Check (every node change)
- Confirm no new paid API path is introduced outside Fireworks for MODE_NARRATE.
- Confirm existing free services remain operational and not replaced with paid alternatives.

### 04.3 Provider Resilience Policy (Fireworks)
```yaml
fireworks_resilience_policy:
  wrapper: smart_retry
  retry_config_default:
    base: 2.0
    max_delay: 60
    max_retries: 5
  classifiers:
    retryable:
      - 429
      - 503
      - timeout/network transient
      behavior: exponential_backoff_with_jitter
    precondition_412:
      behavior: open_circuit_breaker
      window_seconds: 120
      effect: fail_fast_for_endpoint_during_window
    invalid_request_400:
      behavior:
        - one_sanitized_retry
        - then_permanent_failure_for_payload
  telemetry_artifact:
    - tvc_multi_agent_db/runs/<run_id>/provider_resilience_report.json
```

### 04.4 Trace Artifacts (per run)
```yaml
required_trace_artifacts:
  - tvc_multi_agent_db/api_call_trace.jsonl
  - tvc_multi_agent_db/paid_api_policy_check.json
required_trace_fields:
  - timestamp
  - node
  - call_type
  - endpoint_host
  - model
  - prompt_template_id
  - prompt_preview
minimum_expected_template_presence:
  USER_CONTEXT_path:
    - PROMPT_D_WRITER_SCRIPT_DRAFT
    - PROMPT_TOPIC_EXTRACTOR_CALLOUTS
    - PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT
    - PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING
    - PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS
    - PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT
  YOUTUBE_HARVEST_path:
    - PROMPT_A_HARVESTER_QUERY_OPTIMIZER
    - PROMPT_D_WRITER_SCRIPT_DRAFT
    - PROMPT_TOPIC_EXTRACTOR_CALLOUTS
    - PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT
    - PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING
    - PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS
    - PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT
optional_repair_templates:
  - PROMPT_TOPIC_EXTRACTOR_REPAIR
  - PROMPT_F_SCENE_DIRECTOR_REPAIR
  - PROMPT_G_AUDIO_VTT_TO_EPOCH_REPAIR
  - PROMPT_H_PROMPT_ARCHITECT_REPAIR
```

## 05-FAILURE-MODES
| ID | Status | Location | Signature | Impact | Mitigation Direction |
|---|---|---|---|---|---|
| FM-001 | Resolved (2026-03-08) | Harvester fallback | `fireworks_chat_completion() got multiple values for argument 'contents'` during synthetic pivot | fallback intelligence could fail on YouTube block | fixed synthetic pivot call signature + model argument mapping |
| FM-002 | Resolved (2026-03-09) | SotaForge -> Editor | `Missing image asset for epoch X` when all attempts fail and no temp promoted | render previously could fail hard | deterministic per-epoch guarantee added (`generated` -> `copied_previous` -> local placeholder) + Editor preflight materialization gate |
| FM-003 | Mitigated/Open | TopicExtractor -> Editor | `after_sentence` can exceed epoch count in some scene-collapsed runs | overlay mismatch risk reduced; out-of-range card rows now skipped safely in Editor | keep strict callout normalization + editor index guard; consider epoch-aware remap post-Audio if perfect alignment is required |
| FM-015 | Resolved (2026-03-09) | TopicExtractor -> Editor | topic-card timing collapse (`after_sentence` mostly all `1`) rendered all callouts at once | callout stack at frame start reduced readability and looked incorrect | added collapse detector + deterministic index rebalance in TopicExtractor and strict one-at-a-time callout scheduler in Editor |
| FM-004 | Resolved (2026-03-08) | Audio resume -> PromptArchitect | Audio resume return path omitted `total_epochs` in older builds | downstream KeyError was possible | resume path now returns normalized contract including `total_epochs`, `images_forged`, `qa_attempts`; validated in deterministic `A1` + 4 E2E runs |
| FM-005 | Non-blocking (user) | Duration gate | output often >22s despite requested 20s | target duration drift | deprioritized per current user preference |
| FM-006 | Open external (degraded-safe) | Fireworks image endpoint | frequent 400/429/412 responses | intermittent image generation instability (non-fatal when fallback image guarantee succeeds) | provider resilience wrapper + deterministic image guarantee + per-run resilience telemetry |
| FM-007 | Open external (intermittent) | Fireworks text endpoint | `412 PRECONDITION_FAILED` during Writer/synthetic text calls | can fail full run before scene/audio/image stages | keep retry behavior and monitor account/billing health; rerun after each failure |
| FM-008 | Closed (tooling) | Integrity runner | asset path false negatives in evaluator | incorrect defect reporting | evaluator fixed to use `tvc_multi_agent_db/assets` |
| FM-009 | Mitigated (2026-03-08) | SceneDirector JSON parse | `Expecting value: line 1 column 1 (char 0)` from malformed/empty scene payloads | previous builds could hard-fail pipeline | added guarded parse + strict repair retry + deterministic scene fallback; validated in `SD1/SD2` and 4 E2E runs with no SceneDirector hard crash |
| FM-010 | Resolved (2026-03-08) | Writer cache resume contract | cache-resume path omitted `duration_attempts` key | deterministic Writer contract check could fail and duration loop accounting inconsistent | cache-resume return updated to always include `duration_attempts` |
| FM-011 | Resolved (2026-03-08) | Source routing ambiguity | implicit precedence between `context_summary` and `harvested_intelligence` could mask source intent | accidental mixed-source runs and unclear provenance | explicit `input_source` contract + fail-closed guards in Harvester/Writer + CLI context routing |
| FM-012 | Mitigated (2026-03-08) | Writer generation quality | meta-prompt leakage in narration (`system message`, `user message`, self-reasoning) | wrong-topic or unusable voiceover script could propagate to full render | added Writer fail-closed validator + strict retry + hard-stop; tracked in `writer_quality_report.json` |
| FM-013 | Resolved (2026-03-08) | Harvester quality gate | low-relevance YouTube transcripts previously accepted if text length was high | off-topic videos could be generated despite valid runtime/render | added strict relevant-transcript threshold and hard-stop on insufficient relevance; no synthetic replacement in default YOUTUBE mode |
| FM-014 | Resolved (2026-03-09) | Artifact storage policy | root mutable artifacts were overwritten run-to-run | forensic history and deterministic replay were degraded | run-ID namespacing default + latest pointer + opt-in legacy mirror (`TVC_LEGACY_MIRROR=1`) |

## 06-NODE-DOSSIERS

### N01 Harvester -> harvester_node
```yaml
role: Gather intelligence from YouTube transcripts, cache by prompt hash, and provide text grounding for writing.
consumes:
  required: [request_prompt]
  optional: [input_source, context_summary]
mode_behavior:
  USER_CONTEXT:
    action: skip_youtube_harvest
    returns: status=harvest_skipped_user_context
  YOUTUBE_HARVEST:
    action: youtube_multi_pass_with_relevance_scoring_and_strict_halt
    returns: harvested_intelligence + status
produces:
  state_keys: [harvested_intelligence, status]
  artifacts:
    - tvc_multi_agent_db/yt_harvest/*.vtt
    - tvc_multi_agent_db/harvested_intelligence.txt
    - tvc_multi_agent_db/harvester_run_report.json
    - tvc_multi_agent_db/harvester_quality_report.json
    - tvc_multi_agent_db/state_manifest.json
  status_values: [harvested, harvest_skipped_user_context, hard_stop_insufficient_relevance]
downstream_dependencies:
  - Writer grounding context (direct or summarized)
prompt_template_ids:
  - PROMPT_A_HARVESTER_QUERY_OPTIMIZER
failure_signatures:
  - yt-dlp HTTP 429 or sign-in block
  - repeated 429 streak reaching hard-block threshold
  - no_subtitles_written across candidate pool
  - relevant transcript count below strict threshold
safe_edit_zones:
  - query prompt shaping
  - adaptive pass controller (target_vtt_count/max_candidates/max_passes/per_video_retries)
  - transcript relevance scoring and request-intent matching
  - transcript parsing/cleanup
  - cache invalidation rules
  - strict quality-gate and hard-stop messaging
red_lines:
  - never remove harvested_intelligence output key
  - USER_CONTEXT mode must not proceed with prefilled harvested_intelligence
  - YOUTUBE_HARVEST mode must hard-stop when relevant transcript threshold is not met
validation_checkpoints:
  - recoverable path should target >=5 VTT transcripts and enforce minimum relevant transcript threshold
  - `harvested_intelligence` must be built from relevance-passing transcripts only
  - vtt count logged
  - harvester_run_report includes cooldown durations, retry counts, and failure signatures (`no_subtitles_written` included)
  - harvester_quality_report includes per-transcript relevance scores and gate verdict
  - cache-resume path only accepted when cached intelligence passes min-length AND relevant transcript threshold
  - insufficient relevance path raises explicit hard-stop quality-gate error
```

### N02 Writer -> writer_node
```yaml
role: Produce narration script from prompt/context and prosody-process for speech.
consumes:
  required: [request_prompt, target_duration, input_source]
  optional: [context_summary, harvested_intelligence, status, duration_attempts]
produces:
  state_keys: [script, status, duration_attempts]
  artifacts:
    - tvc_multi_agent_db/master_script.txt
    - tvc_multi_agent_db/writer_quality_report.json
    - tvc_multi_agent_db/state_manifest.json
  status_values: [drafted]
downstream_dependencies:
  - DurationGate word/time gating
  - TopicExtractor sentence indexing
  - SceneDirector semantic segmentation
  - Audio narration clarity
prompt_template_ids:
  - PROMPT_D_WRITER_SCRIPT_DRAFT
  - PROMPT_E_WRITER_CPP_PROSODY
failure_signatures:
  - script length explosion after CPP
  - context starvation when grounding absent
  - meta-prompt leakage into final narration script
safe_edit_zones:
  - prompt constraints for script generation
  - explicit source contract (`USER_CONTEXT` uses `context_summary`, `YOUTUBE_HARVEST` uses `harvested_intelligence`, fail-closed on conflicts)
  - bounded context forwarding logic
  - smart punctuation normalization before ASCII sanitize
  - duration_fail rewrite-note behavior
  - CPP guardrails
  - post-CPP length clamp behavior
red_lines:
  - keep return shape stable (script/status/duration_attempts)
  - preserve sentence-per-line format expectation for downstream
  - explicit source mode must fail on mixed-source payloads
validation_checkpoints:
  - Harvester handoff context appears in Writer request when `input_source=YOUTUBE_HARVEST`
  - Writer fails closed on mixed source payloads
  - Writer fails closed when declared source payload is missing
  - `validation_profile` must be `user_context_context_priority` for USER_CONTEXT and `youtube_context_priority` for YOUTUBE_HARVEST
  - USER_CONTEXT validation is context-first (`low_context_alignment` gate); request overlap is informational
  - cache-resume path returns `duration_attempts` and skips model call
  - cache-resume script is revalidated before reuse
  - duration-fail path emits rewrite behavior and increments `duration_attempts`
  - CPP overshoot guard reverts to pre-CPP draft when processed text balloons
  - length clamp enforces <= 1.2x target words
  - hard-stop occurs after strict retry when meta-leak or alignment checks fail
  - script non-empty and coherent
  - word count in reasonable range for target duration
```

### N03 DurationGate -> duration_gate
```yaml
role: Enforce duration envelope and route rewrite loop.
consumes:
  required: [script, duration_attempts]
  optional: [target_duration]
produces:
  state_keys: [status] or [script, status]
  artifacts:
    - tvc_multi_agent_db/master_script.txt (forced truncation path)
  status_values: [duration_pass, duration_fail]
downstream_dependencies:
  - route control to Writer vs TopicExtractor
failure_signatures:
  - excessive looping
  - aggressive truncation quality loss
safe_edit_zones:
  - tolerance and truncation strategy
red_lines:
  - must preserve status values used by route_duration
validation_checkpoints:
  - pass/fail routing works
  - no infinite bounce between nodes
```

### N04 TopicExtractor -> topic_extractor
```yaml
role: Derive on-screen topic callouts anchored to script sentence indices.
consumes:
  required: [script]
  optional: []
produces:
  state_keys: [topic_callouts, status]
  artifacts:
    - tvc_multi_agent_db/topic_callouts.json
    - tvc_multi_agent_db/topic_callout_quality_report.json
  status_values: [topics_extracted]
downstream_dependencies:
  - Editor topic-card layer timing
prompt_template_ids:
  - PROMPT_TOPIC_EXTRACTOR_CALLOUTS
  - PROMPT_TOPIC_EXTRACTOR_REPAIR
failure_signatures:
  - malformed/empty primary model JSON output
  - repair retry still unusable
  - callout index out of range vs epoch count (FM-003; mitigated in Editor)
  - malformed callout schema
safe_edit_zones:
  - extraction constraints
  - one-shot repair retry path
  - strict normalization (uppercase, <=20 chars, dedupe, clamped integer index)
  - collapse detector + deterministic index rebalance when callout indices collapse to a dominant sentence
  - deterministic grounded fallback from script text
  - grounding filters
  - sentence index normalization
red_lines:
  - do not emit callouts without after_sentence integer index
  - do not persist unvalidated cached callouts
validation_checkpoints:
  - invalid cached `topic_callouts.json` must be rejected and regenerated
  - collapsed timing distributions are rebalanced deterministically and persisted
  - malformed primary payload triggers exactly one strict repair retry
  - deterministic local fallback is used only if both primary + repair are unusable
  - after_sentence indices normalized to valid script sentence range; out-of-range epoch mappings are safely skipped by Editor guard
  - callout count sensible for script length
```

### N05 SceneDirector -> scene_director
```yaml
role: Segment script into visual scenes and generate style/meta/character manifest.
consumes:
  required: [script]
  optional: []
produces:
  state_keys: [visual_scenes, style_dna, meta_context, character_manifest, status]
  optional_state_keys: [epochs]
  artifacts:
    - tvc_multi_agent_db/scene_manifest.json
  status_values: [scenes_directed]
downstream_dependencies:
  - Audio scene-to-VTT alignment
  - PromptArchitect style and subject continuity
prompt_template_ids:
  - PROMPT_F_SCENE_DIRECTOR_SEGMENTATION
  - PROMPT_F_SCENE_DIRECTOR_REPAIR
failure_signatures:
  - malformed/empty scene JSON
  - schema-missing payload (no `scenes`)
  - poor segmentation causing timing mismatch
safe_edit_zones:
  - guarded parse + schema normalization
  - scene segmentation prompt + strict repair retry
  - fallback segmentation behavior
red_lines:
  - preserve scene ids and textual grounding
validation_checkpoints:
  - no hard crash on malformed SceneDirector payload
  - scene ids contiguous
  - each scene has text and visual_intent
  - `scene_audio_prompt_report.json` contains SceneDirector source + contract verdict
```

### N06 Audio -> audio_engineer
```yaml
role: Generate narration audio + VTT and map scene boundaries to precise epochs.
consumes:
  required: [script, visual_scenes]
  optional: []
produces:
  state_keys: [audio_path, vtt_path, epochs, status]
  optional_state_keys: [total_epochs, images_forged, qa_attempts]
  artifacts:
    - master_narration.mp3
    - tvc_multi_agent_db/narration.vtt
    - tvc_multi_agent_db/vtt_matrix.json
    - tvc_multi_agent_db/audio_stage_report.json
    - tvc_multi_agent_db/scene_audio_prompt_report.json
    - tvc_multi_agent_db/state_manifest.json
  status_values: [audio_forged, failed]
downstream_dependencies:
  - PromptArchitect uses total_epochs and epochs
  - Editor uses epochs timing
prompt_template_ids:
  - PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT
  - PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING
  - PROMPT_G_AUDIO_VTT_TO_EPOCH_REPAIR
failure_signatures:
  - malformed VTT->epoch mapping output
  - VTT/epoch mismatch
safe_edit_zones:
  - resume-return normalization and parity with fresh return path
  - pre-edge_tts stage pipeline (ingress -> neural cpp -> local cpp fallback -> sanitize)
  - VTT parsing robustness
  - alignment prompt + repair retry + deterministic local mapping
red_lines:
  - keep epoch timing keys: start_time, end_time, duration
validation_checkpoints:
  - total_epochs present for downstream
  - epochs count > 0 and monotonic timing
  - `audio_stage_report.json` records stage-by-stage source decisions
  - `scene_audio_prompt_report.json` records mapping source + contract verdict
```

### N07 PromptArchitect -> prompt_architect
```yaml
role: Convert epochs into SOTA image prompts and QA targets with style/context injection.
consumes:
  required: [epochs, script, total_epochs]
  optional: [style_dna, meta_context, character_manifest]
produces:
  state_keys: [sota_prompts, qa_targets, status]
  artifacts:
    - tvc_multi_agent_db/master_prompts.json
    - tvc_multi_agent_db/state_manifest.json
  status_values: [prompts_architected]
downstream_dependencies:
  - SotaForge generation prompts and refinement
prompt_template_ids:
  - PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS
  - PROMPT_H_PROMPT_ARCHITECT_REPAIR
failure_signatures:
  - malformed prompt JSON from model
  - invalid cached prompt payload
  - prompt count < epoch count
safe_edit_zones:
  - schema repair retry + fallback logic
  - cache validation before resume
  - style/context injection rules
red_lines:
  - prompt count must align with epochs
validation_checkpoints:
  - len(sota_prompts) == len(epochs)
  - len(qa_targets) == len(epochs)
  - `scene_audio_prompt_report.json` contains PromptArchitect source + parity verdict
```

### N08 SotaForge -> sota_vision_forge
```yaml
role: Generate per-epoch images, perform recursive QA/refinement, and set deterministic image paths.
consumes:
  required: [epochs, sota_prompts, total_epochs]
  optional: [qa_targets]
produces:
  state_keys: [status, qa_scores, images_forged, epochs]
  artifacts:
    - tvc_multi_agent_db/assets/epoch_*.png
  status_values: [sota_vision_complete]
downstream_dependencies:
  - Editor requires image availability for each epoch
prompt_template_ids:
  - PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT
  - PROMPT_J_SOTA_FORGE_VISUAL_QA
failure_signatures:
  - Fireworks 400/429/412 responses (FM-006)
  - historical: missing image for an epoch when no temp image to promote (FM-002, now resolved)
safe_edit_zones:
  - retry strategy and fallback promotion logic
  - deterministic per-epoch fallback ladder (`generated` -> `copied_previous` -> `placeholder`)
  - cache validity checks + real QA re-check on cache-resume
  - QA score parser and threshold gate (`qa_pass_threshold=4.0`)
red_lines:
  - each epoch must leave with resolvable image_path or deterministic fallback
  - never auto-pass a cached/generated image without a real parsed QA score
validation_checkpoints:
  - image exists for every epoch before Editor
  - each epoch exposes `image_source` telemetry (`generated`, `copied_previous`, `placeholder`)
  - qa_scores length equals epochs length
  - QA accept condition is strict: `has_real_score == true AND score >= 4.0`
```

### N09 Editor -> lead_editor
```yaml
role: Build dual-layer ASS overlays and render synchronized video using ffmpeg filter graph.
consumes:
  required: [audio_path, epochs, target_output]
  optional: [topic_callouts, watermark_mode]
produces:
  state_keys: [status, final_video] or [errors, status]
  artifacts:
    - tvc_multi_agent_db/typography.ass
    - tvc_multi_agent_db/filter.txt
    - tvc_multi_agent_db/editor_overlay_report.json
    - <target_output>.mp4
  status_values: [rendered, render_failed]
downstream_dependencies:
  - Verifier audio/video and telemetry checks
failure_signatures:
  - missing image asset abort
  - xfade offset mismatch if epochs malformed
safe_edit_zones:
  - ASS generation details
  - ffmpeg filter construction
  - preflight image materialization check per epoch before ffmpeg
  - one-at-a-time topic card scheduler with deterministic overflow handling
  - centered watermark style/event composition and ornament symmetry
red_lines:
  - xfade offset source must remain epoch start_time
  - audio track mapping must remain stable
validation_checkpoints:
  - render success
  - no missing-image abort when placeholder generation succeeds
  - no overlapping topic card windows in `typography.ass`
  - watermark mode `on` writes centered `WatermarkTag` event + mirrored line ornaments
  - watermark mode `off` writes no watermark events
  - filter offsets align with epochs
```

### N10 Verifier -> whisper_verifier
```yaml
role: Verify final A/V drift and script-vs-VTT telemetry consistency.
consumes:
  required: [target_output, audio_path, script, vtt_path]
  optional: []
produces:
  state_keys: [verification_report, status]
  artifacts:
    - tvc_multi_agent_db/verification_report.json
  status_values: [complete]
downstream_dependencies:
  - final mission success reporting
failure_signatures:
  - drift > 1s
  - telemetry_pass false
safe_edit_zones:
  - tolerance and parsing resilience
red_lines:
  - must emit verification_report consistently
validation_checkpoints:
  - verified true for accepted run
  - report includes drift/script_words/vtt_words/telemetry_pass
```

## 07-CHANGE-GUARDRAILS
### 07.1 Pre-change checklist (for every node)
- Read this node dossier in `06-NODE-DOSSIERS`.
- Read `05-FAILURE-MODES` and latest snapshot delta in `09-EVIDENCE-LINKS`.
- Confirm `04-API-BOUNDARY` policy check (Fireworks-only paid API for NARRATE).
- Confirm active source mode intent for this run (`USER_CONTEXT` vs `YOUTUBE_HARVEST`).
- Identify upstream state keys consumed and downstream keys impacted.
- Define exact rollback target for this node before editing.

### 07.2 Post-change checklist (for every node)
- Run full NARRATE validation matrix (3 prompts) with full pipeline.
- Confirm sync and routing invariants I01-I09 remain valid.
- Confirm no new paid API path appears in NARRATE.
- Confirm `regression_assertions.json` passes:
  - `RG-001`: Writer USER_CONTEXT deterministic-default path intact.
  - `RG-002`: Audio deterministic-first mapping path intact.
- Update `05-FAILURE-MODES` and `10-CHANGELOG`.
- If invariant fails, rollback node change and document cause/mitigation.
- For Harvester specifically, include S4 forced-total-failure test and verify exact hard-stop message text.
- For Writer/Harvester specifically, include mixed-source fail-closed assertion and declared-source-missing assertion.

## 08-VALIDATION-PROTOCOL
```yaml
validation_profile:
  mode: MODE_NARRATE
  run_count: 3
  prompt_set:
    - OpenAI agentic coding workflows in 2026
    - Codex vs local coding agents for enterprise teams
    - Multimodal reasoning and tool-using AI systems in production
  command_template: python supreme_commander.py "--mode MODE_NARRATE --duration 20 <TOPIC>"
  dual_source_contract_commands:
    - python supreme_commander.py "--mode MODE_NARRATE --duration 20 --context \"<USER_TEXT>\" <TOPIC>"
    - python supreme_commander.py "--mode MODE_NARRATE --duration 20 <TOPIC>"
```

### 08.1 Blocking gates (current priority)
- Render success and artifact exists.
- `verification_report.verified == true`.
- `verification_report.drift <= 1.0`.
- `verification_report.telemetry_pass == true`.
- Epoch integrity: monotonic timing and resolvable image coverage per epoch.
- Transition integrity: `filter.txt` xfade offsets match epoch `start_time`.
- Callout integrity: valid indices and bounded topic-card windows.
- Source contract integrity: declared source mode accepted only with valid source payload and no mixed-source acceptance.
- Trace integrity: `api_call_trace.jsonl` includes node/template entries for executed model calls.
- Paid API policy: `paid_api_policy_check.passed == true`.

### 08.2 Non-blocking gate (temporarily relaxed by user)
- Duration envelope `18-22s` is informative, not blocking for current workstream.

### 08.3 Operational dry-run simulation (notes-only, no code change)
- Simulated node: `N06 Audio`.
- Steps executed in protocol terms: pre-checklist -> expected contract checks -> post-checklist mapping.
- Result: checklist is decision-complete and executable without additional assumptions.

### 08.4 Dual-source validation artifacts (current standard)
- `run_assertions.json` for log-level source selection markers.
- `dual_source_contract_checks.json` for deterministic fail-closed and CLI precedence checks.
- `trace_summary.json` for prompt-template and host-level trace coverage.
- `regression_assertions.json` for must-not-regress checks (RG-001/RG-002).

### 08.5 Namespacing + CLI hardening checks
- `NS-1`: with `TVC_LEGACY_MIRROR=0`, legacy root mutable artifacts remain unchanged.
- `NS-2`: with `TVC_LEGACY_MIRROR=1`, legacy root mutable artifacts mirror run outputs for compatibility.
- `CLI-1`: malformed `--context-file/--context` fails closed with explicit parse error.
- `CLI-2`: valid quoted context-file paths (including spaces) resolve correctly.
- `CLI-3`: `--context-file` precedence over `--context` is preserved.
- Evidence artifact: [optimization_validation_20260309.json](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/optimization_validation_20260309.json)

### 08.6 Node time-share audit protocol
- Primary target run (frozen): `20260308_203455`.
- Audit runner: [time_audit_runner.py](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/time_audit_runner.py).
- Frozen bundle output root: [time_audit_runs/20260308_203455](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/time_audit_runs/20260308_203455).
- Required outputs per audit run:
  - `node_time_share.json`
  - `node_time_share.csv`
  - `node_time_share.md`
  - `methodology.md`
  - `repeatability_report.json`
- Forward-proof instrumentation artifact (new): `tvc_multi_agent_db/node_timing_trace.jsonl`.
- Confidence policy:
  - `A` trace-span supported
  - `B` artifact-boundary supported
  - `C` inferred/embedded

## 09-EVIDENCE-LINKS
### 09.1 Current baseline snapshot pointer
- Active baseline run (callout scheduler + placeholder watermark fix verified): [run_20260309_113841](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_113841)
- Active narration-style baseline run (human_story mode with style-seeded visual prompts and verifier pass): [run_20260309_124725](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_124725)
- Narration-style validation matrix:
  - documentary (USER_CONTEXT): [run_20260309_123510](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_123510)
  - sales_saas (USER_CONTEXT): [run_20260309_122328](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_122328)
  - human_story (USER_CONTEXT): [run_20260309_124725](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_124725)
  - sales_saas forced rewrite path (`context_rewrite=force`): [run_20260309_124510](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_124510)
- Deterministic fix checks: [callout_fix_deterministic_report_20260309.json](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/callout_fix_deterministic_report_20260309.json)
- Full matrix companions:
  - USER_CONTEXT 20s: [run_20260309_102214](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_102214)
  - USER_CONTEXT 120s: [run_20260309_102548](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_102548)
  - YOUTUBE_HARVEST 20s: [run_20260309_103502](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_103502)
- Regression assertions reference: [run_20260309_105506/regression_assertions.json](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_105506/regression_assertions.json)
- Provider resilience reference: [run_20260309_104007/provider_resilience_report.json](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_104007/provider_resilience_report.json)
- Legacy mirror policy checks: [optimization_validation_20260309.json](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/optimization_validation_20260309.json)
- Active latest pointer artifact: [latest_run_pointer.json](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/latest_run_pointer.json)

### 09.2 Historical snapshots
- Node1 + Writer guard deterministic reliability bundle (H1/H2/H3/W1): [20260308_201555](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_writer_guard_runs/20260308_201555)
- Scene/Audio/Prompt reliability bundle: [20260308_175444](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/scene_audio_prompt_reliability_runs/20260308_175444)
- Prior dual-source routing bundle: [20260308_161616](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/dual_source_sanity/20260308_161616)
- Prior full-sync baseline bundle: [20260308_110639](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/sync_integrity_runs/20260308_110639)
- [20260308_110224](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/sync_integrity_runs/20260308_110224)
- [20260308_105946](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/sync_integrity_runs/20260308_105946)
- Harvester reliability pass bundle: [20260308_124401](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_124401)
- NARRATE smoke bundle: [20260308_124455](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_124455)
- Iran run A (live pull + 429 fallback): [20260308_130213](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_130213)
- Iran run B (cache-resume, full success): [20260308_130345](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_130345)
- Harvester push-harder reliability pass bundle (S1-S5): [20260308_134937](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_134937)
- Harvester push-harder E2E runs: [20260308_135343](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_135343)
- Writer reliability pass bundle (W1-W7 + 3 live runs): [20260308_151056](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/writer_reliability_runs/20260308_151056)
- Dual-source routing sanity bundle (USER_CONTEXT + YOUTUBE_HARVEST + trace/policy artifacts): [20260308_161616](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/dual_source_sanity/20260308_161616)
- Node1 + Writer guard deterministic reliability bundle (H1/H2/H3/W1): [20260308_195636](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_writer_guard_runs/20260308_195636)
- Stand-up live run 1 (strict Harvester relevance halt): [node1_live_standup_120s_run1.log](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_live_standup_120s_run1.log)
- Stand-up live run 2 (Writer fail-closed meta leak halt): [node1_live_standup_120s_run2.log](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_live_standup_120s_run2.log)
- Stand-up live run 3 (strict Harvester relevance halt): [node1_live_standup_120s_run3.log](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_live_standup_120s_run3.log)
- Stand-up live run post-fix (full success): [node1_live_standup_120s_postfix.log](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_live_standup_120s_postfix.log)
- Scene cardinality guard check artifact: [scene_cardinality_guard_check_20260308.json](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/scene_cardinality_guard_check_20260308.json)
- USER_CONTEXT deterministic-writer + run-namespaced-artifacts + deterministic-first-audio smoke: [run_20260309_095157](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_095157)
- Highest-value optimization matrix bundle set:
  - [run_20260309_102214](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_102214)
  - [run_20260309_102548](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_102548)
  - [run_20260309_103502](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_103502)
  - [run_20260309_104007](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_104007)
- Namespacing compatibility checks:
  - mirror enabled: [run_20260309_105418](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_105418)
  - mirror disabled: [run_20260309_105506](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_105506)
- Callout stack + placeholder watermark fix validation:
  - rerun with one-at-a-time callout scheduling: [run_20260309_113841](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_113841)
  - deterministic unit-style checks bundle: [callout_fix_deterministic_report_20260309.json](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/callout_fix_deterministic_report_20260309.json)

### 09.3 Known Open Defects (linked to evidence)
| Defect ID | Evidence Link | Notes |
|---|---|---|
| FM-003 | [topic extractor integration report](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/topic_extractor_reliability_runs/20260308_171101/integration/integration_report.json) | primary issue mitigated by strict normalization + editor index guard; remains open for future epoch-aware remap enhancement. |
| FM-006 | [run_20260309_104007 provider resilience](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_104007/provider_resilience_report.json) | Fireworks image endpoint still returns repeated 400 bursts; now downgraded to degraded-safe because deterministic image fallback keeps pipeline renderable. |
| FM-007 | [run_20260309_104007 provider resilience](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_104007/provider_resilience_report.json) | Fireworks text 412 remains an external intermittent risk; circuit-breaker now fails fast for 120s and avoids noisy retry storms. |

## 10-CHANGELOG
| Timestamp | Entry | Snapshot |
|---|---|---|
| 2026-03-08 | Created master system-memory notes with fixed sections 00-10, full node dossiers, API boundary, guardrails, validation protocol, and snapshot-linked defect registry. | [20260308_110639](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/sync_integrity_runs/20260308_110639) |
| 2026-03-08 | Updated Harvester operational policy: retry-heavy fallback ladder + explicit hard-stop on degraded output; FM-001 marked resolved. | `harvester_reliability_runs/<latest>` |
| 2026-03-08 | Harvester reliability harness updated with deterministic blocked-YouTube Fireworks shim for S3, expected hard-stop handling for S4, and terminal capture on exceptions; latest strict verdict PASS. | [20260308_124401](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_124401) |
| 2026-03-08 | Full MODE_NARRATE smoke reached Writer and failed due Fireworks `412 PRECONDITION_FAILED` (billing/account suspension), logged as FM-007 external blocker. | [20260308_124455](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_124455) |
| 2026-03-08 | Iran-focused run A: Harvester handled YouTube subtitle `429` with successful synthetic pivot; Writer then failed with Fireworks `412`. Iran-focused run B: Harvester cache-resume path succeeded and full pipeline rendered final MP4. | [20260308_130345](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_130345) |
| 2026-03-08 | Implemented Node 1 push-harder adaptive multi-pass harvest loop (target 5 transcripts, adaptive cooldown/retry, strict fallback order) and added `harvester_run_report.json`; reliability runner upgraded to S1-S5 with PASS verdict. | [20260308_134937](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_134937) |
| 2026-03-08 | Ran 2 full MODE_NARRATE smoke tests post-change: run A success with 5 transcript harvest and final video; run B harvested 5 transcripts but failed later in SceneDirector parse (FM-009). | [20260308_135343](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/harvester_reliability_runs/20260308_135343) |
| 2026-03-08 | Added Writer reliability harness (`W1-W7` deterministic + 3 live runs), validated Harvester->Writer forwarding precedence/guards, and achieved `Writer Perfect = PASS` under hybrid attribution policy. | [20260308_151056](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/writer_reliability_runs/20260308_151056) |
| 2026-03-08 | Implemented dual-source routing: explicit `USER_CONTEXT` path skips YouTube Harvester, default `YOUTUBE_HARVEST` path feeds Writer from `harvested_intelligence`; Writer now fail-closes on mixed/missing source payloads. Added per-call prompt/API tracing and paid API policy artifact. | `api_call_trace.jsonl + paid_api_policy_check.json` |
| 2026-03-08 | Validated dual-source behavior with live full runs and deterministic guard tests; both source modes confirmed in logs and trace templates, with paid host policy passing on Fireworks-only endpoints. | [20260308_161616](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/dual_source_sanity/20260308_161616) |
| 2026-03-08 | Methodical master-notes consolidation: moved baseline pointer to dual-source bundle, codified source-routing contract/invariants, expanded prompt ownership per node, and added stateless-agent boot protocol. | [20260308_161616](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/dual_source_sanity/20260308_161616) |
| 2026-03-08 | TopicExtractor reliability hardening implemented: strict callout normalization, one-shot repair retry, deterministic grounded fallback, cache validation on resume, and editor-side defensive index guard. Deterministic scenarios T1-T5 passed; integration validation passed with non-topic failure attribution for the failed YouTube run. | [20260308_171101](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/topic_extractor_reliability_runs/20260308_171101) |
| 2026-03-08 | Joint hardening completed for SceneDirector/Audio/PromptArchitect: guarded SceneDirector parse with strict repair retry + deterministic fallback, Audio resume contract normalized (`total_epochs` always present), explicit pre-`edge_tts` stage telemetry + local CPP fallback, VTT mapping repair + deterministic local mapper, PromptArchitect cache validation + repair retry + parity enforcement. Deterministic scenarios SD1/SD2/A1/A2/A3/PA1/PA2 passed and 4/4 E2E runs passed. | [20260308_175444](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/scene_audio_prompt_reliability_runs/20260308_175444) |
| 2026-03-08 | Implemented strict Node1/Writer anti-regression controls: Harvester now enforces relevant-transcript thresholds and hard-stops on insufficient YouTube relevance (no synthetic replacement in default YOUTUBE mode), Writer now fail-closes on meta-prompt leakage after one strict retry, and SceneDirector deterministic fallback now enforces long-form multi-scene cardinality. Deterministic H1/H2/H3/W1 bundle passed; live stand-up runs now halt safely instead of producing off-topic/fake video outputs. | [20260308_195636](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_writer_guard_runs/20260308_195636) |
| 2026-03-08 | Revalidated Node1/Writer guardrail behavior with fresh deterministic bundle (`H1/H2/H3/W1` all passed) and completed a full 120s YouTube-mode stand-up render. Harvester handled real 429 events with cooldown/retry, met strict relevance gate, Writer rejected first meta-leak draft and succeeded on strict retry, scene cardinality fallback preserved multi-image coverage, Verifier passed (`drift=0.002667`, `verified=true`), and paid API policy remained Fireworks-only. | [20260308_201555](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node1_writer_guard_runs/20260308_201555) |
| 2026-03-08 | Implemented retroactive high-confidence node time-share audit for the latest successful 120s run (`20260308_203455`) with frozen evidence bundle, 10-node + macro percentage outputs, methodology doc, and repeatability checks on two prior successful runs. Added forward per-node timing instrumentation at orchestrator level producing `node_timing_trace.jsonl` for future exact audits. | [20260308_203455](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/time_audit_runs/20260308_203455) |
| 2026-03-08 | Verified forward timing instrumentation in a live `MODE_NARRATE --duration 20` smoke run (`USER_CONTEXT`). `node_timing_trace.jsonl` captured start/end for all 10 nodes with monotonic durations and run_id correlation. | [node_timing_trace_smoke_20260308.log](D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/node_timing_trace_smoke_20260308.log) |
| 2026-03-09 | Implemented highest-leverage sequence `1 -> 5 -> 3`: Writer now defaults to deterministic direct-script generation in `USER_CONTEXT` mode (LLM path only when deterministic quality gate fails or rewrite is required), artifacts are now run-ID namespaced under `tvc_multi_agent_db/runs/<run_id>` with compatibility mirrors, and Audio now uses deterministic-first VTT epoch mapping with optional LLM refine acceptance. Smoke run passed with Fireworks-only paid host policy. | [run_20260309_095157](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_095157) |
| 2026-03-09 | Completed remaining optimization set: Writer validation now context-priority for `USER_CONTEXT` with smart punctuation normalization, FM-002 closed via deterministic image guarantee + Editor preflight, Fireworks resilience wrapper/circuit telemetry enabled, SceneDirector strict cardinality guard strengthened, CLI context parser hardened fail-closed, and namespacing compatibility verified for both `TVC_LEGACY_MIRROR=1` and `0`. 4-run E2E matrix + operational checks passed with Fireworks-only paid host policy. | [run_20260309_104007](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_104007) |
| 2026-03-09 | Fixed callout stack bug and placeholder watermark leak: TopicExtractor now detects/rebalances collapsed `after_sentence` distributions, Editor enforces strict one-at-a-time topic card scheduling with `editor_overlay_report.json`, and deterministic placeholder frames no longer render text watermark by default. Reproduced on the original failing USER_CONTEXT scenario with successful render and verifier pass. | [run_20260309_113841](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_113841) |
| 2026-03-09 | Added explicit narration-style runtime controls for MODE_NARRATE: `--narration-style` (`documentary`, `sales_saas`, `human_story`) and `--context-rewrite` (`off`, `force`). Style profile registry now drives Writer persona, Audio edge_tts params (rate/pitch/volume), SceneDirector style defaults, PromptArchitect tone hints, and style-safe cache keys for Writer/Scene/Audio/PromptArchitect. Regression gate RG-001 updated to allow explicit forced rewrite in USER_CONTEXT mode. | [run_20260309_124510](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_124510) |
| 2026-03-09 | Tightened SotaForge QA truthfulness gate: cache resume now requires a real Fireworks visual QA score (no auto `10.0` cache pass), generated/cached frames are accepted only when `has_real_score=true` and `score>=4.0`, and fail-closed behavior remains in effect on QA outages. | [tvc_langgraph_core.py](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_langgraph_core.py) |
| 2026-03-09 | Added Watermark Mode for MODE_NARRATE with default `on`: new `--watermark-mode on|off` CLI flag, state propagation into orchestrator manifest, and Editor ASS overlay support for fixed text `linkedin.com/in/nilhandemel` at exact screen center (`x=960,y=540`) with deterministic AI-hue styling and mirrored ornamental lines. `editor_overlay_report.json` now includes a `watermark` telemetry block. | [tvc_langgraph_core.py](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_langgraph_core.py) |
| 2026-03-09 | Added run heartbeat observability: `live_status.txt` + `live_status.json` are now updated throughout execution with current node, retry state, elapsed time, and ETA. Retry waits now update status each second during backoff, and completion/failure is finalized in heartbeat artifacts. | [tvc_langgraph_core.py](D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_langgraph_core.py) |

## 11-STATELESS-AGENT-BOOT
### 11.1 Mandatory Read Order (before touching code)
1. `00-SYSTEM-INTENT`
2. `02.3 Source-Routing Contract`
3. `04.2 Prompt/API Map (locked)`
4. `05-FAILURE-MODES`
5. `06-NODE-DOSSIERS` for target node
6. `09.1 Current baseline snapshot pointer`

### 11.2 Fast Reality Check Commands (non-mutating)
```powershell
# Confirm active run pointer and baseline artifacts
Get-Content D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/latest_run_pointer.json
Get-Content D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_113841/paid_api_policy_check.json
Get-Content D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_113841/provider_resilience_report.json

# Confirm must-not-regress assertions and namespacing/CLI hardening evidence
Get-Content D:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/runs/20260309_113841/regression_assertions.json
Get-Content D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/optimization_validation_20260309.json
Get-Content D:/AI-Apps-In-Drive/App_Station/Video_production/Evidence/callout_fix_deterministic_report_20260309.json
```

### 11.3 Source Selection Decision Table
| Operator Intent | Flags | Expected `input_source` | Harvester Behavior | Writer Source |
|---|---|---|---|---|
| User provides source text (non-YouTube) | `--context-file` or `--context` | `USER_CONTEXT` | skip YouTube; return `harvest_skipped_user_context` | `context_summary` only |
| Default documentary from web/YouTube context | no context flags | `YOUTUBE_HARVEST` | adaptive YouTube harvest + strict relevance gate (hard-stop on insufficient relevance) | `harvested_intelligence` only |

### 11.4 Documentation Update Rule (strict)
- After any node change or observed runtime behavior change:
  - update `05-FAILURE-MODES` (open/resolved/intermittent status),
  - update `09-EVIDENCE-LINKS` with exact run bundle paths,
  - append a `10-CHANGELOG` entry with date, behavior delta, and evidence link.
- Do not treat verbal claims as truth; only update status using artifact-backed evidence.
