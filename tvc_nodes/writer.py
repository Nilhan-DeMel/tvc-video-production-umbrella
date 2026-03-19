import os
import re
from dataclasses import asdict
from typing import Dict, List

from tvc_nodes.contracts import WriterInput, WriterOutput
from tvc_nodes.services import WriterServices

_WRITER_META_LEAK_PATTERNS = [
    r"\bsystem message\b",
    r"\buser message\b",
    r"\bconversation history\b",
    r"\bprompt structure\b",
    r"\byour own thought process\b",
    r"\bas an ai\b",
    r"\bi would\b",
]


def _compact_context_for_writer(text: str, services: WriterServices, max_chars: int = 2500) -> str:
    cleaned = services.clean_transcript_text(text)
    if not cleaned:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    selected: List[str] = []
    current_len = 0
    for sentence in sentences:
        if len(sentence.split()) < 4:
            continue
        if selected and sentence.lower() == selected[-1].lower():
            continue
        if current_len + len(sentence) + 1 > max_chars:
            break
        selected.append(sentence)
        current_len += len(sentence) + 1
        if len(selected) >= 24:
            break
    if not selected:
        return cleaned[:max_chars]
    return " ".join(selected)[:max_chars]


def _writer_meta_leak_hits(text: str) -> List[str]:
    low = str(text or "").lower()
    hits = []
    for pattern in _WRITER_META_LEAK_PATTERNS:
        if re.search(pattern, low):
            hits.append(pattern)
    return hits


def _validate_writer_script(
    script_text: str,
    request_prompt: str,
    writer_context: str,
    input_source: str,
    services: WriterServices,
) -> dict:
    script = services.sanitize_tts_script(script_text)
    script_tokens = services.word_token_set(script)
    request_terms = services.meaningful_terms(request_prompt, min_len=4, max_terms=20)
    context_terms = services.meaningful_terms(writer_context, min_len=4, max_terms=36)
    meta_hits = _writer_meta_leak_hits(script)

    req_hits = [t for t in request_terms if t in script_tokens]
    ctx_hits = [t for t in context_terms if t in script_tokens]
    req_overlap = len(req_hits) / float(max(1, len(request_terms)))
    ctx_overlap = len(ctx_hits) / float(max(1, len(context_terms)))

    reasons = []
    if meta_hits:
        reasons.append("meta_prompt_leak")
    source_mode = str(input_source or "").upper()
    if source_mode != "USER_CONTEXT" and len(req_hits) < 2 and req_overlap < 0.12:
        reasons.append("low_request_alignment")
    if source_mode == "YOUTUBE_HARVEST" and len(ctx_hits) < 2 and ctx_overlap < 0.05:
        reasons.append("low_context_alignment")
    if source_mode == "USER_CONTEXT" and len(ctx_hits) < 2 and ctx_overlap < 0.05:
        reasons.append("low_context_alignment")
    if len(script.split()) < 30:
        reasons.append("script_too_short")

    return {
        "valid": len(reasons) == 0,
        "reasons": reasons,
        "meta_hits": meta_hits,
        "word_count": len(script.split()),
        "request_overlap": round(req_overlap, 4),
        "context_overlap": round(ctx_overlap, 4),
        "request_hit_count": len(req_hits),
        "context_hit_count": len(ctx_hits),
        "request_hits": req_hits[:12],
        "context_hits": ctx_hits[:12],
    }


def run_writer(node_input: WriterInput, services: WriterServices) -> WriterOutput:
    state = asdict(node_input)
    duration_meta = services.duration_meta_from_state(state)
    target_secs = int(duration_meta.get("effective_planning_duration_seconds", 60) or 60)
    narration_style = services.normalize_narration_style(node_input.narration_style or services.narration_style_default)
    context_rewrite = services.normalize_context_rewrite(node_input.context_rewrite or "auto")
    deterministic_user_context_mode = services.is_deterministic_user_context_mode(state)
    style_profile = services.narration_profile(narration_style)
    if str(duration_meta.get("duration_mode", "manual")) == "auto":
        est = duration_meta.get("estimated_duration_seconds")
        est_note = f" (~{est}s estimated)" if est is not None else ""
        print(
            f"    [WRITER] Drafting SOTA {style_profile.get('label', narration_style)} script "
            f"(Auto duration from script{est_note})..."
        )
    else:
        print(
            f"    [WRITER] Drafting SOTA {style_profile.get('label', narration_style)} script (Target: {target_secs}s)..."
        )

    manifest = services.manifest.load() or {}
    script_read_file = services.artifacts.read_path("master_script.txt")
    target_words = int(target_secs * 2.5)
    if node_input.status == "duration_fail":
        print("    [WRITER] [REWRITE] Adjusting for duration mismatch...")
        rewrite_note = (
            f" IMPORTANT: Your previous draft was too long/short. FOCUS on EXACTLY {target_words} words."
        )
    else:
        rewrite_note = ""

    input_source = str(node_input.input_source or "").strip().upper()
    context_summary_text = str(node_input.context_summary or "").strip()
    harvested = str(node_input.harvested_intelligence or "").strip()

    if input_source == "USER_CONTEXT":
        if harvested:
            raise RuntimeError(
                "Source conflict: USER_CONTEXT mode cannot include harvested_intelligence in Writer."
            )
        if not context_summary_text:
            raise RuntimeError(
                "Source missing: USER_CONTEXT mode requires non-empty context_summary for Writer."
            )
        writer_context = context_summary_text
        selected_source = "context_summary"
    elif input_source == "YOUTUBE_HARVEST":
        if context_summary_text:
            raise RuntimeError(
                "Source conflict: YOUTUBE_HARVEST mode cannot include context_summary in Writer."
            )
        if not harvested:
            raise RuntimeError(
                "Source missing: YOUTUBE_HARVEST mode requires non-empty harvested_intelligence for Writer."
            )
        writer_context = _compact_context_for_writer(harvested, services, max_chars=2500)
        selected_source = "harvested_intelligence"
    else:
        if context_summary_text:
            writer_context = context_summary_text
            selected_source = "context_summary"
        elif harvested:
            writer_context = _compact_context_for_writer(harvested, services, max_chars=2500)
            selected_source = "harvested_intelligence"
        else:
            writer_context = "General Documentary"
            selected_source = "legacy_fallback"

    script_hash = services.get_hash(
        f"{node_input.request_prompt}|{input_source or 'LEGACY'}|{selected_source}|"
        f"{style_profile.get('cache_key', narration_style)}|{context_rewrite}|{services.get_hash(writer_context)}"
    )
    print(f"    [WRITER] Context source selected: {selected_source}")
    print(f"    [WRITER] Narration style selected: {narration_style} | context_rewrite={context_rewrite}")
    context_block = f"\n\nContext for focus: {writer_context}"

    writer_quality_report: Dict[str, object] = {
        "timestamp": "",
        "request_prompt": node_input.request_prompt,
        "input_source": input_source or "LEGACY",
        "narration_style": narration_style,
        "context_rewrite": context_rewrite,
        "style_profile": style_profile.get("label", narration_style),
        "validation_profile": "user_context_context_priority" if input_source == "USER_CONTEXT" else "youtube_context_priority",
        "selected_source": selected_source,
        "duration_mode": duration_meta.get("duration_mode"),
        "requested_target_duration_seconds": duration_meta.get("requested_target_duration_seconds"),
        "estimated_duration_seconds": duration_meta.get("estimated_duration_seconds"),
        "effective_planning_duration_seconds": target_secs,
        "actual_audio_duration_seconds": duration_meta.get("actual_audio_duration_seconds"),
        "target_duration": target_secs,
        "target_words": target_words,
        "cache_resume_checked": False,
        "cache_resume_used": False,
        "attempts": [],
        "deterministic_clamp_policy": "disabled" if deterministic_user_context_mode else "unchanged",
        "pre_cpp_word_count": None,
        "post_cpp_word_count": None,
        "clamp_applied": False if deterministic_user_context_mode else None,
        "final_status": "pending",
        "final_reason": "",
    }

    def persist_writer_report() -> None:
        writer_quality_report["timestamp"] = writer_quality_report.get("timestamp") or ""
        services.artifacts.write_json(
            "writer_quality_report.json",
            writer_quality_report,
            mirror_legacy=None,
        )

    cpp_mode = str(services.getenv("TVC_WRITER_CPP_MODE", "local") or "local").strip().lower()
    prefer_local_cpp = cpp_mode != "neural"
    writer_quality_report["cpp_mode"] = "local_deterministic" if prefer_local_cpp else "neural_fireworks"

    def apply_cpp_and_clamp(raw_script: str) -> str:
        if prefer_local_cpp:
            print("    [CPP] Local deterministic CPP active.")
            processed_script = services.sanitize_tts_script(services.apply_cpp(raw_script))
            if not processed_script:
                processed_script = raw_script
        else:
            print("    [CPP] Executing Neural Prosody Preprocessor...")
            cpp_sys = (
                "You are a SOTA prosody engineer for AI Speech. Your ONLY job is to optimize this script for natural human-like pacing by removing or replacing 'breath-breaking' commas. "
                f"STYLE GOAL: {style_profile.get('writer_cpp_goal', '')} "
                "RULE 1: Preserve all clause-boundary commas (e.g., 'Meanwhile, Alibaba...', or 'It architects, and it...'). "
                "RULE 2: Remove all serial commas and internal-clause commas that would cause a robotic, stuttering pace. "
                "RULE 3: Do NOT change the words. Only the punctuation. Stop only at sentence-end periods. "
                "Output ONLY the raw processed text."
            )
            cpp_res = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=raw_script,
                config=services.generate_content_config(
                    system_instruction=cpp_sys,
                    temperature=0.1,
                ),
                prompt_template_id="PROMPT_E_WRITER_CPP_PROSODY",
                trace_node="Writer",
            )
            processed_script = str(cpp_res.text or "").strip()

        base_wc = len(raw_script.split())
        proc_wc = len(processed_script.split())
        if base_wc > 0 and proc_wc > int(base_wc * 1.5):
            print(f"    [CPP] Overshoot detected ({proc_wc} vs {base_wc} words). Reverting to pre-CPP draft.")
            processed_script = raw_script

        if _writer_meta_leak_hits(processed_script) and not _writer_meta_leak_hits(raw_script):
            print("    [CPP] Meta-leak introduced during prosody pass. Reverting to pre-CPP draft.")
            processed_script = raw_script

        final_words = processed_script.split()
        max_writer_words = int(target_words * 1.2)
        if len(final_words) > max_writer_words:
            clipped = " ".join(final_words[:max_writer_words])
            sentence_cut = re.search(r".*[.!?]", clipped)
            processed_script = sentence_cut.group(0).strip() if sentence_cut else clipped
            print(
                f"    [WRITER] Length clamp applied ({len(final_words)} -> {len(processed_script.split())} words)."
            )
        return processed_script

    def local_user_context_fallback_script(disable_clamp: bool = False) -> str:
        base_script = services.sanitize_tts_script(context_summary_text)
        if not base_script:
            return ""

        lines: List[str] = []
        for ln in base_script.split("\n"):
            t = ln.strip()
            if not t:
                continue
            if re.fullmatch(r"\[[^\]]+\]", t):
                continue
            lines.append(t)
        if lines:
            base_script = "\n".join(lines)
        pre_cpp_words = len(base_script.split())

        processed_script = services.sanitize_tts_script(services.apply_cpp(base_script))
        if not processed_script:
            processed_script = base_script

        post_cpp_words = len(processed_script.split())
        if disable_clamp:
            writer_quality_report["deterministic_clamp_policy"] = "disabled"
            writer_quality_report["pre_cpp_word_count"] = pre_cpp_words
            writer_quality_report["post_cpp_word_count"] = post_cpp_words
            writer_quality_report["clamp_applied"] = False
            return processed_script

        final_words = processed_script.split()
        max_writer_words = int(target_words * 1.2)
        clamp_applied = False
        if len(final_words) > max_writer_words:
            clipped = " ".join(final_words[:max_writer_words])
            sentence_cut = re.search(r".*[.!?]", clipped)
            processed_script = sentence_cut.group(0).strip() if sentence_cut else clipped
            clamp_applied = True
            print(
                f"    [WRITER] USER_CONTEXT fallback clamp applied ({len(final_words)} -> {len(processed_script.split())} words)."
            )
        writer_quality_report["pre_cpp_word_count"] = pre_cpp_words
        writer_quality_report["post_cpp_word_count"] = len(processed_script.split())
        writer_quality_report["clamp_applied"] = clamp_applied
        return processed_script

    if (
        not deterministic_user_context_mode
        and manifest.get("writer_prompt_hash") == script_hash
        and os.path.exists(script_read_file)
        and node_input.status != "duration_fail"
    ):
        writer_quality_report["cache_resume_checked"] = True
        try:
            with open(script_read_file, "r", encoding="utf-8") as handle:
                cached_script = handle.read()
            cache_quality = _validate_writer_script(
                cached_script,
                node_input.request_prompt,
                writer_context,
                input_source or "LEGACY",
                services,
            )
            writer_quality_report["cache_quality"] = cache_quality
            if cache_quality.get("valid"):
                writer_quality_report["cache_resume_used"] = True
                writer_quality_report["final_status"] = "pass"
                writer_quality_report["final_reason"] = "cache_resume_valid"
                persist_writer_report()
                print("    [RESUMING] Valid script found for this prompt. Skipping Writer.")
                return WriterOutput(
                    script=cached_script,
                    status="drafted",
                    duration_attempts=int(node_input.duration_attempts or 0) + 1,
                    node_report=writer_quality_report,
                )
            print("    [WRITER] Cached script rejected by quality gate. Regenerating...")
        except Exception:
            pass

    if deterministic_user_context_mode:
        direct_script = local_user_context_fallback_script(disable_clamp=True)
        direct_quality = (
            _validate_writer_script(
                direct_script,
                node_input.request_prompt,
                writer_context,
                input_source or "LEGACY",
                services,
            )
            if direct_script
            else {"valid": False, "reasons": ["fallback_empty"], "word_count": 0}
        )
        writer_quality_report["deterministic_user_context_path"] = True
        writer_quality_report["deterministic_quality"] = direct_quality
        if direct_script and direct_quality.get("valid"):
            services.write_text_artifact("master_script.txt", direct_script, mirror_legacy=None)
            manifest["writer_prompt_hash"] = script_hash
            services.manifest.save(manifest)
            writer_quality_report["final_status"] = "pass"
            writer_quality_report["final_reason"] = "user_context_deterministic_default"
            persist_writer_report()
            print("    [WRITER] USER_CONTEXT deterministic direct-script path selected.")
            return WriterOutput(
                script=direct_script,
                status="drafted",
                duration_attempts=int(node_input.duration_attempts or 0) + 1,
                node_report=writer_quality_report,
            )
        writer_quality_report["final_status"] = "hard_stop"
        writer_quality_report["final_reason"] = ",".join(direct_quality.get("reasons", [])) or "user_context_deterministic_quality_failed"
        persist_writer_report()
        raise RuntimeError(
            "USER_CONTEXT deterministic script failed quality gate. "
            "Use --context-rewrite force only if you explicitly want model rewrite."
        )
    elif input_source == "USER_CONTEXT" and context_rewrite == "force" and node_input.status != "duration_fail":
        print("    [WRITER] USER_CONTEXT rewrite forced. Executing style-aware LLM drafting path.")

    latest_quality = {}
    for attempt in range(1, 3):
        strict_note = ""
        if attempt == 2:
            strict_note = (
                " CRITICAL: NEVER output meta reasoning. Never mention 'system message', 'user message', "
                "'conversation history', prompt structure, or your own thought process."
            )
        source_guard_note = ""
        if input_source == "USER_CONTEXT":
            source_guard_note = (
                " If rewriting USER_CONTEXT, preserve the original facts, chronology, and intent while adapting tone."
            )
        sys_inst = (
            f"You are {style_profile.get('writer_role', 'a master narration scriptwriter')}. "
            f"{style_profile.get('writer_tone_instruction', '')} "
            f"Write a highly engaging {style_profile.get('writer_output_label', 'voiceover narration')} of EXACTLY {target_words} words. "
            f"This MUST produce a {target_secs}-second voiceover when spoken at natural pace. "
            f"Output ONLY spoken narration text. No headers, no stage directions, no word counts. "
            f"Every sentence on its own line.{source_guard_note}{rewrite_note}{strict_note}"
        )
        try:
            res = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=f"{node_input.request_prompt}{context_block}",
                config=services.generate_content_config(
                    system_instruction=sys_inst,
                    temperature=float(style_profile.get("writer_temperature", 0.5)),
                ),
                prompt_template_id="PROMPT_D_WRITER_SCRIPT_DRAFT",
                trace_node="Writer",
            )
        except Exception as llm_err:
            llm_msg = str(llm_err).lower()
            if input_source == "USER_CONTEXT" and any(k in llm_msg for k in ["circuit open", "precondition", "412"]):
                fallback_script = local_user_context_fallback_script()
                if fallback_script and len(fallback_script.split()) >= 30:
                    services.write_text_artifact("master_script.txt", fallback_script, mirror_legacy=None)
                    manifest["writer_prompt_hash"] = script_hash
                    services.manifest.save(manifest)
                    writer_quality_report["fallback_mode"] = "user_context_provider_degraded_direct_script"
                    writer_quality_report["final_status"] = "pass"
                    writer_quality_report["final_reason"] = "provider_degraded_user_context_local_path"
                    persist_writer_report()
                    print("    [WRITER] Provider degraded; using deterministic USER_CONTEXT script path.")
                    return WriterOutput(
                        script=fallback_script,
                        status="drafted",
                        duration_attempts=int(node_input.duration_attempts or 0) + 1,
                        node_report=writer_quality_report,
                    )
            raise

        draft_script = str(res.text or "").strip()
        processed_script = apply_cpp_and_clamp(draft_script)
        quality = _validate_writer_script(
            processed_script,
            node_input.request_prompt,
            writer_context,
            input_source or "LEGACY",
            services,
        )
        writer_quality_report["attempts"].append(
            {
                "attempt": attempt,
                "strict_retry": attempt == 2,
                "word_count": quality.get("word_count", 0),
                "request_overlap": quality.get("request_overlap", 0.0),
                "context_overlap": quality.get("context_overlap", 0.0),
                "meta_hits": quality.get("meta_hits", []),
                "reasons": quality.get("reasons", []),
                "valid": bool(quality.get("valid", False)),
            }
        )
        latest_quality = quality

        if quality.get("valid"):
            services.write_text_artifact("master_script.txt", processed_script, mirror_legacy=None)
            manifest["writer_prompt_hash"] = script_hash
            services.manifest.save(manifest)
            writer_quality_report["final_status"] = "pass"
            writer_quality_report["final_reason"] = "quality_gate_passed"
            persist_writer_report()
            print(f"    [WRITER] Script forged ({len(processed_script.split())} words). Locked and loaded.")
            return WriterOutput(
                script=processed_script,
                status="drafted",
                duration_attempts=int(node_input.duration_attempts or 0) + 1,
                node_report=writer_quality_report,
            )

        print(
            f"    [WRITER] Quality gate rejected attempt {attempt}: {', '.join(quality.get('reasons', []))}"
        )

    if input_source == "USER_CONTEXT":
        reason_set = set(latest_quality.get("reasons", []))
        if reason_set and reason_set.issubset({"meta_prompt_leak", "low_request_alignment"}):
            fallback_script = local_user_context_fallback_script()
            fallback_quality = (
                _validate_writer_script(
                    fallback_script,
                    node_input.request_prompt,
                    writer_context,
                    input_source or "LEGACY",
                    services,
                )
                if fallback_script
                else {"valid": False, "reasons": ["fallback_empty"]}
            )

            if fallback_script and not _writer_meta_leak_hits(fallback_script) and len(fallback_script.split()) >= 30:
                services.write_text_artifact("master_script.txt", fallback_script, mirror_legacy=None)
                manifest["writer_prompt_hash"] = script_hash
                services.manifest.save(manifest)
                writer_quality_report["fallback_mode"] = "user_context_direct_script"
                writer_quality_report["fallback_quality"] = fallback_quality
                writer_quality_report["final_status"] = "pass"
                writer_quality_report["final_reason"] = "user_context_direct_fallback_after_meta_leak"
                persist_writer_report()
                print("    [WRITER] USER_CONTEXT direct-script fallback activated after meta-leak retries.")
                return WriterOutput(
                    script=fallback_script,
                    status="drafted",
                    duration_attempts=int(node_input.duration_attempts or 0) + 1,
                    node_report=writer_quality_report,
                )

    writer_quality_report["final_status"] = "hard_stop"
    writer_quality_report["final_reason"] = ",".join(latest_quality.get("reasons", [])) or "writer_quality_gate_failed"
    persist_writer_report()
    raise RuntimeError(
        f"Writer quality gate failed after strict retry: {writer_quality_report['final_reason']}"
    )
