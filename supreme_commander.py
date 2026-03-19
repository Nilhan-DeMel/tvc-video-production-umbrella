"""
================================================================
THE SUPREME VIDEO COMMANDER -- v1.1.0
thanos-vis-supreme-commander

The Sovereign Orchestrator of ALL Video Weapons in the Armoury.
Classifies any video request -> Deploys the correct weapon ->
Monitors execution -> Recovers from failure -> Delivers the artifact.

Fire via CLI:
  python supreme_commander.py "Create a 4K cinematic video of..."
  python supreme_commander.py "Compile my slides into a narrated video"
  python supreme_commander.py "Extend the neon city video by 30 seconds"
  python supreme_commander.py "Generate offline on my local GPU"

Powered by: Fireworks (primary) with Fireworks-only runtime contract.
Fallback:   DiffSynth-Studio -- UniVA (multi-agent)

FULL WEAPON REGISTRY (all tools under command):
  GENERATIVE (cloud): veo-3.1, kling-3.0, sora-2, seedance-2-video
  GENERATIVE (local): diffsynth-studio, ltx2-video-gen, wan2-video-gen,
                      open-sora-video, higgsfield-orch
  NARRATION: omni-cinematic-forge (edge-tts+CPP), mova-av-sync, alive-av-animation
  AUDIO FIX: thanos-aud-precision-sync (Whisper V3)
  ASSEMBLY/NLE:  tvcip (with LAW-14 CPP), absolute-elegance-nle, remotion-renderer
  ANIMATION/UI: motion-canvas, omni-crop, tour-vision
  MULTI-AGENT: univa-orchestrator, vimax-orchestrator
================================================================
"""

import os
import sys
import time
import json
import argparse
import hashlib

from typing import TypedDict, Optional

# ============================================================
# === SOTA RETURN CONTRACT                                 ===
# ============================================================
class VideoJobResult(TypedDict):
    mode: str
    status: str
    output: Optional[str]
    error: Optional[str]
    size_mb: Optional[float]

# ============================================================
# === SOTA VAULT LOADER                                    ===
# ============================================================
from tvc_vault import get_secret, try_get_secret
from tvc_duration import resolve_duration_plan
from tvc_voice_registry import (
    DEFAULT_VOICE_PRESET_ID,
    is_valid_voice_preset,
    voice_preset_ids,
)

import tvc_config
from tvc_launch_contract import get_dead_end_metadata

FIREWORKS_API_KEY = str(os.getenv("FIREWORKS_API_KEY", "") or "").strip()
OUTPUT_DIR = tvc_config.PATHS["root"]


def _ensure_fireworks_api_key() -> str:
    global FIREWORKS_API_KEY
    if FIREWORKS_API_KEY:
        return FIREWORKS_API_KEY
    FIREWORKS_API_KEY = get_secret("key_HGmChvaB")
    return FIREWORKS_API_KEY


def _normalize_on_off(value: str, default: str = "off") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"on", "1", "true", "yes"}:
        return "on"
    if raw in {"off", "0", "false", "no"}:
        return "off"
    raise ValueError(f"Invalid on/off value: {value}")


def _resolve_key_probe_mode(cli_value: str = "") -> str:
    if str(cli_value or "").strip():
        norm = _normalize_on_off(cli_value, default="off")
        if norm not in {"on", "off"}:
            raise ValueError("Invalid --key-probe value. Allowed: on|off.")
        return norm
    env_raw = str(os.getenv("TVC_PREFLIGHT_KEY_PROBE", "") or "").strip()
    return _normalize_on_off(env_raw, default="off")


def _probe_fireworks_key(api_key: str) -> dict:
    endpoint = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "accounts/fireworks/models/kimi-k2p5",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    try:
        resp = _requests.post(endpoint, headers=headers, json=payload, timeout=12)
        if resp.status_code == 200:
            return {"ok": True, "error_code": "", "status_code": 200, "endpoint": endpoint, "message": "ok"}
        if resp.status_code in (401, 403):
            return {
                "ok": False,
                "error_code": "invalid_key",
                "status_code": int(resp.status_code),
                "endpoint": endpoint,
                "message": f"auth_failure_http_{resp.status_code}",
            }
        return {
            "ok": False,
            "error_code": "probe_unreachable",
            "status_code": int(resp.status_code),
            "endpoint": endpoint,
            "message": f"unexpected_http_{resp.status_code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "probe_unreachable",
            "status_code": 0,
            "endpoint": endpoint,
            "message": str(exc)[:300],
        }


def _probe_bfl_key(api_key: str) -> dict:
    endpoint = "https://api.bfl.ai/v1/get_result"
    headers = {"x-key": str(api_key or "")}
    params = {"id": "preflight_probe"}
    try:
        resp = _requests.get(endpoint, headers=headers, params=params, timeout=12)
        if resp.status_code in (200, 404):
            return {"ok": True, "error_code": "", "status_code": int(resp.status_code), "endpoint": endpoint, "message": "ok"}
        if resp.status_code in (401, 403):
            return {
                "ok": False,
                "error_code": "invalid_key",
                "status_code": int(resp.status_code),
                "endpoint": endpoint,
                "message": f"auth_failure_http_{resp.status_code}",
            }
        return {
            "ok": False,
            "error_code": "probe_unreachable",
            "status_code": int(resp.status_code),
            "endpoint": endpoint,
            "message": f"unexpected_http_{resp.status_code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "probe_unreachable",
            "status_code": 0,
            "endpoint": endpoint,
            "message": str(exc)[:300],
        }


# ============================================================
# STEP 1: CLASSIFY THE JOB
# ============================================================

import requests as _requests

class DummyRes:
    def __init__(self, text):
        self.text = text

def fireworks_chat_completion(contents):
    api_key = _ensure_fireworks_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "accounts/fireworks/models/kimi-k2p5",
        "messages": [{"role": "user", "content": contents}],
        "max_tokens": 2000
    }
    resp = _requests.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return DummyRes(data["choices"][0]["message"]["content"])

def classify_job(user_request: str) -> str:
    """Temporary deterministic classifier: force MODE_NARRATE for manual walkthrough debugging."""
    print("[COMMANDER] Classification shortcut enabled: forcing MODE_NARRATE (no API call).")

    # Legacy API classifier notes (kept intentionally for fast restore):
    # - Endpoint: https://api.fireworks.ai/inference/v1/chat/completions
    # - Model: accounts/fireworks/models/kimi-k2p5
    # - Prompt intent:
    #   "Classify request into exactly one mode:
    #    MODE_GENERATIVE, MODE_LOCAL_GPU, MODE_COMPILE, MODE_NARRATE,
    #    MODE_EXTEND, MODE_VOICE, MODE_ANIMATION, MODE_ORCHESTRATE."
    # - Prior behavior:
    #   response = fireworks_chat_completion(prompt_with_user_request)
    #   mode = response.text.strip()
    #   if mode not in valid_modes:
    #       mode = MODE_GENERATIVE
    #   return mode
    # - Temporary override rationale:
    #   During node-by-node debugging, we avoid classifier/API variability
    #   and always route this project into the NARRATE path.
    _ = user_request  # preserved for signature stability and future restore.
    return "MODE_NARRATE"


# ============================================================
# STEP 2: VEO 3.1 -- FIRE WITH RECOVERY
# ============================================================
def fire_veo(prompt: str, output_path: str, max_retries: int = 3, fast_mode: bool = False) -> dict:
    """Veo is disabled in Fireworks-only mode."""
    _ = (prompt, output_path, max_retries, fast_mode)
    message = (
        "Veo/Gemini generation is disabled in Fireworks-only mode. "
        "Use MODE_NARRATE with Fireworks pipeline."
    )
    print(f"[COMMANDER] {message}")
    return {
        "mode": "MODE_GENERATIVE",
        "status": "unsupported_mode",
        "output": None,
        "error": message,
        "size_mb": None,
    }


# ============================================================
# STEP 3: WEAPON DISPATCH ROUTER
# ============================================================
def _looks_like_direct_script(request: str) -> bool:
    """
    Heuristic: detect when MODE_NARRATE input is a fully provided script,
    so we should use USER_CONTEXT and skip YouTube harvest.
    """
    import re

    text = str(request or "").strip()
    if not text:
        return False
    low = f" {text.lower()} "
    youtube_signals = [
        " youtube ",
        " yt-dlp ",
        " transcript ",
        " transcripts ",
        " check 5 videos ",
        " find videos ",
        " latest videos ",
    ]
    if any(sig in low for sig in youtube_signals):
        return False

    word_count = len(re.findall(r"\b\w+\b", text))
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    direct_prompt_signals = [
        " make a video ",
        " create a video ",
        " tell me about ",
        " find me ",
        " search for ",
        " latest ",
    ]
    looks_like_direct_prompt = any(sig in low for sig in direct_prompt_signals)

    if looks_like_direct_prompt and sentence_count <= 4:
        return False

    return word_count >= 70 and sentence_count >= 5


def dispatch_weapon(
    mode: str,
    request: str,
    output_path: str,
    target_duration: Optional[int] = None,
    duration_mode: str = "manual",
    requested_target_duration_seconds: Optional[int] = None,
    estimated_duration_seconds: Optional[int] = None,
    context_summary: Optional[str] = None,
    input_source: str = "YOUTUBE_HARVEST",
    narration_style: str = "documentary",
    context_rewrite: str = "off",
    watermark_mode: str = "on",
    voice_preset: str = DEFAULT_VOICE_PRESET_ID,
) -> VideoJobResult:
    """Dispatches the request to the correct orchestrator, weapon, or agent."""
    resolved_input_source = str(input_source or "YOUTUBE_HARVEST").strip().upper()
    resolved_context_summary = str(context_summary or "").strip()
    if mode == "MODE_NARRATE" and not resolved_context_summary and resolved_input_source != "USER_CONTEXT":
        if _looks_like_direct_script(request):
            resolved_context_summary = str(request or "").strip()
            resolved_input_source = "USER_CONTEXT"
            print("[COMMANDER] Auto-routing script-like text to USER_CONTEXT (YouTube skipped).")

    req_lower = request.lower()
    
    # Initialize SOTA return contract
    result: VideoJobResult = {
        "mode": mode,
        "status": "starting",
        "output": None,
        "error": None,
        "size_mb": None
    }

    if mode == "MODE_GENERATIVE":
        message = str(
            get_dead_end_metadata("MODE_GENERATIVE").get(
                "message",
                "DEAD-END PATH: MODE_GENERATIVE is disabled in Fireworks-only mode. "
                "Use MODE_NARRATE for Fireworks-backed production.",
            )
        )
        print(f"[COMMANDER] {message}")
        result["status"] = "unsupported_mode"
        result["error"] = message

    elif mode == "MODE_LOCAL_GPU":
        print("[COMMANDER] Job type: LOCAL GPU. Consulting offline weapon registry...")
        if "wan" in req_lower: target_weapon = "wan2-video-gen"
        elif "ltx" in req_lower: target_weapon = "ltx2-video-gen"
        elif "sora" in req_lower: target_weapon = "open-sora-video"
        elif "higgsfield" in req_lower: target_weapon = "higgsfield-orch"
        else: target_weapon = "thanos-vis-diffsynth-studio"
        
        print(f"[COMMANDER] Local GPU Weapon Selected: {target_weapon}")
        print(f'  aladdin_one_ring(skill="{target_weapon}", query="{request[:200]}")')
        result["status"] = "local_gpu_bifrost_dispatched"

    elif mode == "MODE_COMPILE":
        print("[COMMANDER] Job type: COMPILE/ASSEMBLY. Selecting NLE Weapon...")
        if "elegance" in req_lower or "nle" in req_lower:
            target_weapon = "thanos-vis-absolute-elegance-nle"
        elif "remotion" in req_lower:
            target_weapon = "thanos-vis-remotion-renderer"
        else:
            target_weapon = "thanos-vis-cinematic-pipeline"
            print("[COMMANDER] NOTE: TVCIP automatically fires the Cinematic Prosody Preprocessor (LAW 14)")
            
        print(f"[COMMANDER] Dispatched to: {target_weapon}")
        print(f'  aladdin_one_ring(skill="{target_weapon}", query="{request[:200]}")')
        result["status"] = "bifrost_dispatched"
        # ISSUE-008: Ensure deterministic return for async modes
        result["output"] = os.path.join(OUTPUT_DIR, f"compile_job_{int(time.time())}.mp4")
        print(f"[OK] Dispatched. Expected output: {result['output']}")

    elif mode == "MODE_NARRATE":
        print("[COMMANDER] Job type: NARRATE. Deploying SOTA Multi-Agent Cognitive Orchestrator (LangGraph).")
        from tvc_langgraph_core import execute_multi_agent_narrator
        try:
            final_artifact = execute_multi_agent_narrator(
                request,
                output_path,
                _ensure_fireworks_api_key(),
                target_duration=target_duration,
                duration_mode=duration_mode,
                requested_target_duration_seconds=requested_target_duration_seconds,
                estimated_duration_seconds=estimated_duration_seconds,
                context_summary=(resolved_context_summary or None),
                input_source=resolved_input_source,
                narration_style=narration_style,
                context_rewrite=context_rewrite,
                watermark_mode=watermark_mode,
                voice_preset=voice_preset,
            )
            result["status"] = "success"
            result["output"] = final_artifact
            if os.path.exists(final_artifact):
                result["size_mb"] = os.path.getsize(final_artifact) / 1_048_576
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            print(f"[COMMANDER] SOTA LangGraph Orchestration Failed: {e}")

    elif mode == "MODE_VOICE":
        print("[COMMANDER] Job type: VOICE. Deploying Narration Arsenal...")
        if "sync" in req_lower and "drift" in req_lower: target_weapon = "thanos-aud-precision-sync"
        elif "avatar" in req_lower or "alive" in req_lower: target_weapon = "alive-av-animation"
        elif "mova" in req_lower: target_weapon = "mova-av-sync"
        else: target_weapon = "thanos-vis-omni-cinematic-forge"
        
        print(f"[COMMANDER] Narration Weapon Selected: {target_weapon}")
        print(f'  aladdin_one_ring(skill="{target_weapon}", query="{request[:200]}")')
        result["status"] = "voice_bifrost_dispatched"
        # ISSUE-008: Ensure deterministic return for async modes
        result["output"] = os.path.join(OUTPUT_DIR, f"voice_job_{int(time.time())}.mp3")
        print(f"[OK] Dispatched. Expected output: {result['output']}")
        
    elif mode == "MODE_ANIMATION":
        print("[COMMANDER] Job type: ANIMATION / UI.")
        if "tour" in req_lower or "product" in req_lower: target_weapon = "tour-vision"
        elif "crop" in req_lower or "aspect ratio" in req_lower: target_weapon = "thanos-vis-omni-crop"
        else: target_weapon = "thanos-vis-motion-canvas"
        
        print(f"[COMMANDER] UI/Animation Weapon Selected: {target_weapon}")
        print(f'  aladdin_one_ring(skill="{target_weapon}", query="{request[:200]}")')
        result["status"] = "animation_bifrost_dispatched"
        # ISSUE-008: Ensure deterministic return for async modes
        result["output"] = os.path.join(OUTPUT_DIR, f"animation_job_{int(time.time())}.mp4")
        print(f"[OK] Dispatched. Expected output: {result['output']}")

    elif mode == "MODE_EXTEND":
        message = str(
            get_dead_end_metadata("MODE_EXTEND").get(
                "message",
                "DEAD-END PATH: MODE_EXTEND is disabled in Fireworks-only mode (Veo path unavailable). "
                "Use MODE_NARRATE for Fireworks-backed production.",
            )
        )
        print(f"[COMMANDER] {message}")
        result["status"] = "unsupported_mode"
        result["error"] = message

    elif mode == "MODE_ORCHESTRATE":
        print("[COMMANDER] Job type: ORCHESTRATE. Multi-agent timeline synthesis.")
        if "vimax" in req_lower or "non-linear" in req_lower: target_weapon = "thanos-dev-vimax-orchestrator"
        else: target_weapon = "thanos-vis-univa-orchestrator"
        
        print(f"[COMMANDER] Orchestrator Selected: {target_weapon}")
        print(f'  aladdin_one_ring(skill="{target_weapon}", query="{request[:200]}")')
        result["status"] = "bifrost_dispatched"
        # ISSUE-008: Ensure deterministic return for async modes
        result["output"] = os.path.join(OUTPUT_DIR, f"orchestrate_job_{int(time.time())}.mp4")
        print(f"[OK] Dispatched. Expected output: {result['output']}")

    return result


# ============================================================
# STEP 4: REQUEST FLAG PARSER (NARRATE CONTEXT ROUTING)
# ============================================================
def _strip_wrapped_quotes(text: str) -> str:
    t = (text or "").strip()
    if len(t) >= 2 and ((t[0] == '"' and t[-1] == '"') or (t[0] == "'" and t[-1] == "'")):
        return t[1:-1]
    return t


def _normalize_context_file_path(context_file: str) -> str:
    """
    Normalize and validate --context-file input before file reads.
    Explicitly reject root/drive-root or directory targets.
    """
    import re

    path = os.path.abspath(os.path.expanduser(os.path.expandvars(str(context_file or "").strip())))
    if not path:
        raise ValueError("--context-file is empty")

    drive, tail = os.path.splitdrive(path)
    if path in (os.path.sep, "\\") or re.fullmatch(r"[A-Za-z]:[\\/]*", path) or (drive and tail in ("", "\\", "/")):
        raise ValueError(f"--context-file must point to a file, not drive root: {path}")
    if os.path.isdir(path):
        raise ValueError(f"--context-file must point to a file, not a directory: {path}")
    return path


def _parse_mode_duration_from_tokens(tokens):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--mode")
    parser.add_argument("--duration", type=int)
    try:
        ns, remaining = parser.parse_known_args(tokens or [])
    except SystemExit as e:
        raise ValueError("Malformed --mode/--duration flags.") from e
    mode = str(ns.mode or "").strip().upper() if ns.mode else None
    return mode, ns.duration, remaining


def parse_narrate_runtime_flags_from_tokens(tokens):
    """
    Token-based parser to avoid regex ambiguity when shell quoting is malformed.
    Returns cleaned request + resolved context + style controls.
    """
    valid_styles = {"documentary", "sales_saas", "human_story"}
    valid_rewrite = {"off", "force"}
    valid_watermark = {"on", "off"}
    valid_key_probe = {"on", "off"}
    valid_voice_presets = set(voice_preset_ids())

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--context-file")
    parser.add_argument("--context")
    parser.add_argument("--narration-style")
    parser.add_argument("--context-rewrite")
    parser.add_argument("--watermark-mode")
    parser.add_argument("--voice-preset")
    parser.add_argument("--key-probe")
    try:
        ns, remaining = parser.parse_known_args(tokens or [])
    except SystemExit as e:
        raise ValueError("Malformed narrate flags. Check quoting/escaping for --context-file/--context.") from e

    cleaned_request = " ".join(remaining).strip()
    context_file = ns.context_file
    context_inline = ns.context
    narration_style = str(ns.narration_style or "documentary").strip().lower()
    context_rewrite = str(ns.context_rewrite or "off").strip().lower()
    watermark_mode = str(ns.watermark_mode or "on").strip().lower()
    voice_preset = str(ns.voice_preset or DEFAULT_VOICE_PRESET_ID).strip()
    key_probe = str(ns.key_probe or "").strip().lower()

    resolved_context = ""
    if context_file:
        context_file = _normalize_context_file_path(context_file)
        if not os.path.exists(context_file):
            raise FileNotFoundError(f"--context-file not found: {context_file}")
        with open(context_file, "r", encoding="utf-8", errors="ignore") as f:
            resolved_context = f.read().strip()
        if not resolved_context:
            raise ValueError(f"--context-file is empty: {context_file}")
    elif context_inline:
        resolved_context = str(context_inline or "").strip()
        if not resolved_context:
            raise ValueError("--context is empty")

    if narration_style not in valid_styles:
        raise ValueError(
            f"Invalid --narration-style '{narration_style}'. Allowed: documentary|sales_saas|human_story."
        )
    if context_rewrite not in valid_rewrite:
        raise ValueError(
            f"Invalid --context-rewrite '{context_rewrite}'. Allowed: off|force."
        )
    if watermark_mode not in valid_watermark:
        raise ValueError(
            f"Invalid --watermark-mode '{watermark_mode}'. Allowed: on|off."
        )
    if not is_valid_voice_preset(voice_preset):
        raise ValueError(
            f"Invalid --voice-preset '{voice_preset}'. Allowed: {','.join(sorted(valid_voice_presets))}."
        )
    if key_probe and key_probe not in valid_key_probe:
        raise ValueError(
            f"Invalid --key-probe '{key_probe}'. Allowed: on|off."
        )

    return (
        cleaned_request,
        resolved_context,
        context_file,
        narration_style,
        context_rewrite,
        watermark_mode,
        voice_preset,
        key_probe,
    )


def parse_narrate_runtime_flags(user_request: str):
    """Extract narrate flags and return cleaned request + resolved context + style controls."""
    import re

    valid_styles = {"documentary", "sales_saas", "human_story"}
    valid_rewrite = {"off", "force"}
    valid_watermark = {"on", "off"}
    valid_key_probe = {"on", "off"}
    valid_voice_presets = set(voice_preset_ids())
    token_pat = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\S+'
    flag_re = re.compile(
        rf'(?P<lead>\s*)(?P<flag>--context-file|--context|--narration-style|--context-rewrite|--watermark-mode|--voice-preset|--key-probe)\s+(?P<value>{token_pat})'
    )
    matches = list(flag_re.finditer(user_request or ""))

    # Strict parse behavior: if any narrate flag is present but not parseable, fail fast.
    for raw_flag in ["--context-file", "--context", "--narration-style", "--context-rewrite", "--watermark-mode", "--voice-preset", "--key-probe"]:
        flag_present = bool(re.search(rf"(?<!\S){re.escape(raw_flag)}(?!\S)", user_request or ""))
        if flag_present and not any(m.group("flag") == raw_flag for m in matches):
            raise ValueError(
                f"Malformed {raw_flag} value. Quote values with spaces and escape embedded quotes."
            )

    context_file = None
    context_inline = None
    narration_style = None
    context_rewrite = None
    watermark_mode = None
    voice_preset = None
    key_probe = None
    for m in matches:
        raw_flag = m.group("flag")
        raw_val = _strip_wrapped_quotes(m.group("value"))
        if raw_flag == "--context-file" and context_file is None:
            context_file = raw_val
        elif raw_flag == "--context" and context_inline is None:
            context_inline = raw_val
        elif raw_flag == "--narration-style" and narration_style is None:
            narration_style = raw_val
        elif raw_flag == "--context-rewrite" and context_rewrite is None:
            context_rewrite = raw_val
        elif raw_flag == "--watermark-mode" and watermark_mode is None:
            watermark_mode = raw_val
        elif raw_flag == "--voice-preset" and voice_preset is None:
            voice_preset = raw_val
        elif raw_flag == "--key-probe" and key_probe is None:
            key_probe = raw_val

    # Preserve request text shape as much as possible while removing consumed flag segments.
    cleaned_parts = []
    last = 0
    for m in matches:
        cleaned_parts.append(user_request[last:m.start()])
        last = m.end()
    cleaned_parts.append(user_request[last:])
    cleaned_request = re.sub(r"\s{2,}", " ", "".join(cleaned_parts)).strip()

    resolved_context = ""
    if context_file:
        context_file = _normalize_context_file_path(context_file)
        if not os.path.exists(context_file):
            raise FileNotFoundError(f"--context-file not found: {context_file}")
        with open(context_file, "r", encoding="utf-8", errors="ignore") as f:
            resolved_context = f.read().strip()
        if not resolved_context:
            raise ValueError(f"--context-file is empty: {context_file}")
    elif context_inline:
        resolved_context = context_inline.strip()
        if not resolved_context:
            raise ValueError("--context is empty")

    narration_style = str(narration_style or "documentary").strip().lower()
    context_rewrite = str(context_rewrite or "off").strip().lower()
    watermark_mode = str(watermark_mode or "on").strip().lower()
    voice_preset = str(voice_preset or DEFAULT_VOICE_PRESET_ID).strip()
    if narration_style not in valid_styles:
        raise ValueError(
            f"Invalid --narration-style '{narration_style}'. Allowed: documentary|sales_saas|human_story."
        )
    if context_rewrite not in valid_rewrite:
        raise ValueError(
            f"Invalid --context-rewrite '{context_rewrite}'. Allowed: off|force."
        )
    if watermark_mode not in valid_watermark:
        raise ValueError(
            f"Invalid --watermark-mode '{watermark_mode}'. Allowed: on|off."
        )
    if not is_valid_voice_preset(voice_preset):
        raise ValueError(
            f"Invalid --voice-preset '{voice_preset}'. Allowed: {','.join(sorted(valid_voice_presets))}."
        )
    key_probe = str(key_probe or "").strip().lower()
    if key_probe and key_probe not in valid_key_probe:
        raise ValueError(
            f"Invalid --key-probe '{key_probe}'. Allowed: on|off."
        )

    return (
        cleaned_request,
        resolved_context,
        context_file,
        narration_style,
        context_rewrite,
        watermark_mode,
        voice_preset,
        key_probe,
    )


def _write_preflight_failure_artifact(payload: dict) -> str:
    failures_dir = os.path.join(OUTPUT_DIR, "Evidence", "preflight_failures")
    os.makedirs(failures_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(failures_dir, f"preflight_{ts}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return file_path


def _startup_preflight_for_narrate(
    mode: str,
    request_text: str,
    cli_tokens,
    run_attempt_id: str,
    key_probe_mode: str = "off",
):
    if mode != "MODE_NARRATE":
        return True, {}

    missing = []
    resolved = {}
    key_failures = {}
    probe_mode = str(key_probe_mode or "off").strip().lower()

    fw_res = try_get_secret("key_HGmChvaB")
    if fw_res.get("ok"):
        resolved["fireworks"] = {
            "env_var": fw_res.get("resolved_env_var", ""),
            "scope": fw_res.get("resolved_scope", ""),
            "canonical_secret": fw_res.get("canonical_secret", ""),
        }
    else:
        missing.append("FIREWORKS_API_KEY")
        key_failures["fireworks"] = {
            "error_code": fw_res.get("error_code", "missing_env"),
            "message": fw_res.get("message", ""),
            "canonical_secret": fw_res.get("canonical_secret", ""),
        }

    flux_res = try_get_secret("BLF_FLUX2PRO")
    if flux_res.get("ok"):
        resolved["flux"] = {
            "env_var": flux_res.get("resolved_env_var", ""),
            "scope": flux_res.get("resolved_scope", ""),
            "canonical_secret": flux_res.get("canonical_secret", ""),
        }
    else:
        missing.append("BLF_FLUX2PRO|BFL_API_KEY")
        key_failures["flux"] = {
            "error_code": flux_res.get("error_code", "missing_env"),
            "message": flux_res.get("message", ""),
            "canonical_secret": flux_res.get("canonical_secret", ""),
        }

    if missing:
        request_basis = str(request_text or " ".join(cli_tokens or []))
        failure_codes = [str(v.get("error_code", "") or "missing_env") for v in key_failures.values()]
        if any(code in {"unsupported_secret", "disabled_secret"} for code in failure_codes):
            err_code = "unsupported_secret"
        else:
            err_code = "missing_env"
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "run_attempt_id": run_attempt_id,
            "mode": mode,
            "key_probe_mode": probe_mode,
            "cwd": os.getcwd(),
            "argv": list(cli_tokens or []),
            "request_hash_sha256_16": hashlib.sha256(request_basis.encode("utf-8")).hexdigest()[:16],
            "missing": missing,
            "resolved": resolved,
            "key_failures": key_failures,
            "error_code": err_code,
        }
        artifact = _write_preflight_failure_artifact(payload)
        print(f"[PRECHECK] FAILED missing keys: {missing}")
        print(f"[PRECHECK] Artifact: {artifact}")
        return False, {
            "missing_keys": missing,
            "resolved": resolved,
            "artifact": artifact,
            "error_code": err_code,
            "error": "Startup preflight failed: required API keys could not be resolved.",
        }

    if probe_mode == "on":
        probe_failures = {}
        fw_probe = _probe_fireworks_key(str(fw_res.get("key", "") or ""))
        if not fw_probe.get("ok"):
            probe_failures["fireworks"] = fw_probe
        flux_probe = _probe_bfl_key(str(flux_res.get("key", "") or ""))
        if not flux_probe.get("ok"):
            probe_failures["flux"] = flux_probe
        if probe_failures:
            request_basis = str(request_text or " ".join(cli_tokens or []))
            error_codes = [str(v.get("error_code", "") or "probe_unreachable") for v in probe_failures.values()]
            if any(code == "invalid_key" for code in error_codes):
                err_code = "invalid_key"
            else:
                err_code = "probe_unreachable"
            payload = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "run_attempt_id": run_attempt_id,
                "mode": mode,
                "key_probe_mode": probe_mode,
                "cwd": os.getcwd(),
                "argv": list(cli_tokens or []),
                "request_hash_sha256_16": hashlib.sha256(request_basis.encode("utf-8")).hexdigest()[:16],
                "missing": [],
                "resolved": resolved,
                "probe_failures": probe_failures,
                "error_code": err_code,
            }
            artifact = _write_preflight_failure_artifact(payload)
            print(f"[PRECHECK] FAILED key probe ({err_code}): {list(probe_failures.keys())}")
            print(f"[PRECHECK] Artifact: {artifact}")
            return False, {
                "missing_keys": [],
                "resolved": resolved,
                "artifact": artifact,
                "error_code": err_code,
                "error": f"Startup preflight probe failed: {err_code}",
                "probe_failures": probe_failures,
            }

    print(
        "[PRECHECK] OK mode=MODE_NARRATE "
        f"fireworks={resolved['fireworks'].get('env_var','')}@{resolved['fireworks'].get('scope','')} "
        f"flux={resolved['flux'].get('env_var','')}@{resolved['flux'].get('scope','')} "
        f"key_probe={probe_mode}"
    )
    return True, {"resolved": resolved, "key_probe_mode": probe_mode}


# ============================================================
# STEP 4: THE MASTER ENTRY POINT
# ============================================================
def supreme_video_commander(user_request: str, output_path: str = None, cli_tokens=None) -> dict:
    """
    THE MASTER ENTRY POINT.
    Call with ANY video request. The Commander does the rest.
    """
    print("=" * 65)
    print("        SUPREME VIDEO COMMANDER -- ACTIVATED")
    print("        Thanos Armoury | thanos-vis-supreme-commander")
    print("=" * 65)
    print(f"[INTEL] Request: {user_request}")

    # Auto-name output
    if not output_path:
        timestamp = int(time.time())
        output_path = os.path.join(OUTPUT_DIR, f"emperor_output_{timestamp}.mp4")

    run_attempt_id = f"{int(time.time())}-{os.getpid()}"

    # Classify job (with explicit manual override support)
    import re
    token_mode = None
    token_duration = None
    token_remaining = None
    if cli_tokens:
        token_mode, token_duration, token_remaining = _parse_mode_duration_from_tokens(cli_tokens)

    if token_mode:
        mode = token_mode
        user_request = " ".join(token_remaining or []).strip()
        print(f"[COMMANDER] Classification Override Detected: {mode}")
    else:
        mode_match = re.search(r'--mode\s+(MODE_\w+)', user_request)
        if mode_match:
            mode = mode_match.group(1).upper()
            user_request = re.sub(r'--mode\s+MODE_\w+', '', user_request).strip()
            print(f"[COMMANDER] Classification Override Detected: {mode}")
        else:
            mode = classify_job(user_request)
            print(f"[COMMANDER] Classification: {mode}")

    requested_target_duration_seconds = None
    if token_duration is not None:
        requested_target_duration_seconds = int(token_duration)
    else:
        duration_match = re.search(r'--duration\s+(\d+)', user_request)
        if duration_match:
            requested_target_duration_seconds = int(duration_match.group(1))
            user_request = re.sub(r'--duration\s+\d+', '', user_request).strip()

    context_summary = None
    input_source = "YOUTUBE_HARVEST"
    narration_style = "documentary"
    context_rewrite = "off"
    watermark_mode = "on"
    voice_preset = DEFAULT_VOICE_PRESET_ID
    key_probe_override = ""
    duration_mode = "manual"
    estimated_duration_seconds = None
    target_duration = None
    if mode == "MODE_NARRATE":
        if cli_tokens:
            narrate_tokens = token_remaining if token_remaining is not None else cli_tokens
            (
                user_request,
                context_summary,
                context_file,
                narration_style,
                context_rewrite,
                watermark_mode,
                voice_preset,
                key_probe_override,
            ) = (
                parse_narrate_runtime_flags_from_tokens(narrate_tokens)
            )
        else:
            (
                user_request,
                context_summary,
                context_file,
                narration_style,
                context_rewrite,
                watermark_mode,
                voice_preset,
                key_probe_override,
            ) = (
                parse_narrate_runtime_flags(user_request)
            )
        key_probe_mode = _resolve_key_probe_mode(key_probe_override)
        if context_summary:
            input_source = "USER_CONTEXT"
            if context_file:
                print(f"[COMMANDER] Context Source: USER_CONTEXT via file ({context_file})")
            else:
                print("[COMMANDER] Context Source: USER_CONTEXT via inline text")
        elif _looks_like_direct_script(user_request):
            context_summary = user_request
            input_source = "USER_CONTEXT"
            print("[COMMANDER] Context Source: USER_CONTEXT via auto-detected script text")
        else:
            print("[COMMANDER] Context Source: YOUTUBE_HARVEST (default)")
        duration_plan = resolve_duration_plan(
            input_source=input_source,
            context_rewrite=context_rewrite,
            narration_style=narration_style,
            context_text=context_summary or user_request,
            requested_target_duration=requested_target_duration_seconds,
        )
        duration_mode = str(duration_plan.get("duration_mode", "manual") or "manual")
        parsed_requested_target_duration_seconds = requested_target_duration_seconds
        requested_target_duration_seconds = duration_plan.get("requested_target_duration_seconds")
        estimated_duration_seconds = duration_plan.get("estimated_duration_seconds")
        target_duration = duration_plan.get("effective_planning_duration_seconds")
        if duration_mode == "auto":
            if parsed_requested_target_duration_seconds is not None:
                print(
                    "[COMMANDER] Duration Mode: AUTO_FROM_SCRIPT "
                    "(manual duration ignored for deterministic USER_CONTEXT)"
                )
            else:
                estimate_note = (
                    f" (~{estimated_duration_seconds}s estimated)"
                    if estimated_duration_seconds is not None
                    else ""
                )
                print(f"[COMMANDER] Duration Mode: AUTO_FROM_SCRIPT{estimate_note}")
        elif requested_target_duration_seconds is not None:
            print(f"[COMMANDER] Duration Override Detected: {requested_target_duration_seconds}s")
        print(f"[COMMANDER] Narration Style: {narration_style}")
        print(f"[COMMANDER] Context Rewrite: {context_rewrite}")
        print(f"[COMMANDER] Watermark Mode: {watermark_mode}")
        print(f"[COMMANDER] Voice Preset: {voice_preset}")
        print(f"[COMMANDER] Key Probe Mode: {key_probe_mode}")
    else:
        key_probe_mode = "off"
        target_duration = int(requested_target_duration_seconds or 60)

    preflight_ok, preflight_meta = _startup_preflight_for_narrate(
        mode=mode,
        request_text=user_request,
        cli_tokens=cli_tokens,
        run_attempt_id=run_attempt_id,
        key_probe_mode=key_probe_mode,
    )

    if preflight_ok:
        result = dispatch_weapon(
            mode,
            user_request,
            output_path,
            target_duration=target_duration,
            duration_mode=duration_mode,
            requested_target_duration_seconds=requested_target_duration_seconds,
            estimated_duration_seconds=estimated_duration_seconds,
            context_summary=context_summary,
            input_source=input_source,
            narration_style=narration_style,
            context_rewrite=context_rewrite,
            watermark_mode=watermark_mode,
            voice_preset=voice_preset,
        )
    else:
        preflight_error_code = str(preflight_meta.get("error_code", "missing_env") or "missing_env")
        result = {
            "mode": mode,
            "status": "preflight_failed",
            "output": None,
            "error": str(preflight_meta.get("error", "Startup preflight failed.")),
            "size_mb": None,
            "error_code": preflight_error_code,
            "missing_keys": preflight_meta.get("missing_keys", []),
            "preflight_artifact": preflight_meta.get("artifact"),
        }

    # Final report
    print("\n" + "=" * 65)
    print(f"[COMMANDER] Status: {result['status'].upper()}")
    if result.get("output"):
        size_mb = result.get('size_mb')
        size_str = f" ({size_mb:.2f} MB)" if size_mb is not None else ""
        print(f"[COMMANDER] Artifact: {result['output']}{size_str}")
    if result.get("error"):
        print(f"[COMMANDER] Last Error: {result['error']}")
    print("=" * 65)

    # Save mission log
    log_path = os.path.join(OUTPUT_DIR, "commander_mission_log.json")
    try:
        logs = []
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                logs = json.load(f)
        logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "request": user_request,
            "mode": mode,
            "status": result["status"],
            "output": result.get("output"),
            "run_attempt_id": run_attempt_id,
            "voice_preset": voice_preset,
            "duration_mode": duration_mode,
            "requested_target_duration_seconds": requested_target_duration_seconds,
            "estimated_duration_seconds": estimated_duration_seconds,
            "effective_planning_duration_seconds": target_duration,
        })
        if result.get("error_code"):
            logs[-1]["error_code"] = result.get("error_code")
        if result.get("missing_keys"):
            logs[-1]["missing_keys"] = result.get("missing_keys")
        if result.get("preflight_artifact"):
            logs[-1]["preflight_artifact"] = result.get("preflight_artifact")
        with open(log_path, "w") as f:
            json.dump(logs, f, indent=2)
        print(f"[COMMANDER] Mission logged to: {log_path}")
    except Exception:
        pass

    return result


# ============================================================
# CLI ENTRY
# ============================================================
if __name__ == "__main__":
    cli_tokens = None
    if len(sys.argv) > 1:
        cli_tokens = list(sys.argv[1:])
        request = " ".join(cli_tokens)
    else:
        request = input("\n[SUPREME COMMANDER] Enter your video command: ").strip()

    if not request:
        print("No command received. Commander standing down.")
        sys.exit(0)

    result = supreme_video_commander(request, cli_tokens=cli_tokens)
    if str(result.get("status", "")).lower() == "preflight_failed":
        sys.exit(2)
