import re
from typing import Any, Dict

from tvc_nodes.contracts import DurationGateInput, DurationGateOutput
from tvc_nodes.services import DurationGateServices


def _duration_payload(node_input: DurationGateInput) -> Dict[str, Any]:
    return {
        "input_source": node_input.input_source,
        "context_rewrite": node_input.context_rewrite,
        "script": node_input.script,
        "duration_attempts": node_input.duration_attempts,
        "duration_mode": node_input.duration_mode,
        "requested_target_duration_seconds": node_input.requested_target_duration_seconds,
        "estimated_duration_seconds": node_input.estimated_duration_seconds,
        "target_duration": node_input.target_duration,
        "actual_audio_duration_seconds": node_input.actual_audio_duration_seconds,
    }


def run_duration_gate(
    node_input: DurationGateInput,
    services: DurationGateServices,
) -> DurationGateOutput:
    input_source = str(node_input.input_source or "").strip().upper()
    context_rewrite = services.normalize_context_rewrite(node_input.context_rewrite)
    if input_source == "USER_CONTEXT" and context_rewrite != "force":
        print("[OK]  [DURATION GATE] BYPASS -- USER_CONTEXT deterministic channel (no rewrite loop).")
        return DurationGateOutput(status="duration_pass")

    word_count = len(str(node_input.script or "").split())
    expected_duration = word_count / 2.5
    duration_meta = services.duration_meta_from_state(_duration_payload(node_input))
    target = int(duration_meta.get("effective_planning_duration_seconds", 60) or 60)
    tolerance = 10

    if abs(expected_duration - target) <= tolerance:
        print(f"[OK]  [DURATION GATE] PASS -- {expected_duration:.0f}s within {tolerance}s of {target}s target.")
        return DurationGateOutput(status="duration_pass")

    if int(node_input.duration_attempts or 1) >= 3:
        words = str(node_input.script or "").split()
        force_limit = int(target * 2.7)
        primary_cutoff = " ".join(words[:force_limit])
        last_sentence = re.search(r".*[.!?]", primary_cutoff)
        if last_sentence:
            truncated = last_sentence.group(0).strip()
        else:
            truncated = primary_cutoff

        print(f"[WARN] [DURATION GATE] SOTA Graceful Truncation applied -- {len(truncated.split())} words.")
        services.write_text_artifact("master_script.txt", truncated, mirror_legacy=None)
        return DurationGateOutput(status="duration_pass", script=truncated)

    print(
        f" [DURATION GATE] REJECT -- {expected_duration:.0f}s vs {target}s target. "
        f"Sending back to Writer (attempt {node_input.duration_attempts})."
    )
    return DurationGateOutput(status="duration_fail")
