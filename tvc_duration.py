from __future__ import annotations

import math
from typing import Any, Dict, Optional


DEFAULT_MANUAL_TARGET_DURATION = 60
DURATION_MODE_AUTO = "auto"
DURATION_MODE_MANUAL = "manual"

_STYLE_WPM = {
    "documentary": 150,
    "sales_saas": 165,
    "human_story": 132,
}


def normalize_narration_style(style: str) -> str:
    value = str(style or "documentary").strip().lower()
    if value not in _STYLE_WPM:
        return "documentary"
    return value


def normalize_context_rewrite(value: str) -> str:
    rewrite = str(value or "off").strip().lower()
    if rewrite not in {"off", "force"}:
        return "off"
    return rewrite


def normalize_input_source(value: str) -> str:
    source = str(value or "YOUTUBE_HARVEST").strip().upper()
    return source or "YOUTUBE_HARVEST"


def is_auto_duration_mode(input_source: str, context_rewrite: str) -> bool:
    return normalize_input_source(input_source) == "USER_CONTEXT" and normalize_context_rewrite(context_rewrite) != "force"


def estimate_duration_seconds(text: str, narration_style: str) -> Optional[int]:
    words = len([token for token in str(text or "").split() if token.strip()])
    if words <= 0:
        return None
    wpm = _STYLE_WPM.get(normalize_narration_style(narration_style), _STYLE_WPM["documentary"])
    seconds = int(math.ceil((words / float(wpm)) * 60.0))
    return max(1, seconds)


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def resolve_duration_plan(
    input_source: str,
    context_rewrite: str,
    narration_style: str,
    context_text: str,
    requested_target_duration: Any = None,
    actual_audio_duration: Any = None,
) -> Dict[str, Any]:
    duration_mode = DURATION_MODE_AUTO if is_auto_duration_mode(input_source, context_rewrite) else DURATION_MODE_MANUAL
    requested_seconds = _coerce_optional_int(requested_target_duration)
    estimated_seconds = estimate_duration_seconds(context_text, narration_style)
    actual_audio_seconds = _coerce_optional_float(actual_audio_duration)

    if duration_mode == DURATION_MODE_AUTO:
        requested_seconds = None
        effective_planning_seconds = int(estimated_seconds or DEFAULT_MANUAL_TARGET_DURATION)
        target_duration = None
    else:
        effective_planning_seconds = int(requested_seconds or DEFAULT_MANUAL_TARGET_DURATION)
        target_duration = effective_planning_seconds

    return {
        "duration_mode": duration_mode,
        "requested_target_duration_seconds": requested_seconds,
        "target_duration": target_duration,
        "estimated_duration_seconds": estimated_seconds,
        "effective_planning_duration_seconds": effective_planning_seconds,
        "actual_audio_duration_seconds": actual_audio_seconds,
    }
