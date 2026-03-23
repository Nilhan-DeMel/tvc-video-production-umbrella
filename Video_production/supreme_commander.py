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

Powered by: Gemini 2.5 Pro (brain) + Veo 3.1 (default cloud weapon)
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
from tvc_vault import get_secret

import tvc_config

FIREWORKS_API_KEY = get_secret("key_HGmChvaB")
GEMINI_API_KEY = get_secret("Gemini Dev")
GEMINI_BRAIN = "gemini-2.5-pro"
VEO_MODEL = "veo-3.1-generate-preview"
VEO_MODEL_FAST = "veo-3.1-fast-generate-preview"
OUTPUT_DIR = tvc_config.PATHS["root"]

# Initialize Google GenAI Client for Veo 3.1
from google import genai
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})


# ============================================================
# STEP 1: CLASSIFY THE JOB
# ============================================================

import requests as _requests

class DummyRes:
    def __init__(self, text):
        self.text = text

def fireworks_chat_completion(contents):
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
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
    """Fires Veo 3.1 with live monitoring, progressive retry, and DiffSynth fallback."""
    model = VEO_MODEL_FAST if fast_mode else VEO_MODEL
    result = {"mode": "MODE_GENERATIVE", "status": "starting", "output": None, "error": None}

    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n[VEO 3.1] Attempt {attempt}/{max_retries} -- Firing `{model}`...")
            print(f"[VEO 3.1] Prompt: {prompt[:120]}...")

            operation = client.models.generate_videos(
                model=model,
                prompt=prompt,
            )

            print(f"[VEO 3.1] Operation created: {operation.name}")
            print("[VEO 3.1] Monitoring generation (polling every 10s)...")

            # ---- LIVE MONITOR LOOP ----
            poll_count = 0
            while not operation.done:
                poll_count += 1
                print(f"[VEO 3.1] Poll #{poll_count}... still rendering...")
                time.sleep(10)
                operation = client.operations.get(operation=operation)

            if operation.error:
                raise RuntimeError(f"Veo API error: {operation.error}")

            # ---- DOWNLOAD ----
            print(f"[VEO 3.1] Generation COMPLETE after {poll_count * 10}s. Downloading...")
            video = operation.response.generated_videos[0]
            response_bytes = client.files.download(file=video.video)
            with open(output_path, "wb") as f:
                f.write(response_bytes)

            size_mb = os.path.getsize(output_path) / 1_048_576
            print(f"[VEO 3.1] Video saved: {output_path} ({size_mb:.2f} MB)")

            result["status"] = "success"
            result["output"] = output_path
            result["size_mb"] = size_mb
            return result

        except Exception as e:
            error_str = str(e)
            result["error"] = error_str
            print(f"[VEO 3.1] FAILURE on attempt {attempt}: {error_str}")

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print("[COMMANDER] Quota exhausted. Cannot retry Veo.")
                break

            if attempt < max_retries:
                backoff = 15 * attempt
                print(f"[COMMANDER] Recovery protocol: retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                print("[COMMANDER] All retries exhausted. Escalating to Tier 2 fallback...")

    # ---- FALLBACK to DiffSynth-Studio ----
    print("\n[COMMANDER] ESCALATING TO TIER 2: DiffSynth-Studio (Local GPU)")
    print("[COMMANDER] Action required: Run the following via Bifrost Bridge:")
    print(f'  aladdin_one_ring(skill="thanos-vis-diffsynth-studio", query="{prompt[:200]}")')
    result["status"] = "bifrost_fallback_required"
    return result


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
    target_duration: int = 60,
    context_summary: Optional[str] = None,
    input_source: str = "YOUTUBE_HARVEST",
    narration_style: str = "documentary",
    context_rewrite: str = "off",
    watermark_mode: str = "on",
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
        if "kling" in req_lower:
            print("[COMMANDER] Deploying Tier 1 cloud weapon: Kling-3.0")
            print(f'  aladdin_one_ring(skill="thanos-ora-kling-3.0", query="{request[:200]}")')
            result["status"] = "bifrost_dispatched"
        elif "sora" in req_lower:
            print("[COMMANDER] Deploying Tier 1 cloud weapon: Sora-2")
            print(f'  aladdin_one_ring(skill="thanos-ora-sora-2", query="{request[:200]}")')
            result["status"] = "bifrost_dispatched"
        elif "seedance" in req_lower:
            print("[COMMANDER] Deploying Tier 1 cloud weapon: Seedance 2.0")
            print(f'  aladdin_one_ring(skill="seedance-2-video", query="{request[:200]}")')
            result["status"] = "bifrost_dispatched"
        else:
            print("[COMMANDER] Deploying Tier 1 cloud weapon: Veo 3.1 (Default)")
            result = fire_veo(request, output_path)

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
                FIREWORKS_API_KEY,
                target_duration=target_duration,
                context_summary=(resolved_context_summary or None),
                input_source=resolved_input_source,
                narration_style=narration_style,
                context_rewrite=context_rewrite,
                watermark_mode=watermark_mode,
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
        print("[COMMANDER] Job type: EXTEND. Routing to Veo 3.1 extension mode (up to 148s).")
        result = fire_veo(request + " [VIDEO EXTENSION MODE]", output_path)

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


def parse_narrate_runtime_flags(user_request: str):
    """Extract narrate flags and return cleaned request + resolved context + style controls."""
    import re

    valid_styles = {"documentary", "sales_saas", "human_story"}
    valid_rewrite = {"off", "force"}
    valid_watermark = {"on", "off"}
    token_pat = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\S+'
    flag_re = re.compile(
        rf'(?P<lead>\s*)(?P<flag>--context-file|--context|--narration-style|--context-rewrite|--watermark-mode)\s+(?P<value>{token_pat})'
    )
    matches = list(flag_re.finditer(user_request or ""))

    # Strict parse behavior: if any narrate flag is present but not parseable, fail fast.
    for raw_flag in ["--context-file", "--context", "--narration-style", "--context-rewrite", "--watermark-mode"]:
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
        context_file = os.path.abspath(os.path.expanduser(os.path.expandvars(context_file)))
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

    return cleaned_request, resolved_context, context_file, narration_style, context_rewrite, watermark_mode


# ============================================================
# STEP 4: THE MASTER ENTRY POINT
# ============================================================
def supreme_video_commander(user_request: str, output_path: str = None) -> dict:
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

    # Classify job (with explicit manual override support)
    import re
    mode_match = re.search(r'--mode\s+(MODE_\w+)', user_request)
    if mode_match:
        mode = mode_match.group(1).upper()
        # Remove the flag from the request so it doesn't pollute actual prompts
        user_request = re.sub(r'--mode\s+MODE_\w+', '', user_request).strip()
        print(f"[COMMANDER] Classification Override Detected: {mode}")
    else:
        mode = classify_job(user_request)
        print(f"[COMMANDER] Classification: {mode}")

    # Phase 23 Fix #17: Parse --duration flag (default 60s)
    duration_match = re.search(r'--duration\s+(\d+)', user_request)
    target_duration = int(duration_match.group(1)) if duration_match else 60
    if duration_match:
        user_request = re.sub(r'--duration\s+\d+', '', user_request).strip()
        print(f"[COMMANDER] Duration Override Detected: {target_duration}s")

    context_summary = None
    input_source = "YOUTUBE_HARVEST"
    narration_style = "documentary"
    context_rewrite = "off"
    watermark_mode = "on"
    if mode == "MODE_NARRATE":
        user_request, context_summary, context_file, narration_style, context_rewrite, watermark_mode = parse_narrate_runtime_flags(user_request)
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
        print(f"[COMMANDER] Narration Style: {narration_style}")
        print(f"[COMMANDER] Context Rewrite: {context_rewrite}")
        print(f"[COMMANDER] Watermark Mode: {watermark_mode}")

    # Dispatch
    result = dispatch_weapon(
        mode,
        user_request,
        output_path,
        target_duration=target_duration,
        context_summary=context_summary,
        input_source=input_source,
        narration_style=narration_style,
        context_rewrite=context_rewrite,
        watermark_mode=watermark_mode,
    )

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
        })
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
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = input("\n[SUPREME COMMANDER] Enter your video command: ").strip()

    if not request:
        print("No command received. Commander standing down.")
        sys.exit(0)

    supreme_video_commander(request)
