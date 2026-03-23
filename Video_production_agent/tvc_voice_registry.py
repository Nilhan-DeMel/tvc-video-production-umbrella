"""
TVC voice registry (agent repo only).

This is the single source of truth for selectable narration voices.
Primary execution remains Edge TTS for reliability. External-provider
presets are represented with deterministic fallbacks.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any


DEFAULT_VOICE_PRESET_ID = "style_default"
RATE_LIMITS = (-25.0, 25.0)
PITCH_LIMITS = (-12.0, 12.0)
VOLUME_LIMITS = (-20.0, 20.0)


VOICE_PRESETS: Dict[str, Dict[str, Any]] = {
    # Keeps current behavior: style profile in tvc_langgraph_core selects voice/rate/pitch/volume.
    "style_default": {
        "id": "style_default",
        "label": "Style Default (Current)",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": None,
        "rate": None,
        "pitch": None,
        "volume": None,
        "description": "Use narration-style profile defaults (current behavior).",
        "fallback_voice_preset": None,
    },
    "aria_premium": {
        "id": "aria_premium",
        "label": "Aria Premium",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-US-AriaNeural",
        "rate": "+2%",
        "pitch": "+1Hz",
        "volume": "+0%",
        "description": "Clean premium commercial female voice.",
        "fallback_voice_preset": "style_default",
    },
    "guy_explainer": {
        "id": "guy_explainer",
        "label": "Guy Explainer",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-US-GuyNeural",
        "rate": "+4%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "Energetic explainer male voice.",
        "fallback_voice_preset": "style_default",
    },
    "jenny_marketing": {
        "id": "jenny_marketing",
        "label": "Jenny Marketing",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-US-JennyNeural",
        "rate": "+6%",
        "pitch": "+2Hz",
        "volume": "+2%",
        "description": "Polished marketing female voice.",
        "fallback_voice_preset": "style_default",
    },
    "andrew_corporate": {
        "id": "andrew_corporate",
        "label": "Andrew Corporate",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-US-AndrewNeural",
        "rate": "+1%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "Corporate and clear male delivery.",
        "fallback_voice_preset": "style_default",
    },
    "libby_story": {
        "id": "libby_story",
        "label": "Libby Story",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-GB-LibbyNeural",
        "rate": "-6%",
        "pitch": "-1Hz",
        "volume": "+0%",
        "description": "Warm UK storytelling female voice.",
        "fallback_voice_preset": "style_default",
    },
    "sonia_warm": {
        "id": "sonia_warm",
        "label": "Sonia Warm",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-GB-SoniaNeural",
        "rate": "-4%",
        "pitch": "+1Hz",
        "volume": "+0%",
        "description": "Warm British tone for human stories.",
        "fallback_voice_preset": "style_default",
    },
    "natasha_broadcast": {
        "id": "natasha_broadcast",
        "label": "Natasha Broadcast",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-AU-NatashaNeural",
        "rate": "+2%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "Broadcast-news style female voice.",
        "fallback_voice_preset": "style_default",
    },
    "william_business": {
        "id": "william_business",
        "label": "William Business",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-AU-WilliamNeural",
        "rate": "+2%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "Business-ready Australian male voice.",
        "fallback_voice_preset": "style_default",
    },
    "christopher_confident": {
        "id": "christopher_confident",
        "label": "Christopher Confident",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-US-ChristopherNeural",
        "rate": "+3%",
        "pitch": "+0Hz",
        "volume": "+1%",
        "description": "Confident U.S. male narration.",
        "fallback_voice_preset": "style_default",
    },
    "neerja_global": {
        "id": "neerja_global",
        "label": "Neerja Global",
        "provider": "edge",
        "engine": "edge_tts",
        "voice": "en-IN-NeerjaNeural",
        "rate": "+1%",
        "pitch": "+1Hz",
        "volume": "+0%",
        "description": "Global English female voice.",
        "fallback_voice_preset": "style_default",
    },
    # ElevenLabs-style slot (scaffold only in this phase).
    "elevenlabs_premium_scaffold": {
        "id": "elevenlabs_premium_scaffold",
        "label": "ElevenLabs Premium (Scaffold)",
        "provider": "elevenlabs",
        "engine": "elevenlabs",
        "voice": "elevenlabs_voice_id_placeholder",
        "rate": "+0%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "SOTA external voice slot with deterministic edge fallback.",
        "fallback_voice_preset": "jenny_marketing",
    },
}


def voice_preset_ids() -> List[str]:
    return sorted(VOICE_PRESETS.keys())


def voice_preset_choices() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for key in voice_preset_ids():
        item = VOICE_PRESETS.get(key, {})
        out.append({"id": key, "label": str(item.get("label", key))})
    return out


def is_valid_voice_preset(value: str) -> bool:
    return str(value or "").strip() in VOICE_PRESETS


def _style_defaults(style_tts: Dict[str, str]) -> Dict[str, str]:
    style_tts = dict(style_tts or {})
    return {
        "voice": str(style_tts.get("voice", "en-GB-RyanNeural") or "en-GB-RyanNeural"),
        "rate": str(style_tts.get("rate", "+0%") or "+0%"),
        "pitch": str(style_tts.get("pitch", "+0Hz") or "+0Hz"),
        "volume": str(style_tts.get("volume", "+0%") or "+0%"),
    }


def _signed_value(token: Any, suffix: str) -> float:
    raw = str(token or "").strip()
    if not raw:
        return 0.0
    if raw.endswith(suffix):
        raw = raw[: -len(suffix)]
    try:
        return float(raw)
    except Exception:
        return 0.0


def _format_signed_value(value: float, suffix: str) -> str:
    rounded = round(float(value), 3)
    if abs(rounded - int(round(rounded))) < 0.001:
        rounded = int(round(rounded))
    sign = "+" if float(rounded) >= 0 else ""
    return f"{sign}{rounded}{suffix}"


def _merge_signed_token(base: Any, delta: Any, suffix: str, limits: tuple[float, float]) -> str:
    merged = _signed_value(base, suffix) + _signed_value(delta, suffix)
    lower, upper = limits
    merged = max(lower, min(upper, merged))
    return _format_signed_value(merged, suffix)


def _preset_overlay_tokens(preset: Dict[str, Any]) -> Dict[str, str]:
    return {
        "rate": str(preset.get("rate_delta", preset.get("rate", "+0%")) or "+0%"),
        "pitch": str(preset.get("pitch_delta", preset.get("pitch", "+0Hz")) or "+0Hz"),
        "volume": str(preset.get("volume_delta", preset.get("volume", "+0%")) or "+0%"),
    }


def _build_voice_payload(
    *,
    requested_preset: str,
    effective_preset_id: str,
    effective_preset_label: str,
    provider: str,
    engine: str,
    voice: str,
    style_base: Dict[str, str],
    preset_overlay: Dict[str, str],
    fallback_used: bool,
    fallback_reason: str,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "requested_preset": requested_preset,
        "effective_preset_id": effective_preset_id,
        "effective_preset_label": effective_preset_label,
        "provider": provider,
        "engine": engine,
        "voice": voice,
        "voice_identity": voice,
        "style_base": dict(style_base),
        "preset_overlay": dict(preset_overlay),
        "rate": _merge_signed_token(style_base["rate"], preset_overlay["rate"], "%", RATE_LIMITS),
        "pitch": _merge_signed_token(style_base["pitch"], preset_overlay["pitch"], "Hz", PITCH_LIMITS),
        "volume": _merge_signed_token(style_base["volume"], preset_overlay["volume"], "%", VOLUME_LIMITS),
        "fallback_used": bool(fallback_used),
        "fallback_reason": str(fallback_reason or ""),
    }
    if extra:
        payload.update(extra)
    return payload


def resolve_voice_preset(preset_id: str, style_tts: Dict[str, str]) -> Dict[str, Any]:
    """
    Returns effective TTS settings and fallback telemetry.
    """
    requested = str(preset_id or DEFAULT_VOICE_PRESET_ID).strip()
    if requested not in VOICE_PRESETS:
        requested = DEFAULT_VOICE_PRESET_ID
    preset = dict(VOICE_PRESETS.get(requested, {}))
    defaults = _style_defaults(style_tts)

    # Style default keeps current behavior unchanged while still reporting explicit overlay telemetry.
    if requested == DEFAULT_VOICE_PRESET_ID:
        return _build_voice_payload(
            requested_preset=preset_id,
            effective_preset_id=DEFAULT_VOICE_PRESET_ID,
            effective_preset_label=str(preset.get("label", DEFAULT_VOICE_PRESET_ID)),
            provider="edge",
            engine="edge_tts",
            voice=defaults["voice"],
            style_base=defaults,
            preset_overlay={"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
            fallback_used=False,
            fallback_reason="",
        )

    provider = str(preset.get("provider", "edge") or "edge").strip().lower()
    if provider == "edge":
        return _build_voice_payload(
            requested_preset=preset_id,
            effective_preset_id=requested,
            effective_preset_label=str(preset.get("label", requested)),
            provider="edge",
            engine="edge_tts",
            voice=str(preset.get("voice", defaults["voice"]) or defaults["voice"]),
            style_base=defaults,
            preset_overlay=_preset_overlay_tokens(preset),
            fallback_used=False,
            fallback_reason="",
        )

    # External providers are scaffold-only in this phase.
    fallback_id = str(preset.get("fallback_voice_preset", DEFAULT_VOICE_PRESET_ID) or DEFAULT_VOICE_PRESET_ID)
    fallback = VOICE_PRESETS.get(fallback_id, VOICE_PRESETS[DEFAULT_VOICE_PRESET_ID])
    has_external_key = bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())
    reason = "external_adapter_not_implemented"
    if not has_external_key:
        reason = "external_key_missing"

    return _build_voice_payload(
        requested_preset=preset_id,
        effective_preset_id=fallback_id,
        effective_preset_label=str(fallback.get("label", fallback_id)),
        provider="edge",
        engine="edge_tts",
        voice=str(fallback.get("voice", defaults["voice"]) or defaults["voice"]),
        style_base=defaults,
        preset_overlay=_preset_overlay_tokens(fallback),
        fallback_used=True,
        fallback_reason=reason,
        extra={
            "external_requested_provider": provider,
            "external_requested_engine": str(preset.get("engine", provider)),
        },
    )
