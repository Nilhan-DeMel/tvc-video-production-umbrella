import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Tuple

from tvc_nodes.contracts import TopicExtractorInput, TopicExtractorOutput
from tvc_nodes.services import TopicExtractorServices


def _topic_sentences(script_text: str) -> List[str]:
    text = str(script_text or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        sentences: List[str] = []
        for ln in lines:
            parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", ln) if s.strip()]
            if parts:
                sentences.extend(parts)
            else:
                sentences.append(ln)
        if sentences:
            return sentences
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _topic_to_headline(text: str, max_len: int = 20) -> str:
    clean = re.sub(r"[^A-Za-z0-9 ]+", " ", str(text or "").upper())
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return ""
    if len(clean) <= max_len:
        return clean
    trimmed = clean[:max_len]
    if " " in trimmed and len(clean) > max_len and clean[max_len:max_len + 1] != " ":
        trimmed = trimmed.rsplit(" ", 1)[0]
    trimmed = trimmed.strip()
    return trimmed if trimmed else clean[:max_len].strip()


def _normalize_topic_callouts(raw_callouts: Any, script_text: str, max_topics: int = 6) -> List[dict]:
    if not isinstance(raw_callouts, list):
        return []

    script_lower = str(script_text or "").lower()
    sentence_count = max(1, len(_topic_sentences(script_text)))
    normalized: List[dict] = []
    seen = set()

    for item in raw_callouts:
        if not isinstance(item, dict):
            continue

        topic = _topic_to_headline(item.get("topic", ""), max_len=20)
        if not topic:
            continue

        raw_after = item.get("after_sentence", 1)
        try:
            if isinstance(raw_after, bool):
                raise ValueError("bool-not-allowed")
            if isinstance(raw_after, str):
                after_sentence = int(float(raw_after.strip()))
            else:
                after_sentence = int(raw_after)
        except Exception:
            after_sentence = 1
        after_sentence = max(1, min(after_sentence, sentence_count))

        if script_lower:
            topic_lower = topic.lower()
            keywords = [w for w in re.findall(r"[a-z0-9']+", topic_lower) if len(w) > 3]
            grounded = (topic_lower in script_lower) or any(w in script_lower for w in keywords)
        else:
            grounded = topic == "BREAKING NEWS"

        if not grounded or topic in seen:
            continue
        seen.add(topic)
        normalized.append({"topic": topic, "after_sentence": after_sentence})
        if len(normalized) >= max_topics:
            break

    return normalized


def _build_deterministic_topic_fallback(script_text: str) -> List[dict]:
    fallback = []
    seen = set()
    for idx, sentence in enumerate(_topic_sentences(script_text)[:6], start=1):
        topic = _topic_to_headline(sentence, max_len=20)
        if not topic or topic in seen:
            continue
        seen.add(topic)
        fallback.append({"topic": topic, "after_sentence": idx})
        if len(fallback) >= 3:
            break
    if fallback:
        return fallback
    return [{"topic": "BREAKING NEWS", "after_sentence": 1}]


def _callout_index_distribution(callouts: List[dict]) -> Dict[str, int]:
    distribution: Dict[str, int] = {}
    for item in callouts:
        try:
            idx = int(item.get("after_sentence", 1))
        except Exception:
            idx = 1
        key = str(idx)
        distribution[key] = distribution.get(key, 0) + 1
    return distribution


def _repair_collapsed_topic_callouts(callouts: List[dict], script_text: str) -> Tuple[List[dict], dict]:
    sentence_count = max(1, len(_topic_sentences(script_text)))
    pre_distribution = _callout_index_distribution(callouts)
    count = len(callouts)
    dominant_idx = None
    dominant_count = 0
    for key, value in pre_distribution.items():
        if value > dominant_count:
            dominant_idx = key
            dominant_count = value

    dominant_ratio = (dominant_count / float(max(1, count))) if count else 0.0
    collapse_detected = sentence_count > 1 and count >= 3 and dominant_ratio >= 0.8
    report = {
        "detected": bool(collapse_detected),
        "rebalanced": False,
        "reason": "",
        "sentence_count": sentence_count,
        "callout_count": count,
        "dominant_index": dominant_idx,
        "dominant_ratio": round(dominant_ratio, 4),
        "pre_distribution": pre_distribution,
        "post_distribution": pre_distribution,
    }

    if not collapse_detected:
        return callouts, report

    repaired: List[dict] = []
    step_den = float(max(1, count - 1))
    prev_idx = 0
    for i, item in enumerate(callouts):
        target = 1 + int(round(i * (sentence_count - 1) / step_den))
        target = max(1, min(sentence_count, target))
        if count <= sentence_count and target <= prev_idx:
            target = min(sentence_count, prev_idx + 1)
        prev_idx = target
        repaired.append(
            {
                "topic": item.get("topic", ""),
                "after_sentence": target,
            }
        )

    post_distribution = _callout_index_distribution(repaired)
    report["rebalanced"] = bool(repaired != callouts)
    report["reason"] = "dominant_index_collapse_rebalanced"
    report["post_distribution"] = post_distribution
    return repaired, report


def _persist_topic_quality(
    services: TopicExtractorServices,
    source: str,
    pre_repair: List[dict],
    final_callouts: List[dict],
    collapse_report: dict,
    cache_resume: bool,
    deterministic_user_context_mode: bool,
    script_hash: str,
    sentence_count: int,
) -> None:
    quality_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "cache_resume": bool(cache_resume),
        "api_bypassed": bool(deterministic_user_context_mode),
        "bypass_reason": "deterministic_user_context_mode" if deterministic_user_context_mode else "",
        "script_hash": script_hash,
        "script_sentence_count": sentence_count,
        "pre_distribution": _callout_index_distribution(pre_repair),
        "post_distribution": _callout_index_distribution(final_callouts),
        "collapse_repair": collapse_report,
        "callout_count": len(final_callouts),
        "topics": [c.get("topic", "") for c in final_callouts],
    }
    services.artifacts.write_json("topic_callout_quality_report.json", quality_report, mirror_legacy=None)


def _persist_topic_diagnostics(
    services: TopicExtractorServices,
    diagnostics: dict,
    final_source: str,
    final_callouts: List[dict],
) -> None:
    diagnostics["final_selected_source"] = final_source
    diagnostics["final_callout_count"] = len(final_callouts or [])
    try:
        services.artifacts.write_json("topic_extractor_diagnostics.json", diagnostics, mirror_legacy=None)
    except Exception:
        pass


def run_topic_extractor(
    node_input: TopicExtractorInput,
    services: TopicExtractorServices,
) -> TopicExtractorOutput:
    script_text = str(node_input.script or "")
    deterministic_user_context_mode = services.is_deterministic_user_context_mode(
        {
            "input_source": node_input.input_source,
            "context_rewrite": node_input.context_rewrite,
        }
    )
    script_hash = services.get_hash(script_text)
    manifest = services.manifest.load() or {}
    topic_file = services.artifacts.read_path("topic_callouts.json")
    sentence_count = max(1, len(_topic_sentences(script_text)))
    diagnostics = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "node": "TopicExtractor",
        "api_bypassed": bool(deterministic_user_context_mode),
        "bypass_reason": "deterministic_user_context_mode" if deterministic_user_context_mode else "",
        "first_response_char_count": 0,
        "first_response_sha256_16": "",
        "primary_repair_success": False,
        "primary_repair_reason": "",
        "repair_retry_success": False,
        "repair_retry_reason": "",
        "final_selected_source": "",
        "final_callout_count": 0,
    }

    if (not deterministic_user_context_mode) and manifest.get("topic_script_hash") == script_hash and os.path.exists(topic_file):
        try:
            with open(topic_file, "r", encoding="utf-8") as handle:
                cached_raw = json.load(handle)
                cached_callouts = _normalize_topic_callouts(cached_raw, script_text)
            pre_repair = list(cached_callouts)
            cached_callouts, collapse_report = _repair_collapsed_topic_callouts(cached_callouts, script_text)
            if cached_callouts:
                if cached_callouts != cached_raw:
                    services.artifacts.write_json("topic_callouts.json", cached_callouts, mirror_legacy=None)
                _persist_topic_quality(
                    services,
                    "cache_resume",
                    pre_repair,
                    cached_callouts,
                    collapse_report,
                    cache_resume=True,
                    deterministic_user_context_mode=deterministic_user_context_mode,
                    script_hash=script_hash,
                    sentence_count=sentence_count,
                )
                diagnostics["primary_repair_reason"] = "cache_resume_used"
                _persist_topic_diagnostics(services, diagnostics, "cache_resume", cached_callouts)
                print("    [RESUMING] Valid topics found for this script. Skipping Extractor API call.")
                return TopicExtractorOutput(topic_callouts=cached_callouts, status="topics_extracted")
            print("    [TOPIC EXTRACTOR] Cached topics invalid. Regenerating...")
        except Exception as exc:
            print(f"    [TOPIC EXTRACTOR] Cache read failed: {exc}")

    prompt = f"""Extract up to 4-6 key topic headlines from this documentary script.

These will appear as bold on-screen title cards during the video.

GROUNDING RULE: Every topic MUST be a verbatim phrase or key term that literally appears in the script text.

Do NOT invent or infer topics. If the script has fewer than 4 clear topics, just return fewer.

Return ONLY a JSON array of objects with "topic" (short uppercase headline, MAX 20 CHARACTERS) and "after_sentence" (the sentence number after which this topic should appear, 1-indexed).

Script:

{script_text}"""

    callouts: List[dict] = []
    primary_reason = ""
    source_label = "primary"

    if deterministic_user_context_mode:
        source_label = "deterministic_primary"
        callouts = _normalize_topic_callouts(_build_deterministic_topic_fallback(script_text), script_text)
        diagnostics["primary_repair_success"] = True
        diagnostics["primary_repair_reason"] = "deterministic_local_primary"
        print("    [TOPIC EXTRACTOR] Fireworks bypassed. Using deterministic local callout extraction.")
    else:
        try:
            response = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=prompt,
                config=services.generate_content_config(
                    system_instruction="You are a strict text extraction engine. ABSOLUTE RULE: Every 'topic' you return MUST be a verbatim phrase that physically appears in the provided script text. You are FORBIDDEN from inventing topics. Return strict JSON array only. No markdown.",
                    temperature=0.1,
                ),
                prompt_template_id="PROMPT_TOPIC_EXTRACTOR_CALLOUTS",
                trace_node="TopicExtractor",
            )
            primary_text = str(response.text or "").strip()
            diagnostics["first_response_char_count"] = len(primary_text)
            if primary_text:
                diagnostics["first_response_sha256_16"] = hashlib.sha256(primary_text.encode("utf-8")).hexdigest()[:16]
            primary_raw = services.json_repair(primary_text)
            callouts = _normalize_topic_callouts(primary_raw, script_text)
            if not callouts:
                primary_reason = "primary_output_unusable"
                diagnostics["primary_repair_success"] = False
                diagnostics["primary_repair_reason"] = primary_reason
            else:
                diagnostics["primary_repair_success"] = True
                diagnostics["primary_repair_reason"] = "primary_json_repair_ok"
        except Exception as exc:
            primary_reason = f"primary_parse_error: {exc}"
            diagnostics["primary_repair_success"] = False
            diagnostics["primary_repair_reason"] = primary_reason

    if primary_reason:
        print(f"    [TOPIC EXTRACTOR] Primary extraction needs repair ({primary_reason}). Running strict repair retry...")
        repair_prompt = f"""Re-run topic extraction with strict schema compliance.

Return ONLY a JSON array of objects:
[{{"topic":"UPPERCASE PHRASE <= 20 CHARACTERS","after_sentence":1}}]

STRICT RULES:
- Topics must come directly from words/phrases in the script.
- No invented topics.
- after_sentence must be integer, 1-indexed.
- Return 1 to 6 items, or fewer if script has fewer clear topics.

Script:
{script_text}"""
        try:
            repair_response = services.smart_retry(
                services.fireworks_chat_completion,
                "fireworks_llm",
                contents=repair_prompt,
                config=services.generate_content_config(
                    system_instruction="Return strict JSON array only. No markdown. No prose. No comments.",
                    temperature=0.0,
                ),
                prompt_template_id="PROMPT_TOPIC_EXTRACTOR_REPAIR",
                trace_node="TopicExtractor",
            )
            repair_raw = services.json_repair((repair_response.text or "").strip())
            callouts = _normalize_topic_callouts(repair_raw, script_text)
            if callouts:
                source_label = "repair_retry"
                diagnostics["repair_retry_success"] = True
                diagnostics["repair_retry_reason"] = "repair_retry_json_ok"
            else:
                diagnostics["repair_retry_success"] = False
                diagnostics["repair_retry_reason"] = "repair_retry_output_unusable"
        except Exception as exc:
            diagnostics["repair_retry_success"] = False
            diagnostics["repair_retry_reason"] = f"repair_retry_failed:{str(exc)[:220]}"
            print(f"    [TOPIC EXTRACTOR] Repair retry failed: {exc}")

    if not callouts:
        source_label = "deterministic_fallback"
        callouts = _normalize_topic_callouts(_build_deterministic_topic_fallback(script_text), script_text)
        if not callouts:
            callouts = [{"topic": "BREAKING NEWS", "after_sentence": 1}]
        print("    [TOPIC EXTRACTOR] Using deterministic local fallback callouts.")

    pre_repair = list(callouts)
    callouts, collapse_report = _repair_collapsed_topic_callouts(callouts, script_text)
    if collapse_report.get("rebalanced"):
        print(
            "    [TOPIC EXTRACTOR] Rebalanced collapsed callout indices: "
            f"{collapse_report.get('pre_distribution')} -> {collapse_report.get('post_distribution')}"
        )

    print(f"    [TOPIC EXTRACTOR] Extracted {len(callouts)} verified callouts: {[c['topic'] for c in callouts]}")

    services.artifacts.write_json("topic_callouts.json", callouts, mirror_legacy=None)
    _persist_topic_quality(
        services,
        source_label,
        pre_repair,
        callouts,
        collapse_report,
        cache_resume=False,
        deterministic_user_context_mode=deterministic_user_context_mode,
        script_hash=script_hash,
        sentence_count=sentence_count,
    )
    _persist_topic_diagnostics(services, diagnostics, source_label, callouts)

    manifest["topic_script_hash"] = script_hash
    services.manifest.save(manifest)
    return TopicExtractorOutput(topic_callouts=callouts, status="topics_extracted")
