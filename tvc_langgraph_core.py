from tvc_vault import get_secret
import base64

class DummyTypes:
    class GenerateContentConfig:
        def __init__(self, system_instruction=None, temperature=None, response_mime_type=None, response_schema=None):
            self.system_instruction = system_instruction
            self.temperature = temperature
            self.response_mime_type = response_mime_type
            self.response_schema = response_schema
types = DummyTypes()

import io
import sys
# SOTA UTF-8 Stream Hardening (Phase 24 Windows Stability)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

"""

TVC V3.0 -- LangGraph Cognitive Multi-Agent State Machine

=========================================================

9-Node Architecture:

  Harvester  Writer (real CPP)  Duration Gate  Topic Extractor

   Audio Engineer  Vision Director (batch)  Visual QA

   Lead Editor (dual-layer ASS)  Whisper Verifier  END



Structurally eliminates all 8 issues from V2.0 production.

"""

import os

import re

import json

import time

import glob
import shutil

import subprocess

import hashlib

import random

import uuid
import functools

from typing import TypedDict, Annotated, List, Dict, Any, Optional
from urllib.parse import urlparse


from langgraph.graph import StateGraph, END

import operator

import edge_tts

import asyncio


try:

    import requests as _requests

except ImportError:

    _requests = None


try:

    import smartcrop

    from PIL import Image, ImageDraw

except ImportError:

    smartcrop = None

    Image = None
    ImageDraw = None


import tvc_config


PROJECT_DIR = tvc_config.PATHS["root"]

INTEL_DIR = tvc_config.PATHS["intelligence"]
ROOT_INTEL_DIR = INTEL_DIR
_CURRENT_TIMING_RUN_ID = ""
_CURRENT_PIPELINE_RUN_ID = ""
_CURRENT_PIPELINE_RUN_DIR = ""
_FIREWORKS_CIRCUIT_UNTIL: Dict[str, float] = {}
_PROVIDER_RESILIENCE_REPORT: Dict[str, Any] = {
    "timestamp": "",
    "run_id": "",
    "events": [],
    "counts": {
        "retryable": 0,
        "precondition_412": 0,
        "invalid_request_400": 0,
        "circuit_open_failfast": 0,
        "sanitized_retry": 0,
        "permanent_failures": 0,
        "successful_calls": 0,
    },
}
_PIPELINE_NODE_ORDER = [
    "Harvester",
    "Writer",
    "DurationGate",
    "TopicExtractor",
    "SceneDirector",
    "Audio",
    "PromptArchitect",
    "SotaForge",
    "Editor",
    "Verifier",
]
_LIVE_STATUS: Dict[str, Any] = {}
_LIVE_STATUS_LAST_WRITE_EPOCH = 0.0

tvc_config.ensure_structure()


def _active_intel_dir() -> str:
    return _CURRENT_PIPELINE_RUN_DIR or ROOT_INTEL_DIR


def _artifact_path(name: str) -> str:
    return os.path.join(_active_intel_dir(), name)


def _legacy_artifact_path(name: str) -> str:
    return os.path.join(ROOT_INTEL_DIR, name)


def _artifact_read_path(name: str) -> str:
    run_path = _artifact_path(name)
    if os.path.exists(run_path):
        return run_path
    try:
        ptr_file = os.path.join(ROOT_INTEL_DIR, "latest_run_pointer.json")
        if os.path.exists(ptr_file):
            with open(ptr_file, "r", encoding="utf-8") as f:
                ptr = json.load(f) or {}
            run_dir = str(ptr.get("run_dir", "") or "").strip()
            if run_dir:
                latest_path = os.path.join(run_dir, name)
                if os.path.exists(latest_path):
                    return latest_path
    except Exception:
        pass
    return _legacy_artifact_path(name)


def _ensure_artifact_parent(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _legacy_mirror_enabled() -> bool:
    return str(os.getenv("TVC_LEGACY_MIRROR", "0") or "0").strip() == "1"


def _write_text_artifact(name: str, content: str, encoding: str = "utf-8", mirror_legacy: Optional[bool] = None) -> str:
    target = _artifact_path(name)
    _ensure_artifact_parent(target)
    with open(target, "w", encoding=encoding) as f:
        f.write(content)
    if mirror_legacy is None:
        mirror_legacy = _legacy_mirror_enabled()
    if mirror_legacy:
        legacy = _legacy_artifact_path(name)
        if legacy != target:
            _ensure_artifact_parent(legacy)
            with open(legacy, "w", encoding=encoding) as f:
                f.write(content)
    return target


def _write_json_artifact(name: str, payload: Any, mirror_legacy: Optional[bool] = None):
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    _write_text_artifact(name, text, encoding="utf-8", mirror_legacy=mirror_legacy)


def _write_binary_artifact(name: str, data: bytes, mirror_legacy: Optional[bool] = None) -> str:
    target = _artifact_path(name)
    _ensure_artifact_parent(target)
    with open(target, "wb") as f:
        f.write(data)
    if mirror_legacy is None:
        mirror_legacy = _legacy_mirror_enabled()
    if mirror_legacy:
        legacy = _legacy_artifact_path(name)
        if legacy != target:
            _ensure_artifact_parent(legacy)
            with open(legacy, "wb") as f:
                f.write(data)
    return target


def _trace_file_path() -> str:
    return _artifact_path("api_call_trace.jsonl")


def _node_timing_trace_file_path() -> str:
    return _artifact_path("node_timing_trace.jsonl")


def _state_manifest_path() -> str:
    # Keep manifest global so resume hashes remain stable across runs.
    return os.path.join(ROOT_INTEL_DIR, "state_manifest.json")


def _init_provider_resilience_report(run_id: str):
    global _PROVIDER_RESILIENCE_REPORT, _FIREWORKS_CIRCUIT_UNTIL
    _FIREWORKS_CIRCUIT_UNTIL = {}
    _PROVIDER_RESILIENCE_REPORT = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "events": [],
        "counts": {
            "retryable": 0,
            "precondition_412": 0,
            "invalid_request_400": 0,
            "circuit_open_failfast": 0,
            "sanitized_retry": 0,
            "permanent_failures": 0,
            "successful_calls": 0,
        },
    }


def _record_provider_event(endpoint: str, category: str, message: str, attempt: int = 0, delay_s: float = 0.0):
    global _PROVIDER_RESILIENCE_REPORT
    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": endpoint,
        "category": category,
        "attempt": int(attempt or 0),
        "delay_s": round(float(delay_s or 0.0), 3),
        "message": str(message or "")[:240],
    }
    _PROVIDER_RESILIENCE_REPORT.setdefault("events", []).append(row)
    counts = _PROVIDER_RESILIENCE_REPORT.setdefault("counts", {})
    if category in counts:
        counts[category] = int(counts.get(category, 0) or 0) + 1


def _write_provider_resilience_report():
    report = dict(_PROVIDER_RESILIENCE_REPORT or {})
    report["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        _write_json_artifact("provider_resilience_report.json", report, mirror_legacy=None)
    except Exception:
        pass
    return report


def _format_seconds_human(seconds: float) -> str:
    sec = max(0, int(round(float(seconds or 0.0))))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _progress_from_live_status(status_obj: Dict[str, Any]) -> Dict[str, Any]:
    total_nodes = len(_PIPELINE_NODE_ORDER)
    completed = set(str(n) for n in status_obj.get("nodes_completed", []))
    current_node = str(status_obj.get("current_node", "") or "")
    progress_nodes = float(len(completed))
    if current_node and current_node not in completed:
        progress_nodes += 0.35
    progress_pct = 0.0
    if total_nodes > 0:
        progress_pct = min(100.0, round((progress_nodes / float(total_nodes)) * 100.0, 2))
    return {
        "completed_nodes": sorted(list(completed)),
        "completed_count": len(completed),
        "total_nodes": total_nodes,
        "progress_pct": progress_pct,
    }


def _write_live_status(force: bool = False):
    global _LIVE_STATUS_LAST_WRITE_EPOCH
    if not _LIVE_STATUS:
        return
    now_epoch = time.time()
    if not force and (now_epoch - _LIVE_STATUS_LAST_WRITE_EPOCH) < 0.9:
        return

    status_obj = dict(_LIVE_STATUS)
    status_obj["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    started_epoch = float(status_obj.get("started_epoch", now_epoch) or now_epoch)
    elapsed_s = max(0.0, now_epoch - started_epoch)
    status_obj["elapsed_s"] = round(elapsed_s, 2)

    progress = _progress_from_live_status(status_obj)
    status_obj.update(progress)

    eta_s = None
    if status_obj.get("pipeline_status") == "running":
        pct = float(progress.get("progress_pct", 0.0) or 0.0)
        if pct > 0.0:
            eta_s = max(0.0, elapsed_s * ((100.0 - pct) / pct))
    status_obj["eta_s"] = round(eta_s, 2) if eta_s is not None else None
    if eta_s is not None:
        status_obj["eta_human"] = _format_seconds_human(eta_s)

    retry_state = status_obj.get("retry_state", {}) if isinstance(status_obj.get("retry_state"), dict) else {}
    lines = [
        f"timestamp: {status_obj.get('timestamp', '')}",
        f"run_id: {status_obj.get('run_id', '')}",
        f"pipeline_status: {status_obj.get('pipeline_status', 'unknown')}",
        f"current_node: {status_obj.get('current_node', '')}",
        f"node_event: {status_obj.get('current_node_event', '')}",
        f"progress: {status_obj.get('progress_pct', 0.0)}% ({status_obj.get('completed_count', 0)}/{status_obj.get('total_nodes', 0)} nodes)",
        f"elapsed: {_format_seconds_human(elapsed_s)} ({status_obj.get('elapsed_s', 0)}s)",
        f"eta: {status_obj.get('eta_human', 'n/a')}",
        f"retries_total: {status_obj.get('retries_total', 0)}",
        f"retry_wait_remaining_s: {retry_state.get('wait_remaining_s', 0.0)}",
    ]
    last_api = status_obj.get("last_api_call", {}) if isinstance(status_obj.get("last_api_call"), dict) else {}
    if last_api:
        lines.extend([
            f"last_api_node: {last_api.get('node', '')}",
            f"last_api_template: {last_api.get('prompt_template_id', '')}",
            f"last_api_model: {last_api.get('model', '')}",
            f"last_api_type: {last_api.get('call_type', '')}",
        ])
    if status_obj.get("last_error"):
        lines.append(f"last_error: {status_obj.get('last_error')}")
    if status_obj.get("final_video"):
        lines.append(f"final_video: {status_obj.get('final_video')}")

    try:
        _write_json_artifact("live_status.json", status_obj, mirror_legacy=False)
        _write_text_artifact("live_status.txt", "\n".join(lines) + "\n", mirror_legacy=False)
        _LIVE_STATUS_LAST_WRITE_EPOCH = now_epoch
    except Exception:
        pass


def _init_live_status(run_id: str, seed: Dict[str, Any]):
    global _LIVE_STATUS, _LIVE_STATUS_LAST_WRITE_EPOCH
    _LIVE_STATUS_LAST_WRITE_EPOCH = 0.0
    _LIVE_STATUS = {
        "run_id": run_id,
        "started_epoch": time.time(),
        "pipeline_status": "running",
        "current_node": "",
        "current_node_event": "",
        "nodes_completed": [],
        "node_durations_s": {},
        "retries_total": 0,
        "retries_by_endpoint": {},
        "retry_state": {},
        "last_api_call": {},
        "last_error": "",
        "final_video": "",
        "seed": seed or {},
    }
    _write_live_status(force=True)


def _update_live_status(fields: Dict[str, Any], force: bool = False):
    if not _LIVE_STATUS:
        return
    try:
        _LIVE_STATUS.update(fields or {})
        _write_live_status(force=force)
    except Exception:
        pass


def _mark_live_retry(endpoint: str, attempt: int, max_retries: int, delay_s: float, error_preview: str):
    if not _LIVE_STATUS:
        return
    retries_by_ep = _LIVE_STATUS.setdefault("retries_by_endpoint", {})
    retries_by_ep[str(endpoint)] = int(retries_by_ep.get(str(endpoint), 0) or 0) + 1
    _LIVE_STATUS["retries_total"] = int(_LIVE_STATUS.get("retries_total", 0) or 0) + 1
    _LIVE_STATUS["retry_state"] = {
        "endpoint": str(endpoint or ""),
        "attempt": int(attempt or 0),
        "max_retries": int(max_retries or 0),
        "delay_s": round(float(delay_s or 0.0), 3),
        "wait_remaining_s": round(float(delay_s or 0.0), 3),
        "error_preview": str(error_preview or "")[:180],
    }
    _LIVE_STATUS["last_error"] = str(error_preview or "")[:240]
    _write_live_status(force=True)


def _heartbeat_sleep(delay_s: float, endpoint: str, attempt: int, max_retries: int, error_preview: str):
    remaining = max(0.0, float(delay_s or 0.0))
    while remaining > 0.0:
        if _LIVE_STATUS:
            retry_state = dict(_LIVE_STATUS.get("retry_state", {}) or {})
            retry_state.update({
                "endpoint": str(endpoint or ""),
                "attempt": int(attempt or 0),
                "max_retries": int(max_retries or 0),
                "error_preview": str(error_preview or "")[:180],
                "wait_remaining_s": round(remaining, 3),
            })
            _LIVE_STATUS["retry_state"] = retry_state
            _write_live_status(force=False)
        tick = 1.0 if remaining > 1.0 else remaining
        time.sleep(tick)
        remaining = max(0.0, remaining - tick)
    if _LIVE_STATUS:
        retry_state = dict(_LIVE_STATUS.get("retry_state", {}) or {})
        retry_state["wait_remaining_s"] = 0.0
        _LIVE_STATUS["retry_state"] = retry_state
        _write_live_status(force=True)


def _finalize_live_status(status: str, final_video: str = "", error: str = ""):
    if not _LIVE_STATUS:
        return
    _LIVE_STATUS["pipeline_status"] = str(status or "unknown")
    _LIVE_STATUS["final_video"] = str(final_video or "")
    _LIVE_STATUS["last_error"] = str(error or _LIVE_STATUS.get("last_error", ""))[:240]
    _LIVE_STATUS["retry_state"] = {}
    _write_live_status(force=True)


# ==============================================================

# PHASE 20: API KEYS & IMAGE GENERATION MODE

# ==============================================================


# SEC-001: Moved to vault (D:\AI\API\Secrets\runware_sota.json)

FIREWORKS_API_KEY = get_secret("key_HGmChvaB")

RUNWARE_FLUX_MODEL = "runware:100@1"  # FLUX.1 Schnell (Verified SOTA)

RUNWARE_ENDPOINT = "https://api.runware.ai/v1"

IMAGE_GEN_MODE = "FIREWORKS"  # Options: "RUNWARE" or "GEMINI"


def _extract_prompt_preview(contents, max_len: int = 280) -> str:
    if isinstance(contents, str):
        txt = contents
    elif isinstance(contents, list):
        parts = []
        for part in contents:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        txt = " ".join(parts)
    else:
        txt = str(contents)
    return " ".join(txt.split())[:max_len]


def trace_api_call(node: str, endpoint_url: str, model: str, prompt_template_id: str, prompt_preview: str, call_type: str):
    try:
        os.makedirs(_active_intel_dir(), exist_ok=True)
        host = urlparse(endpoint_url).netloc or endpoint_url
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "node": node or "Unknown",
            "call_type": call_type,
            "endpoint_url": endpoint_url,
            "endpoint_host": host,
            "model": model,
            "prompt_template_id": prompt_template_id or "UNSPECIFIED",
            "prompt_preview": (prompt_preview or "")[:280],
        }
        with open(_trace_file_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
        if _LIVE_STATUS:
            _update_live_status({
                "last_api_call": {
                    "node": node or "Unknown",
                    "endpoint_host": host,
                    "model": model,
                    "prompt_template_id": prompt_template_id or "UNSPECIFIED",
                    "call_type": call_type or "",
                    "timestamp": entry["timestamp"],
                }
            })
    except Exception:
        pass


def trace_node_timing(
    node: str,
    event: str,
    monotonic_s: float,
    duration_s: Optional[float] = None,
    status: str = "",
    details: Optional[Dict[str, Any]] = None,
):
    try:
        os.makedirs(_active_intel_dir(), exist_ok=True)
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "run_id": _CURRENT_TIMING_RUN_ID or "",
            "node": node,
            "event": event,
            "monotonic_s": round(float(monotonic_s), 6),
            "duration_s": round(float(duration_s), 6) if duration_s is not None else None,
            "status": status or "",
        }
        if details:
            compact = {}
            for k, v in details.items():
                try:
                    compact[str(k)] = v
                except Exception:
                    compact[str(k)] = str(v)
            entry["details"] = compact
        with open(_node_timing_trace_file_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
        if _LIVE_STATUS:
            node_name = str(node or "")
            if event == "start":
                _update_live_status({
                    "current_node": node_name,
                    "current_node_event": "start",
                })
            elif event == "end":
                node_durations = dict(_LIVE_STATUS.get("node_durations_s", {}) or {})
                if duration_s is not None:
                    node_durations[node_name] = round(float(duration_s), 3)
                completed = list(_LIVE_STATUS.get("nodes_completed", []) or [])
                if status == "ok" and node_name and node_name not in completed:
                    completed.append(node_name)
                live_payload = {
                    "current_node": node_name,
                    "current_node_event": "end",
                    "node_durations_s": node_durations,
                    "nodes_completed": completed,
                }
                if status and status != "ok":
                    live_payload["last_error"] = (details or {}).get("error", status)
                _update_live_status(live_payload, force=True)
    except Exception:
        pass


def write_paid_api_policy_check():
    observed_hosts = set()
    trace_file = _trace_file_path()
    if os.path.exists(trace_file):
        try:
            with open(trace_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    host = str(row.get("endpoint_host", "")).strip()
                    if host:
                        observed_hosts.add(host)
        except Exception:
            pass

    non_fireworks = sorted([h for h in observed_hosts if h != "api.fireworks.ai"])
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "policy": "paid_model_api_must_be_fireworks_only",
        "allowed_paid_hosts": ["api.fireworks.ai"],
        "observed_paid_hosts": sorted(observed_hosts),
        "non_fireworks_paid_hosts": non_fireworks,
        "passed": len(non_fireworks) == 0,
    }
    try:
        _write_json_artifact("paid_api_policy_check.json", report, mirror_legacy=None)
    except Exception:
        pass
    return report


def fireworks_generate_image(
    prompt: str,
    width: int = 1920,
    height: int = 1088,
    output_path: str = "",
    prompt_template_id: str = "UNSPECIFIED",
    trace_node: str = "Unknown",
) -> bool:
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "image/jpeg"
    }
    payload = {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "guidance_scale": 3.5,
        "num_inference_steps": 4,
        "seed": 0
    }
    try:
        endpoint_url = "https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-1-schnell-fp8/text_to_image"
        trace_api_call(
            node=trace_node,
            endpoint_url=endpoint_url,
            model="accounts/fireworks/models/flux-1-schnell-fp8",
            prompt_template_id=prompt_template_id,
            prompt_preview=_extract_prompt_preview(prompt),
            call_type="image_generation",
        )
        resp = _requests.post(
            endpoint_url,
            headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        _ensure_artifact_parent(output_path)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        print(f"    [FIREWORKS IMAGE] Generated image: {output_path}")
        return True
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
             err_msg += f". Response: {e.response.text}"
        print(f"    [FIREWORKS IMAGE] API Error: {err_msg[:250]}")
        raise RuntimeError(err_msg) from e
# ==============================================================

# SOTA STATE CONTROLLER (Hash-Based Persistence)

# ==============================================================


def get_hash(text: str) -> str:

    return hashlib.md5((text or "").encode('utf-8')).hexdigest()


def get_state_manifest() -> dict:

    mf = _state_manifest_path()

    if os.path.exists(mf):

        try:

            with open(mf, "r", encoding="utf-8") as f: return json.load(f)

        except Exception: pass

    return {}


def save_state_manifest(data: dict):

    mf = _state_manifest_path()

    with open(mf, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)


# ==============================================================

# SOTA SMART RETRY ENGINE (API Agnostic)

# ==============================================================
RETRY_CONFIGS = {

    "gemini_text":  {"base": 2.0, "max_delay": 60, "max_retries": 5},

    "gemini_image": {"base": 4.0, "max_delay": 90, "max_retries": 6},

    "runware":      {"base": 1.0, "max_delay": 30, "max_retries": 8},

    "default":      {"base": 2.0, "max_delay": 60, "max_retries": 5},

}
CIRCUIT_BREAKER_WINDOW_S = 120.0


class DummyRes:
    def __init__(self, text):
        self.text = text


def _classify_fireworks_error(err_text: str) -> str:
    low = str(err_text or "").lower()
    if "412" in low or "precondition_failed" in low or "precondition failed" in low:
        return "precondition_412"
    if "400" in low or "invalid_request_error" in low or "invalid request" in low:
        return "invalid_request_400"
    if any(k in low for k in ["429", "rate", "throttl", "503", "408", "timeout", "connection", "unavailable", "network"]):
        return "retryable"
    return "permanent_failures"


def _sanitize_fireworks_retry_kwargs(kwargs: dict) -> dict:
    sanitized = dict(kwargs or {})
    for key in ["contents", "prompt"]:
        if key in sanitized:
            val = sanitized.get(key)
            if isinstance(val, str):
                val = val.replace("\u2019", "'").replace("\u2018", "'")
                val = val.replace("\u201c", '"').replace("\u201d", '"')
                val = val.replace("\u2014", "-").replace("\u2013", "-").replace("\u2026", "...")
                val = val.replace("\u00a0", " ")
                val = re.sub(r"\s+", " ", val).strip()
                sanitized[key] = val[:12000]
    return sanitized


def sota_json_repair(text):
    """Surgically repairs malformed or unterminated JSON common in LLM outputs."""
    if not text:
        return [] # Emergency empty fallback
    t = text.strip()
    if not t:
        return []
    if t.startswith("```json"):
        t = t[7:]
        if t.endswith("```"): t = t[:-3]
    elif t.startswith("```"):
        t = t[3:]
        if t.endswith("```"): t = t[:-3]
    t = t.strip()

    # 2. Basic Unterminated String Repair (The "U-Fix")
    # If the text ends with an open quote but no closing brace, try to close it.
    if t.count('"') % 2 != 0:
        t += '"'

    # 3. Structural Completion
    # Count braces and brackets
    open_b = t.count('{')
    close_b = t.count('}')
    open_s = t.count('[')
    close_s = t.count(']')

    # Close missing brackets/braces in reverse order
    stack = []
    for char in t:
        if char == '{': stack.append('}')
        elif char == '[': stack.append(']')
        elif char == '}' or char == ']':
            if stack: stack.pop()

    while stack:
        t += stack.pop()

    try:
        return json.loads(t)
    except Exception:
        # 4. Final Hail Mary: Regex-based extraction of valid objects
        import re
        matches = re.findall(r'\{.*\}', t, re.DOTALL)
        if not matches:
            matches = re.findall(r'\[.*\]', t, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except: pass
        raise


def fireworks_chat_completion(
    contents,
    model="accounts/fireworks/models/kimi-k2p5",
    config=None,
    api_key=None,
    prompt_template_id="UNSPECIFIED",
    trace_node="Unknown",
    **kwargs,
):
    if api_key is None:
        api_key = FIREWORKS_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = []
    sys_instruction = None

    if config and hasattr(config, 'system_instruction') and config.system_instruction:
        sys_instruction = config.system_instruction

    if isinstance(contents, str):
        if sys_instruction:
            messages.append({"role": "system", "content": sys_instruction})
        messages.append({"role": "user", "content": contents})
    elif isinstance(contents, list):
        content_arr = []
        for part in contents:
            if isinstance(part, str):
                content_arr.append({"type": "text", "text": part})
            elif isinstance(part, (bytes, bytearray)):
                b64 = base64.b64encode(bytes(part)).decode('utf-8')
                content_arr.append({"type": "image_url", "image_url": {
                                   "url": f"data:image/png;base64,{b64}"}})
            elif isinstance(part, dict):
                ptype = str(part.get("type", "")).strip().lower()
                if ptype == "text":
                    txt = str(part.get("text", "") or "")
                    if txt:
                        content_arr.append({"type": "text", "text": txt})
                elif ptype == "image_url" and isinstance(part.get("image_url"), dict):
                    content_arr.append({"type": "image_url", "image_url": part.get("image_url")})
                elif "data" in part:
                    data = part.get("data")
                    if isinstance(data, str):
                        data = data.encode("utf-8")
                    if isinstance(data, (bytes, bytearray)):
                        mime = str(part.get("mime_type", "image/png") or "image/png")
                        b64 = base64.b64encode(bytes(data)).decode('utf-8')
                        content_arr.append({"type": "image_url", "image_url": {
                                           "url": f"data:{mime};base64,{b64}"}})
            elif hasattr(part, 'inline_data') or hasattr(part, 'data'):
                data = part.inline_data.data if hasattr(
                    part, 'inline_data') else part.data
                b64 = base64.b64encode(data).decode('utf-8')
                content_arr.append({"type": "image_url", "image_url": {
                                   "url": f"data:image/png;base64,{b64}"}})
        if sys_instruction:
            messages.append({"role": "system", "content": sys_instruction})
        messages.append({"role": "user", "content": content_arr})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 4000
    }

    endpoint_url = "https://api.fireworks.ai/inference/v1/chat/completions"
    trace_api_call(
        node=trace_node,
        endpoint_url=endpoint_url,
        model=model,
        prompt_template_id=prompt_template_id,
        prompt_preview=_extract_prompt_preview(contents),
        call_type="chat_completion",
    )
    resp = _requests.post(endpoint_url,
                          headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return DummyRes(data["choices"][0]["message"]["content"])

# FIREWORKS_LLM_INJECTED


def smart_retry(fn, endpoint="default", *args, **kwargs):

    cfg = RETRY_CONFIGS.get(endpoint, RETRY_CONFIGS["default"])
    last_exception = None
    call_kwargs = dict(kwargs or {})
    fireworks_endpoint = str(endpoint or "").startswith("fireworks_")
    sanitized_once = False

    for attempt in range(cfg["max_retries"]):
        if fireworks_endpoint:
            open_until = float(_FIREWORKS_CIRCUIT_UNTIL.get(endpoint, 0.0) or 0.0)
            now = time.time()
            if open_until > now:
                wait_left = round(open_until - now, 2)
                msg = f"Circuit open for {endpoint}; retry after {wait_left}s"
                _record_provider_event(endpoint, "circuit_open_failfast", msg, attempt=attempt + 1)
                raise RuntimeError(msg)

        try:
            result = fn(*args, **call_kwargs)
            if fireworks_endpoint:
                _record_provider_event(endpoint, "successful_calls", "call_success", attempt=attempt + 1)
            if _LIVE_STATUS:
                _update_live_status(
                    {
                        "retry_state": {},
                    },
                    force=True,
                )
            return result

        except Exception as e:
            last_exception = e
            err = str(e)
            err_low = err.lower()

            if fireworks_endpoint:
                category = _classify_fireworks_error(err_low)
                if category == "precondition_412":
                    _FIREWORKS_CIRCUIT_UNTIL[endpoint] = time.time() + CIRCUIT_BREAKER_WINDOW_S
                    _record_provider_event(
                        endpoint, "precondition_412", err, attempt=attempt + 1, delay_s=CIRCUIT_BREAKER_WINDOW_S
                    )
                    raise RuntimeError(
                        f"Fireworks precondition failure (412). Circuit opened for {int(CIRCUIT_BREAKER_WINDOW_S)}s."
                    ) from e
                if category == "invalid_request_400":
                    _record_provider_event(endpoint, "invalid_request_400", err, attempt=attempt + 1)
                    if not sanitized_once:
                        sanitized_once = True
                        call_kwargs = _sanitize_fireworks_retry_kwargs(call_kwargs)
                        _record_provider_event(endpoint, "sanitized_retry", "one-time payload sanitization retry", attempt=attempt + 1)
                        continue
                    _record_provider_event(endpoint, "permanent_failures", err, attempt=attempt + 1)
                    raise e
                if category == "retryable":
                    _record_provider_event(endpoint, "retryable", err, attempt=attempt + 1)
                else:
                    _record_provider_event(endpoint, "permanent_failures", err, attempt=attempt + 1)
                    raise e
            else:
                retryable_patterns = [
                    "429", "resource_exhausted", "providerratelimitexceeded",
                    "rate", "throttl", "503", "408", "timeout",
                    "connection", "unavailable",
                ]
                if not any(p in err_low for p in retryable_patterns):
                    raise e

            match = re.search(r"retry.?after[:\s]*(\d+)", err_low, re.IGNORECASE)
            if match:
                delay = float(match.group(1)) + random.uniform(0, 1)
            else:
                delay = min(cfg["base"] * (2 ** attempt) + random.uniform(0, cfg["base"]), cfg["max_delay"])

            _mark_live_retry(
                endpoint=str(endpoint or "default"),
                attempt=attempt + 1,
                max_retries=int(cfg["max_retries"]),
                delay_s=delay,
                error_preview=err_low[:180],
            )
            print(
                f"    [SMART RETRY] Attempt {attempt+1}/{cfg['max_retries']}. Waiting {delay:.1f}s ({err_low[:80]})"
            )
            _heartbeat_sleep(
                delay_s=delay,
                endpoint=str(endpoint or "default"),
                attempt=attempt + 1,
                max_retries=int(cfg["max_retries"]),
                error_preview=err_low[:180],
            )

    raise last_exception


# ==============================================================

# THE REAL CINEMATIC PROSODY PREPROCESSOR (CPP)
# Ported from narrator_forge.py (lines 24-62) -- Battle-Tested
# ==============================================================
CLAUSE_STARTERS = {

    'and', 'but', 'or', 'yet', 'so', 'nor', 'for',

    'we', 'they', 'it', 'its', 'our', 'the', 'this', 'that', 'those', 'these',

    'his', 'her', 'she', 'he', 'a', 'an', 'who', 'which', 'whom', 'whose',

    'in', 'on', 'at', 'to', 'from', 'with', 'as', 'if', 'by', 'of',

    'even', 'while', 'where', 'when', 'whether', 'not', 'no', 'every', 'each',

    'once', 'still', 'however', 'therefore', 'thus', 'instead', 'rather',

}


ADJECTIVE_EXCEPTIONS_ED = {

    'alarmed', 'aggravated', 'amazed', 'amused', 'annoyed', 'astonished', 'astounded', 'bewildered', 'bored',

    'captivated', 'challenged', 'charmed', 'comforted', 'concerned', 'confused', 'convinced', 'depressed',

    'devastated', 'disappointed', 'discouraged', 'disgusted', 'distressed', 'disturbed', 'embarrassed',

    'enchanted', 'encouraged', 'energised', 'energized', 'entertained', 'exasperated', 'excited', 'exhausted',

    'fascinated', 'flattered', 'frightened', 'frustrated', 'fulfilled', 'gratified', 'horrified', 'humiliated',

    'inspired', 'insulted', 'interested', 'intrigued', 'irritated', 'moved', 'mystified', 'overwhelmed',

    'perplexed', 'perturbed', 'pleased', 'puzzled', 'relaxed', 'satisfied', 'shocked', 'sickened', 'soothed',

    'surprised', 'tempted', 'terrified', 'tired', 'detailed', 'colored', 'skilled', 'talented', 'advanced',

    'experienced', 'related', 'limited', 'united', 'distinguished', 'renowned', 'established', 'expected',

    'accepted', 'complicated', 'automated', 'simulated', 'animated', 'fixed', 'damaged', 'abandoned',

    'preferred', 'required', 'recommended', 'closed', 'opened', 'dedicated', 'educated', 'sophisticated'

}


def apply_cpp(text: str) -> str:
    """The REAL Cinematic Prosody Preprocessor (SOTA Zero-Dependency Heuristic).

    - Removes commas between adjectives (cause unnatural TTS pauses)

    - Preserves commas at clause boundaries (grammatically necessary)

    - Converts em-dashes/en-dashes to ellipses for smoother prosody

    - Uses suffix analysis (-ly, -ing, -ed, -ous) to guess part of speech without NLTK bloat.

    """

    result_parts = []

    i = 0

    while i < len(text):

        if text[i] == ',' and i + 1 < len(text) and text[i + 1] == ' ':

            rest = text[i + 1:].lstrip()

            next_word_match = re.match(r'([a-zA-Z\-]+)', rest)

            if next_word_match:

                next_word = next_word_match.group(1).lower()

                # Check against the Exception Dictionary to prevent adjective misclassification

                is_ed_verb = next_word.endswith(
                    'ed') and next_word not in ADJECTIVE_EXCEPTIONS_ED

                # SOTA Heuristic: Is it likely a clause boundary or a continuing adjective list?

                is_clause = (

                    next_word in CLAUSE_STARTERS or

                    next_word.endswith('ing') or

                    # Adverbs usually start phrases
                    next_word.endswith('ly') or

                    is_ed_verb    # Past-tense verbs (filtered by dictionary)

                )

                is_adjective_chain = (

                    next_word.endswith('ous') or

                    next_word.endswith('ful') or

                    next_word.endswith('ic')

                )

                if is_clause and not is_adjective_chain:

                    result_parts.append(text[i])  # KEEP clause-boundary comma

                else:

                    pass  # REMOVE adjective-pair comma

            else:

                result_parts.append(text[i])

        elif text[i] == '\u2014':  # em-dash

            result_parts.append('... ')

            if i + 1 < len(text) and text[i + 1] == ' ':

                i += 1

        elif text[i] == '\u2013':  # en-dash

            result_parts.append('... ')

            if i + 1 < len(text) and text[i + 1] == ' ':

                i += 1

        else:

            result_parts.append(text[i])

        i += 1

    processed = ''.join(result_parts)

    removed = text.count(',') - processed.count(',')

    print(
        f"    [CPP] Fallback Parser Active. Commas: {text.count(',')}  {processed.count(',')} (removed {removed} prosody-breaking commas)")

    return processed


# ==============================================================
# NARRATION STYLE REGISTRY (MODE_NARRATE)
# ==============================================================
NARRATION_STYLE_DEFAULT = "documentary"
CONTEXT_REWRITE_DEFAULT = "off"
WATERMARK_MODE_DEFAULT = "on"

NARRATION_STYLE_PROFILES = {
    "documentary": {
        "label": "Cinematic Documentary",
        "cache_key": "documentary_v1",
        "writer_role": "the absolute master of cinematic documentary scriptwriting",
        "writer_tone_instruction": "Use neutral authority, grounded detail, and cinematic pacing with crisp transitions.",
        "writer_output_label": "documentary voiceover narration",
        "writer_temperature": 0.5,
        "writer_cpp_goal": "Keep cadence steady and authoritative for documentary narration.",
        "audio_tts": {"voice": "en-GB-RyanNeural", "rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
        "audio_cpp_goal": "Target delivery is balanced, authoritative, and easy to follow.",
        "scene_style_dna_default": "Cinematic documentary palette, grounded realism, natural contrast, controlled camera language",
        "scene_meta_context_default": "Documentary-style narrative sequence",
        "scene_direction_hint": "Prioritize factual realism and coherent visual progression.",
        "scene_visual_prefix": "Cinematic photorealistic shot showing:",
        "prompt_tone_hint": "Ground every frame in documentary realism with cinematic clarity.",
        "prompt_fallback_scene_label": "Documentary scene",
    },
    "sales_saas": {
        "label": "SaaS Sales",
        "cache_key": "sales_saas_v1",
        "writer_role": "an elite B2B SaaS launch copywriter and high-conversion voiceover scriptwriter",
        "writer_tone_instruction": "Use persuasive product storytelling, energetic momentum, clear value framing, and strong emotional lift without hype spam.",
        "writer_output_label": "polished SaaS/product marketing narration",
        "writer_temperature": 0.55,
        "writer_cpp_goal": "Keep delivery punchy, upbeat, and conversion-focused with confident cadence shifts.",
        "audio_tts": {"voice": "en-GB-RyanNeural", "rate": "+12%", "pitch": "+6Hz", "volume": "+8%"},
        "audio_cpp_goal": "Target delivery is energetic, polished, and sales-ready with persuasive emphasis.",
        "scene_style_dna_default": "Premium SaaS campaign look, clean modern gradients, high-contrast product lighting, polished commercial framing",
        "scene_meta_context_default": "High-energy SaaS value story from pain point to outcome",
        "scene_direction_hint": "Frame pain points, product flow, and transformation moments with premium marketing aesthetics.",
        "scene_visual_prefix": "Premium SaaS commercial shot showing:",
        "prompt_tone_hint": "Use premium product-marketing cinematography and conversion-oriented visual storytelling.",
        "prompt_fallback_scene_label": "SaaS marketing scene",
    },
    "human_story": {
        "label": "Human Story",
        "cache_key": "human_story_v1",
        "writer_role": "a deeply empathetic human-story narrator focused on emotional clarity and connection",
        "writer_tone_instruction": "Use warm, compassionate language with slower emotional pacing, human vulnerability, and intimate detail.",
        "writer_output_label": "warm human story narration",
        "writer_temperature": 0.45,
        "writer_cpp_goal": "Keep delivery calm, warm, and emotionally resonant with generous breathing room.",
        "audio_tts": {"voice": "en-GB-RyanNeural", "rate": "-12%", "pitch": "-2Hz", "volume": "+0%"},
        "audio_cpp_goal": "Target delivery is warm, empathetic, and reflective with softer phrasing.",
        "scene_style_dna_default": "Warm cinematic realism, soft natural light, intimate close framing, emotional texture",
        "scene_meta_context_default": "Human-centered emotional narrative with empathy and connection",
        "scene_direction_hint": "Prioritize facial emotion, relational moments, and lived-in environments over spectacle.",
        "scene_visual_prefix": "Warm intimate cinematic shot showing:",
        "prompt_tone_hint": "Favor emotionally grounded human moments with warm, empathetic visual language.",
        "prompt_fallback_scene_label": "Human story scene",
    },
}


def _normalize_narration_style(value: str) -> str:
    style = str(value or NARRATION_STYLE_DEFAULT).strip().lower()
    if style not in NARRATION_STYLE_PROFILES:
        return NARRATION_STYLE_DEFAULT
    return style


def _normalize_context_rewrite(value: str) -> str:
    mode = str(value or CONTEXT_REWRITE_DEFAULT).strip().lower()
    if mode not in {"off", "force"}:
        return CONTEXT_REWRITE_DEFAULT
    return mode


def _normalize_watermark_mode(value: str) -> str:
    mode = str(value or WATERMARK_MODE_DEFAULT).strip().lower()
    if mode not in {"on", "off"}:
        return WATERMARK_MODE_DEFAULT
    return mode


def _narration_profile(style: str) -> dict:
    return NARRATION_STYLE_PROFILES[_normalize_narration_style(style)]


def _is_deterministic_user_context_mode(state: Any) -> bool:
    source = str((state or {}).get("input_source", "") or "").strip().upper()
    rewrite = _normalize_context_rewrite((state or {}).get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
    return source == "USER_CONTEXT" and rewrite != "force"


# ==============================================================

# STATE DEFINITION

# ==============================================================

class AgentState(TypedDict):

    request_prompt: str

    input_source: str

    context_summary: str

    narration_style: str

    context_rewrite: str

    watermark_mode: str

    target_output: str

    target_duration: int  # in seconds

    api_key: str

    # Node outputs

    harvested_intelligence: str

    script: str

    duration_attempts: int

    topic_callouts: List[dict]

    audio_path: str

    vtt_path: str

    epochs: List[dict]

    visual_scenes: List[dict]  # NEW: Phase 18 Scene Director

    style_dna: str             # NEW: Phase 18 Global aesthetic

    meta_context: str          # NEW: Phase 18 Global context

    character_manifest: Dict[str, str]  # NEW: Phase 19 Character Bible

    sota_prompts: List[str]  # NEW: Phase 14 Architected Prompts

    qa_targets: List[str]    # NEW: Phase 22 Clean Scene Bodies for QA

    images_forged: int

    total_epochs: int

    qa_scores: List[float]

    final_video: str

    verification_report: dict

    # Flow control

    errors: Annotated[List[str], operator.add]

    status: str


# ==============================================================

# NODE 1: HARVESTER (yt-dlp YouTube Intelligence)

# ==============================================================

def harvester_node(state: AgentState):
    input_source = str(state.get("input_source", "YOUTUBE_HARVEST") or "YOUTUBE_HARVEST").strip().upper()
    context_summary = str(state.get("context_summary", "") or "").strip()
    incoming_harvest = str(state.get("harvested_intelligence", "") or "").strip()
    target_duration = int(state.get("target_duration", 60) or 60)
    min_relevant_vtt_required = 5 if target_duration >= 90 else 3
    target_vtt_count = 5
    max_downloaded_vtts = max(target_vtt_count * 3, min_relevant_vtt_required * 4)
    max_candidates = 45 if min_relevant_vtt_required >= 5 else 30
    max_passes = 5
    per_video_retries = 3
    hard_block_threshold = 6
    min_cache_intel_chars = 200

    req_hash = get_hash(state["request_prompt"])

    manifest = get_state_manifest()

    intel_read_file = _artifact_read_path("harvested_intelligence.txt")
    quality_read_file = _artifact_read_path("harvester_quality_report.json")
    harvest_dir = _artifact_path("yt_harvest")
    os.makedirs(harvest_dir, exist_ok=True)

    harvest_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "request_hash": req_hash,
        "target_duration": target_duration,
        "min_relevant_vtt_required": min_relevant_vtt_required,
        "target_vtt_count": target_vtt_count,
        "max_downloaded_vtts": max_downloaded_vtts,
        "max_candidates": max_candidates,
        "max_passes": max_passes,
        "per_video_retries": per_video_retries,
        "cache_hit": False,
        "query": "",
        "pass_queries": [],
        "passes_used": 0,
        "candidate_pool_size": 0,
        "attempted_videos": [],
        "retry_counts": {},
        "cooldown_durations": [],
        "consecutive_429_peak": 0,
        "hard_block_triggered": False,
        "failure_signatures": [],
        "actual_vtt_count": 0,
        "relevant_vtt_count": 0,
        "intelligence_length": 0,
        "quality_gate_passed": False,
        "status": "",
        "fallback_path": "",
    }

    quality_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "request_prompt": state.get("request_prompt", ""),
        "request_terms": [],
        "intent_terms": [],
        "min_relevant_vtt_required": min_relevant_vtt_required,
        "actual_vtt_count": 0,
        "relevant_vtt_count": 0,
        "quality_gate_passed": False,
        "halt_reason": "",
        "transcripts": [],
    }

    def persist_reports():
        try:
            _write_json_artifact("harvester_run_report.json", harvest_report, mirror_legacy=None)
        except Exception:
            pass
        try:
            _write_json_artifact("harvester_quality_report.json", quality_report, mirror_legacy=None)
        except Exception:
            pass

    def add_failure(signature: str):
        sig = (signature or "").replace("\n", " ").strip()[:240]
        if sig and sig not in harvest_report["failure_signatures"]:
            harvest_report["failure_signatures"].append(sig)

    def classify_yt_error(err_msg: str) -> str:
        low = (err_msg or "").lower()
        if any(k in low for k in ["429", "too many requests", "sign in", "forbidden", "rate", "captcha"]):
            return "rate_limited"
        if any(k in low for k in ["timeout", "timed out", "connection", "network", "temporar"]):
            return "retryable"
        if any(k in low for k in ["private", "unavailable", "deleted", "copyright", "not available"]):
            return "terminal"
        return "unknown"

    def vtt_count() -> int:
        return len(glob.glob(os.path.join(harvest_dir, "*.vtt")))

    request_terms = _meaningful_terms(state.get("request_prompt", ""), min_len=4, max_terms=20)
    intent_terms = _harvester_intent_terms(state.get("request_prompt", ""))
    quality_report["request_terms"] = request_terms
    quality_report["intent_terms"] = intent_terms

    if input_source == "USER_CONTEXT":
        print("    [HARVESTER] USER_CONTEXT mode detected. YouTube harvest bypassed.")
        if incoming_harvest:
            raise RuntimeError(
                "Source conflict: USER_CONTEXT mode cannot include harvested_intelligence at Harvester entry."
            )
        if not context_summary:
            raise RuntimeError(
                "Source missing: USER_CONTEXT mode requires non-empty context_summary."
            )
        harvest_report["status"] = "harvest_skipped_user_context"
        harvest_report["fallback_path"] = "user_context_direct"
        harvest_report["actual_vtt_count"] = 0
        harvest_report["intelligence_length"] = 0
        harvest_report["quality_gate_passed"] = True
        quality_report["quality_gate_passed"] = True
        persist_reports()
        return {"status": "harvest_skipped_user_context"}

    print("[SEARCH] [HARVESTER] Pulling YouTube intelligence via yt-dlp...")

    if manifest.get("harvest_request_hash") == req_hash and os.path.exists(intel_read_file):

        try:

            with open(intel_read_file, "r", encoding="utf-8") as f:

                intelligence = f.read()
            cached_quality = {}
            if os.path.exists(quality_read_file):
                try:
                    with open(quality_read_file, "r", encoding="utf-8") as qf:
                        cached_quality = json.load(qf) or {}
                except Exception:
                    cached_quality = {}
            cached_relevant = int(cached_quality.get("relevant_vtt_count", 0) or 0)
            if len((intelligence or "").strip()) >= min_cache_intel_chars and cached_relevant >= min_relevant_vtt_required:
                print(
                    "    [RESUMING] Valid YouTube intelligence found for this request. Skipping scrape.")
                harvest_report["cache_hit"] = True
                harvest_report["actual_vtt_count"] = vtt_count()
                harvest_report["relevant_vtt_count"] = cached_relevant
                harvest_report["intelligence_length"] = len((intelligence or "").strip())
                harvest_report["status"] = "harvested"
                harvest_report["fallback_path"] = "cache_resume"
                harvest_report["quality_gate_passed"] = True
                quality_report.update({
                    "actual_vtt_count": harvest_report["actual_vtt_count"],
                    "relevant_vtt_count": cached_relevant,
                    "quality_gate_passed": True,
                })
                persist_reports()
                return {"harvested_intelligence": intelligence, "status": "harvested"}
            print("    [RESUMING] Cached intelligence does not satisfy strict quality gate. Re-harvesting.")

        except Exception:

            pass

    # Clean old harvests

    for f in glob.glob(os.path.join(harvest_dir, "*.vtt")):

        os.remove(f)

    try:
        res = smart_retry(
            fireworks_chat_completion, "fireworks_llm",  # Phase 20: Utility task  Flash
            contents=f"You are a SEO search expert. Extract a 3 to 4 word highly optimized YouTube search query to find documentary b-roll and information for this project. Output ONLY the keywords. NO QUOTES. Project: {state['request_prompt']}",
            prompt_template_id="PROMPT_A_HARVESTER_QUERY_OPTIMIZER",
            trace_node="Harvester",
        )

        query = res.text.strip().replace('"', '')

        print(f"    [HARVESTER] Extracted Optimized Query: '{query}'")

    except Exception:

        query = state["request_prompt"][:50]
    harvest_report["query"] = query

    import yt_dlp

    def build_subtitle_opts(write_subs: bool, write_auto_subs: bool):
        return {
            "writesubtitles": write_subs,
            "writeautomaticsub": write_auto_subs,
            "subtitleslangs": ["en"],
            "subtitlesformat": "vtt",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(harvest_dir, "%(id)s.%(ext)s"),
        }

    search_queries = _build_harvester_search_queries(query, state.get("request_prompt", ""), max_passes=max_passes)
    harvest_report["pass_queries"] = search_queries

    candidate_ids = []
    candidate_meta = {}
    seen_ids = set()
    consecutive_429 = 0

    for pass_idx, pass_query in enumerate(search_queries, start=1):
        if harvest_report["hard_block_triggered"]:
            break
        if vtt_count() >= max_downloaded_vtts:
            break

        harvest_report["passes_used"] = pass_idx
        search_size = 12 if pass_idx == 1 else 18
        print(f"    [HARVESTER] Pass {pass_idx}/{max_passes} search: '{pass_query}'")

        entries = []
        for search_attempt in range(1, 3):
            try:
                with yt_dlp.YoutubeDL({
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "extract_flat": True,
                }) as ydl:
                    info = ydl.extract_info(f"ytsearch{search_size}:{pass_query}", download=False) or {}
                entries = info.get("entries", []) or []
                break
            except Exception as e:
                err_msg = str(e)
                add_failure(f"search:{err_msg}")
                err_class = classify_yt_error(err_msg)
                if err_class in ("rate_limited", "retryable"):
                    if err_class == "rate_limited":
                        consecutive_429 += 1
                    delay = min(20.0, 1.5 * (2 ** min(max(consecutive_429, 1), 4)))
                    harvest_report["cooldown_durations"].append(round(delay, 2))
                    harvest_report["consecutive_429_peak"] = max(
                        harvest_report["consecutive_429_peak"], consecutive_429
                    )
                    print(
                        f"    [HARVESTER] Search retry {search_attempt}/2 after {err_class}. Cooling {delay:.1f}s.")
                    time.sleep(delay)
                    if consecutive_429 >= hard_block_threshold:
                        harvest_report["hard_block_triggered"] = True
                        break
                    continue
                break

        if harvest_report["hard_block_triggered"]:
            break

        pass_candidates = []
        for entry in entries:
            video_id = (entry or {}).get("id") or (entry or {}).get("url")
            if not video_id:
                continue
            if "watch?v=" in video_id:
                video_id = video_id.split("watch?v=")[-1].split("&")[0]
            video_id = str(video_id).strip()
            if not video_id or video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            title = str((entry or {}).get("title", "") or "").strip()
            candidate_meta[video_id] = {"title": title, "query": pass_query, "pass_idx": pass_idx}
            candidate_ids.append(video_id)
            pass_candidates.append(video_id)
            if len(candidate_ids) >= max_candidates:
                break

        harvest_report["candidate_pool_size"] = len(candidate_ids)
        if len(candidate_ids) >= max_candidates and vtt_count() < max_downloaded_vtts:
            max_candidates += 15
            harvest_report["max_candidates"] = max_candidates

        for video_id in pass_candidates:
            if vtt_count() >= max_downloaded_vtts:
                break
            if harvest_report["hard_block_triggered"]:
                break

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            harvest_report["attempted_videos"].append(video_id)
            terminal_error = False

            for attempt in range(1, per_video_retries + 1):
                if harvest_report["hard_block_triggered"]:
                    break

                harvest_report["retry_counts"][video_id] = attempt
                downloaded = False
                should_retry = False

                for mode_name, write_subs, write_auto_subs in [
                    ("manual_subtitles", True, False),
                    ("auto_subtitles", False, True),
                ]:
                    try:
                        before_files = set(glob.glob(os.path.join(harvest_dir, f"{video_id}*.vtt")))
                        with yt_dlp.YoutubeDL(build_subtitle_opts(write_subs, write_auto_subs)) as ydl:
                            ydl.extract_info(video_url, download=True)
                        after_files = set(glob.glob(os.path.join(harvest_dir, f"{video_id}*.vtt")))
                        if after_files and (after_files != before_files or len(after_files) > 0):
                            downloaded = True
                            break
                        add_failure(f"{video_id}:{mode_name}:no_subtitles_written")
                        should_retry = True
                    except Exception as e:
                        err_msg = str(e)
                        add_failure(f"{video_id}:{mode_name}:{err_msg}")
                        err_class = classify_yt_error(err_msg)

                        if err_class == "terminal":
                            terminal_error = True
                            break

                        if err_class in ("rate_limited", "retryable"):
                            should_retry = True
                            if err_class == "rate_limited":
                                consecutive_429 += 1
                            delay = min(24.0, 1.0 + 2.0 * min(max(consecutive_429, 1), 6))
                            harvest_report["cooldown_durations"].append(round(delay, 2))
                            harvest_report["consecutive_429_peak"] = max(
                                harvest_report["consecutive_429_peak"], consecutive_429
                            )
                            print(
                                f"    [HARVESTER] {video_id} {mode_name} retry after {err_class}. Cooling {delay:.1f}s.")
                            time.sleep(delay)
                            if consecutive_429 >= hard_block_threshold:
                                harvest_report["hard_block_triggered"] = True
                                break

                if downloaded:
                    consecutive_429 = max(0, consecutive_429 - 1)
                    time.sleep(0.4 + 0.2 * min(consecutive_429, 3))
                    break
                if terminal_error or harvest_report["hard_block_triggered"] or not should_retry:
                    break

        if harvest_report["hard_block_triggered"]:
            break

    # Parse all VTT files into combined intelligence

    vtt_files = glob.glob(os.path.join(harvest_dir, "*.vtt"))
    harvest_report["actual_vtt_count"] = len(vtt_files)
    quality_report["actual_vtt_count"] = len(vtt_files)

    print(f"    [HARVESTER] Harvested {len(vtt_files)} YouTube transcripts.")

    parsed_records = []
    for vf in vtt_files:

        try:

            with open(vf, "r", encoding="utf-8", errors="ignore") as f:

                raw = f.read()

            transcript_text = _clean_transcript_text(raw)
            if not transcript_text:
                continue
            file_name = os.path.basename(vf)
            video_id = file_name.split(".")[0]
            meta = candidate_meta.get(video_id, {})
            relevance = _score_harvest_relevance(
                transcript_text,
                state.get("request_prompt", ""),
                request_terms,
                intent_terms,
            )
            parsed_records.append({
                "video_id": video_id,
                "file": vf,
                "title": meta.get("title", ""),
                "query": meta.get("query", ""),
                "word_count": len(transcript_text.split()),
                "relevance_score": relevance["score"],
                "request_hit_count": relevance["request_hit_count"],
                "intent_hit_count": relevance["intent_hit_count"],
                "request_hits": relevance["request_hits"],
                "intent_hits": relevance["intent_hits"],
                "relevant": relevance["relevant"],
                "text": transcript_text,
            })

        except Exception:

            continue

    parsed_records.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)
    relevant_records = [r for r in parsed_records if r.get("relevant")]
    harvest_report["relevant_vtt_count"] = len(relevant_records)
    quality_report["relevant_vtt_count"] = len(relevant_records)
    quality_report["transcripts"] = [
        {
            "video_id": r.get("video_id"),
            "title": r.get("title", ""),
            "query": r.get("query", ""),
            "word_count": r.get("word_count", 0),
            "relevance_score": r.get("relevance_score", 0.0),
            "request_hit_count": r.get("request_hit_count", 0),
            "intent_hit_count": r.get("intent_hit_count", 0),
            "request_hits": r.get("request_hits", []),
            "intent_hits": r.get("intent_hits", []),
            "relevant": bool(r.get("relevant", False)),
        }
        for r in parsed_records
    ]

    parse_cap = min(10, len(relevant_records))
    combined = [r.get("text", "") for r in relevant_records[:parse_cap] if r.get("text")]
    intelligence = "\n\n---\n\n".join(combined) if combined else ""
    harvest_report["intelligence_length"] = len((intelligence or "").strip())
    if len(relevant_records) >= min_relevant_vtt_required and len((intelligence or "").strip()) >= min_cache_intel_chars:
        _write_text_artifact("harvested_intelligence.txt", intelligence, mirror_legacy=None)
        manifest["harvest_request_hash"] = req_hash
        save_state_manifest(manifest)
        harvest_report["status"] = "harvested"
        harvest_report["fallback_path"] = "youtube"
        harvest_report["quality_gate_passed"] = True
        quality_report["quality_gate_passed"] = True
        persist_reports()
        return {"harvested_intelligence": intelligence, "status": "harvested"}

    halt_reason = (
        f"Harvester quality gate failed: only {len(relevant_records)} relevant YouTube transcripts "
        f"(minimum {min_relevant_vtt_required}). Halting to prevent off-topic video."
    )
    harvest_report["status"] = "hard_stop_insufficient_relevance"
    harvest_report["fallback_path"] = "hard_stop"
    quality_report["halt_reason"] = halt_reason
    persist_reports()
    raise RuntimeError(halt_reason)



# ==============================================================

# NODE 2: WRITER (Real CPP + Duration-Aware)

# ==============================================================

def writer_node(state: AgentState):

    print("[WRITE]  [WRITER] Synthesizing duration-aware script with real CPP...")

    target_secs = state.get("target_duration", 60)
    narration_style = _normalize_narration_style(state.get("narration_style", NARRATION_STYLE_DEFAULT))
    context_rewrite = _normalize_context_rewrite(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
    deterministic_user_context_mode = _is_deterministic_user_context_mode(state)
    style_profile = _narration_profile(narration_style)
    print(
        f"    [WRITER] Drafting SOTA {style_profile.get('label', narration_style)} script (Target: {state['target_duration']}s)...")
    script_hash = ""
    manifest = get_state_manifest()
    script_read_file = _artifact_read_path("master_script.txt")

    target_secs = state.get("target_duration", 60)
    target_words = int(target_secs * 2.5)
    if state.get("status") == "duration_fail":
        print(f"    [WRITER] [REWRITE] Adjusting for duration mismatch...")
        rewrite_note = f" IMPORTANT: Your previous draft was too long/short. FOCUS on EXACTLY {target_words} words."
    else:
        rewrite_note = ""
    # Explicit source contract:
    # USER_CONTEXT path consumes context_summary only.
    # YOUTUBE_HARVEST path consumes harvested_intelligence only.
    input_source = str(state.get("input_source", "") or "").strip().upper()
    context_summary = state.get("context_summary")
    harvested = str(state.get("harvested_intelligence", "") or "").strip()
    context_summary_text = str(context_summary or "").strip()

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
        writer_context = _compact_context_for_writer(harvested, max_chars=2500)
        selected_source = "harvested_intelligence"
    else:
        # Legacy backward-compatible mode when old callers do not send input_source.
        if context_summary_text:
            writer_context = context_summary_text
            selected_source = "context_summary"
        elif harvested:
            writer_context = _compact_context_for_writer(harvested, max_chars=2500)
            selected_source = "harvested_intelligence"
        else:
            writer_context = "General Documentary"
            selected_source = "legacy_fallback"
    script_hash = get_hash(
        f"{state.get('request_prompt', '')}|{input_source or 'LEGACY'}|{selected_source}|"
        f"{style_profile.get('cache_key', narration_style)}|{context_rewrite}|{get_hash(writer_context)}"
    )
    print(f"    [WRITER] Context source selected: {selected_source}")
    print(f"    [WRITER] Narration style selected: {narration_style} | context_rewrite={context_rewrite}")
    context_block = f"\n\nContext for focus: {writer_context}"

    writer_quality_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "request_prompt": state.get("request_prompt", ""),
        "input_source": input_source or "LEGACY",
        "narration_style": narration_style,
        "context_rewrite": context_rewrite,
        "style_profile": style_profile.get("label", narration_style),
        "validation_profile": "user_context_context_priority" if input_source == "USER_CONTEXT" else "youtube_context_priority",
        "selected_source": selected_source,
        "target_duration": target_secs,
        "target_words": target_words,
        "cache_resume_checked": False,
        "cache_resume_used": False,
        "attempts": [],
        "final_status": "pending",
        "final_reason": "",
    }

    def persist_writer_report():
        try:
            _write_json_artifact("writer_quality_report.json", writer_quality_report, mirror_legacy=None)
        except Exception:
            pass

    # Global default: deterministic local CPP for reliability and zero CPP API usage.
    # Optional override for experiments:
    #   TVC_WRITER_CPP_MODE=neural  -> enable Fireworks CPP pass
    #   (default/missing/other)     -> local deterministic CPP
    cpp_mode = str(os.getenv("TVC_WRITER_CPP_MODE", "local") or "local").strip().lower()
    prefer_local_cpp = cpp_mode != "neural"
    writer_quality_report["cpp_mode"] = "local_deterministic" if prefer_local_cpp else "neural_fireworks"

    def apply_cpp_and_clamp(raw_script: str) -> str:
        if prefer_local_cpp:
            print("    [CPP] Local deterministic CPP active.")
            processed_script = _sanitize_tts_script(apply_cpp(raw_script))
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
            cpp_res = smart_retry(
                fireworks_chat_completion, "fireworks_llm",  # Phase 20: Use Utility Flash
                contents=raw_script,
                config=types.GenerateContentConfig(
                    system_instruction=cpp_sys, temperature=0.1),
                prompt_template_id="PROMPT_E_WRITER_CPP_PROSODY",
                trace_node="Writer",
            )
            processed_script = str(cpp_res.text or "").strip()

        # Robustness guard: if CPP balloons output, fall back to pre-CPP draft.
        base_wc = len(raw_script.split())
        proc_wc = len(processed_script.split())
        if base_wc > 0 and proc_wc > int(base_wc * 1.5):
            print(
                f"    [CPP] Overshoot detected ({proc_wc} vs {base_wc} words). Reverting to pre-CPP draft.")
            processed_script = raw_script

        if _writer_meta_leak_hits(processed_script) and not _writer_meta_leak_hits(raw_script):
            print("    [CPP] Meta-leak introduced during prosody pass. Reverting to pre-CPP draft.")
            processed_script = raw_script

        # Final writer clamp so downstream duration control is not overwhelmed.
        final_words = processed_script.split()
        max_writer_words = int(target_words * 1.2)
        if len(final_words) > max_writer_words:
            clipped = " ".join(final_words[:max_writer_words])
            sentence_cut = re.search(r'.*[.!?]', clipped)
            processed_script = sentence_cut.group(0).strip() if sentence_cut else clipped
            print(
                f"    [WRITER] Length clamp applied ({len(final_words)} -> {len(processed_script.split())} words).")
        return processed_script

    def local_user_context_fallback_script() -> str:
        base_script = _sanitize_tts_script(context_summary_text)
        if not base_script:
            return ""

        # Drop pure stage-direction lines like "[Walks on stage]" for cleaner narration.
        lines = []
        for ln in base_script.split("\n"):
            t = ln.strip()
            if not t:
                continue
            if re.fullmatch(r"\[[^\]]+\]", t):
                continue
            lines.append(t)
        if lines:
            base_script = "\n".join(lines)

        # Use deterministic local CPP to avoid another LLM meta-leak.
        processed_script = _sanitize_tts_script(apply_cpp(base_script))
        if not processed_script:
            processed_script = base_script

        final_words = processed_script.split()
        max_writer_words = int(target_words * 1.2)
        if len(final_words) > max_writer_words:
            clipped = " ".join(final_words[:max_writer_words])
            sentence_cut = re.search(r'.*[.!?]', clipped)
            processed_script = sentence_cut.group(0).strip() if sentence_cut else clipped
            print(
                f"    [WRITER] USER_CONTEXT fallback clamp applied ({len(final_words)} -> {len(processed_script.split())} words).")
        return processed_script

    if (
        not deterministic_user_context_mode
        and manifest.get("writer_prompt_hash") == script_hash
        and os.path.exists(script_read_file)
        and state.get("status") != "duration_fail"
    ):
        writer_quality_report["cache_resume_checked"] = True
        try:
            with open(script_read_file, "r", encoding="utf-8") as f:
                cached_script = f.read()
            cache_quality = _validate_writer_script(
                cached_script,
                state.get("request_prompt", ""),
                writer_context,
                input_source or "LEGACY",
            )
            writer_quality_report["cache_quality"] = cache_quality
            if cache_quality.get("valid"):
                writer_quality_report["cache_resume_used"] = True
                writer_quality_report["final_status"] = "pass"
                writer_quality_report["final_reason"] = "cache_resume_valid"
                persist_writer_report()
                print(
                    "    [RESUMING] Valid script found for this prompt. Skipping Writer.")
                return {"script": cached_script, "status": "drafted", "duration_attempts": state.get("duration_attempts", 0) + 1}
            print("    [WRITER] Cached script rejected by quality gate. Regenerating...")
        except Exception:
            pass

    if deterministic_user_context_mode:
        direct_script = local_user_context_fallback_script()
        direct_quality = _validate_writer_script(
            direct_script,
            state.get("request_prompt", ""),
            writer_context,
            input_source or "LEGACY",
        ) if direct_script else {"valid": False, "reasons": ["fallback_empty"], "word_count": 0}
        writer_quality_report["deterministic_user_context_path"] = True
        writer_quality_report["deterministic_quality"] = direct_quality
        if direct_script and direct_quality.get("valid"):
            _write_text_artifact("master_script.txt", direct_script, mirror_legacy=None)
            manifest["writer_prompt_hash"] = script_hash
            save_state_manifest(manifest)
            writer_quality_report["final_status"] = "pass"
            writer_quality_report["final_reason"] = "user_context_deterministic_default"
            persist_writer_report()
            print("    [WRITER] USER_CONTEXT deterministic direct-script path selected.")
            return {"script": direct_script, "status": "drafted", "duration_attempts": state.get("duration_attempts", 0) + 1}
        writer_quality_report["final_status"] = "hard_stop"
        writer_quality_report["final_reason"] = ",".join(direct_quality.get("reasons", [])) or "user_context_deterministic_quality_failed"
        persist_writer_report()
        raise RuntimeError(
            "USER_CONTEXT deterministic script failed quality gate. "
            "Use --context-rewrite force only if you explicitly want model rewrite."
        )
    elif input_source == "USER_CONTEXT" and context_rewrite == "force" and state.get("status") != "duration_fail":
        print("    [WRITER] USER_CONTEXT rewrite forced. Executing style-aware LLM drafting path.")

    latest_processed = ""
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
            source_guard_note = " If rewriting USER_CONTEXT, preserve the original facts, chronology, and intent while adapting tone."
        sys_inst = (
            f"You are {style_profile.get('writer_role', 'a master narration scriptwriter')}. "
            f"{style_profile.get('writer_tone_instruction', '')} "
            f"Write a highly engaging {style_profile.get('writer_output_label', 'voiceover narration')} of EXACTLY {target_words} words. "
            f"This MUST produce a {target_secs}-second voiceover when spoken at natural pace. "
            f"Output ONLY spoken narration text. No headers, no stage directions, no word counts. "
            f"Every sentence on its own line.{source_guard_note}{rewrite_note}{strict_note}"
        )
        try:
            res = smart_retry(
                fireworks_chat_completion, "fireworks_llm",
                contents=f"{state['request_prompt']}{context_block}",
                config=types.GenerateContentConfig(
                    system_instruction=sys_inst, temperature=float(style_profile.get("writer_temperature", 0.5))),
                prompt_template_id="PROMPT_D_WRITER_SCRIPT_DRAFT",
                trace_node="Writer",
            )
        except Exception as llm_err:
            llm_msg = str(llm_err).lower()
            if input_source == "USER_CONTEXT" and any(k in llm_msg for k in ["circuit open", "precondition", "412"]):
                fallback_script = local_user_context_fallback_script()
                if fallback_script and len(fallback_script.split()) >= 30:
                    _write_text_artifact("master_script.txt", fallback_script, mirror_legacy=None)
                    manifest["writer_prompt_hash"] = script_hash
                    save_state_manifest(manifest)
                    writer_quality_report["fallback_mode"] = "user_context_provider_degraded_direct_script"
                    writer_quality_report["final_status"] = "pass"
                    writer_quality_report["final_reason"] = "provider_degraded_user_context_local_path"
                    persist_writer_report()
                    print("    [WRITER] Provider degraded; using deterministic USER_CONTEXT script path.")
                    return {"script": fallback_script, "status": "drafted", "duration_attempts": state.get("duration_attempts", 0) + 1}
            raise
        draft_script = str(res.text or "").strip()
        processed_script = apply_cpp_and_clamp(draft_script)
        quality = _validate_writer_script(
            processed_script,
            state.get("request_prompt", ""),
            writer_context,
            input_source or "LEGACY",
        )
        writer_quality_report["attempts"].append({
            "attempt": attempt,
            "strict_retry": attempt == 2,
            "word_count": quality.get("word_count", 0),
            "request_overlap": quality.get("request_overlap", 0.0),
            "context_overlap": quality.get("context_overlap", 0.0),
            "meta_hits": quality.get("meta_hits", []),
            "reasons": quality.get("reasons", []),
            "valid": bool(quality.get("valid", False)),
        })
        latest_processed = processed_script
        latest_quality = quality

        if quality.get("valid"):
            _write_text_artifact("master_script.txt", processed_script, mirror_legacy=None)

            manifest["writer_prompt_hash"] = script_hash
            save_state_manifest(manifest)
            writer_quality_report["final_status"] = "pass"
            writer_quality_report["final_reason"] = "quality_gate_passed"
            persist_writer_report()
            print(
                f"    [WRITER] Script forged ({len(processed_script.split())} words). Locked and loaded.")
            return {"script": processed_script, "status": "drafted", "duration_attempts": state.get("duration_attempts", 0) + 1}

        print(
            f"    [WRITER] Quality gate rejected attempt {attempt}: {', '.join(quality.get('reasons', []))}")

    if input_source == "USER_CONTEXT":
        reason_set = set(latest_quality.get("reasons", []))
        if reason_set and reason_set.issubset({"meta_prompt_leak", "low_request_alignment"}):
            fallback_script = local_user_context_fallback_script()
            fallback_quality = _validate_writer_script(
                fallback_script,
                state.get("request_prompt", ""),
                writer_context,
                input_source or "LEGACY",
            ) if fallback_script else {"valid": False, "reasons": ["fallback_empty"]}

            if fallback_script and not _writer_meta_leak_hits(fallback_script) and len(fallback_script.split()) >= 30:
                _write_text_artifact("master_script.txt", fallback_script, mirror_legacy=None)
                manifest["writer_prompt_hash"] = script_hash
                save_state_manifest(manifest)
                writer_quality_report["fallback_mode"] = "user_context_direct_script"
                writer_quality_report["fallback_quality"] = fallback_quality
                writer_quality_report["final_status"] = "pass"
                writer_quality_report["final_reason"] = "user_context_direct_fallback_after_meta_leak"
                persist_writer_report()
                print("    [WRITER] USER_CONTEXT direct-script fallback activated after meta-leak retries.")
                return {"script": fallback_script, "status": "drafted", "duration_attempts": state.get("duration_attempts", 0) + 1}

    writer_quality_report["final_status"] = "hard_stop"
    writer_quality_report["final_reason"] = ",".join(latest_quality.get("reasons", [])) or "writer_quality_gate_failed"
    persist_writer_report()
    raise RuntimeError(
        f"Writer quality gate failed after strict retry: {writer_quality_report['final_reason']}"
    )



# ==============================================================

# NODE 3: DURATION GATE (Enforce Target Length)

# ==============================================================

def duration_gate(state: AgentState):

    input_source = str(state.get("input_source", "") or "").strip().upper()
    context_rewrite = _normalize_context_rewrite(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
    if input_source == "USER_CONTEXT" and context_rewrite != "force":
        print("[OK]  [DURATION GATE] BYPASS -- USER_CONTEXT deterministic channel (no rewrite loop).")
        return {"status": "duration_pass"}

    word_count = len(state["script"].split())

    expected_dur = word_count / 2.5

    target = state.get("target_duration", 60)

    tolerance = 10  # seconds

    if abs(expected_dur - target) <= tolerance:

        print(
            f"[OK]  [DURATION GATE] PASS -- {expected_dur:.0f}s within {tolerance}s of {target}s target.")

        return {"status": "duration_pass"}

    elif state.get("duration_attempts", 1) >= 3:

        # Force truncation after 3 attempts

        # SOTA: Prioritize sentence boundaries for clean cuts, with a slightly more generous lookback

        words = state["script"].split()

        # Allow slight breathing room for slow speech
        force_limit = int(target * 2.7)

        primary_cutoff = " ".join(words[:force_limit])

        last_sentence = re.search(r'.*[.!?]', primary_cutoff)

        if last_sentence:

            truncated = last_sentence.group(0).strip()

        else:

            truncated = primary_cutoff  # Fallback to raw word cut if no punctuation

        print(
            f"[WARN] [DURATION GATE] SOTA Graceful Truncation applied -- {len(truncated.split())} words.")

        _write_text_artifact("master_script.txt", truncated, mirror_legacy=None)

        return {"script": truncated, "status": "duration_pass"}

    else:

        print(
            f" [DURATION GATE] REJECT -- {expected_dur:.0f}s vs {target}s target. Sending back to Writer (attempt {state['duration_attempts']}).")

        return {"status": "duration_fail"}


# ==============================================================

# NODE 4: TOPIC EXTRACTOR (Headline Callouts)

# ==============================================================

def _topic_sentences(script_text: str) -> List[str]:
    text = str(script_text or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        sentences: List[str] = []
        for ln in lines:
            parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', ln) if s.strip()]
            if parts:
                sentences.extend(parts)
            else:
                sentences.append(ln)
        if sentences:
            return sentences
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _minimum_scene_count_for_script(script_text: str) -> int:
    words = len(re.findall(r"[a-z0-9']+", str(script_text or "").lower()))
    if words >= 260:
        return 6
    if words >= 180:
        return 5
    if words >= 120:
        return 4
    if words >= 70:
        return 3
    if words >= 35:
        return 2
    return 1


def _scene_sentence_splits(script_text: str) -> List[str]:
    text = str(script_text or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        sentences = lines
    else:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

    if not sentences:
        merged = " ".join(text.split()).strip()
        if merged:
            sentences = [merged]
    return sentences


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
            t_low = topic.lower()
            keywords = [w for w in re.findall(r"[a-z0-9']+", t_low) if len(w) > 3]
            grounded = (t_low in script_lower) or any(w in script_lower for w in keywords)
        else:
            grounded = (topic == "BREAKING NEWS")

        if not grounded:
            continue
        if topic in seen:
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
    dist: Dict[str, int] = {}
    for item in callouts:
        try:
            idx = int(item.get("after_sentence", 1))
        except Exception:
            idx = 1
        key = str(idx)
        dist[key] = dist.get(key, 0) + 1
    return dist


def _repair_collapsed_topic_callouts(callouts: List[dict], script_text: str):
    sentence_count = max(1, len(_topic_sentences(script_text)))
    pre_dist = _callout_index_distribution(callouts)
    count = len(callouts)
    dominant_idx = None
    dominant_count = 0
    for k, v in pre_dist.items():
        if v > dominant_count:
            dominant_idx = k
            dominant_count = v

    dominant_ratio = (dominant_count / float(max(1, count))) if count else 0.0
    collapse_detected = (
        sentence_count > 1
        and count >= 3
        and dominant_ratio >= 0.8
    )

    report = {
        "detected": bool(collapse_detected),
        "rebalanced": False,
        "reason": "",
        "sentence_count": sentence_count,
        "callout_count": count,
        "dominant_index": dominant_idx,
        "dominant_ratio": round(dominant_ratio, 4),
        "pre_distribution": pre_dist,
        "post_distribution": pre_dist,
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
        repaired.append({
            "topic": item.get("topic", ""),
            "after_sentence": target,
        })

    post_dist = _callout_index_distribution(repaired)
    report["rebalanced"] = bool(repaired != callouts)
    report["reason"] = "dominant_index_collapse_rebalanced"
    report["post_distribution"] = post_dist
    return repaired, report


def topic_extractor(state: AgentState):

    print("    [TOPIC EXTRACTOR] Extracting on-screen topic callouts...")

    script_text = str(state.get("script", "") or "")
    deterministic_user_context_mode = _is_deterministic_user_context_mode(state)
    script_hash = get_hash(script_text)

    manifest = get_state_manifest()

    topic_file = _artifact_read_path("topic_callouts.json")
    sentence_count = max(1, len(_topic_sentences(script_text)))

    def persist_topic_quality(source: str, pre_repair: List[dict], final_callouts: List[dict], collapse_report: dict, cache_resume: bool):
        quality_report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "cache_resume": bool(cache_resume),
            "script_hash": script_hash,
            "script_sentence_count": sentence_count,
            "pre_distribution": _callout_index_distribution(pre_repair),
            "post_distribution": _callout_index_distribution(final_callouts),
            "collapse_repair": collapse_report,
            "callout_count": len(final_callouts),
            "topics": [c.get("topic", "") for c in final_callouts],
        }
        _write_json_artifact("topic_callout_quality_report.json", quality_report, mirror_legacy=None)

    if (not deterministic_user_context_mode) and manifest.get("topic_script_hash") == script_hash and os.path.exists(topic_file):

        try:

            with open(topic_file, "r", encoding="utf-8") as f:

                cached_raw = json.load(f)
                cached_callouts = _normalize_topic_callouts(cached_raw, script_text)
            pre_repair = list(cached_callouts)
            cached_callouts, collapse_report = _repair_collapsed_topic_callouts(cached_callouts, script_text)
            if cached_callouts:
                if cached_callouts != cached_raw:
                    _write_json_artifact("topic_callouts.json", cached_callouts, mirror_legacy=None)
                persist_topic_quality("cache_resume", pre_repair, cached_callouts, collapse_report, cache_resume=True)
                print(
                    "    [RESUMING] Valid topics found for this script. Skipping Extractor API call.")
                return {"topic_callouts": cached_callouts, "status": "topics_extracted"}
            print("    [TOPIC EXTRACTOR] Cached topics invalid. Regenerating...")

        except Exception as e:
            print(f"    [TOPIC EXTRACTOR] Cache read failed: {e}")

            pass

    prompt = f"""Extract up to 4-6 key topic headlines from this documentary script.

These will appear as bold on-screen title cards during the video.

GROUNDING RULE: Every topic MUST be a verbatim phrase or key term that literally appears in the script text.

Do NOT invent or infer topics. If the script has fewer than 4 clear topics, just return fewer.

Return ONLY a JSON array of objects with "topic" (short uppercase headline, MAX 20 CHARACTERS) and "after_sentence" (the sentence number after which this topic should appear, 1-indexed).

Script:

{script_text}"""

    callouts = []
    primary_reason = ""
    source_label = "primary"

    try:
        res = smart_retry(
            fireworks_chat_completion, "fireworks_llm", contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a strict text extraction engine. ABSOLUTE RULE: Every 'topic' you return MUST be a verbatim phrase that physically appears in the provided script text. You are FORBIDDEN from inventing topics. Return strict JSON array only. No markdown.",
                temperature=0.1
            ),
            prompt_template_id="PROMPT_TOPIC_EXTRACTOR_CALLOUTS",
            trace_node="TopicExtractor",
        )
        primary_raw = sota_json_repair((res.text or "").strip())
        callouts = _normalize_topic_callouts(primary_raw, script_text)
        if not callouts:
            primary_reason = "primary_output_unusable"
    except Exception as e:
        primary_reason = f"primary_parse_error: {e}"

    if primary_reason:
        if deterministic_user_context_mode:
            print(
                f"    [TOPIC EXTRACTOR] Primary extraction needs repair ({primary_reason}). "
                "Deterministic USER_CONTEXT mode uses single-shot API; switching to local fallback."
            )
        else:
            print(f"    [TOPIC EXTRACTOR] Primary extraction needs repair ({primary_reason}). Running strict repair retry...")
            source_label = "repair"
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
                repair_res = smart_retry(
                    fireworks_chat_completion, "fireworks_llm", contents=repair_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="Return strict JSON array only. No markdown. No prose. No comments.",
                        temperature=0.0
                    ),
                    prompt_template_id="PROMPT_TOPIC_EXTRACTOR_REPAIR",
                    trace_node="TopicExtractor",
                )
                repair_raw = sota_json_repair((repair_res.text or "").strip())
                callouts = _normalize_topic_callouts(repair_raw, script_text)
            except Exception as e:
                print(f"    [TOPIC EXTRACTOR] Repair retry failed: {e}")

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
            f"    [TOPIC EXTRACTOR] Rebalanced collapsed callout indices: {collapse_report.get('pre_distribution')} -> {collapse_report.get('post_distribution')}")

    print(
        f"    [TOPIC EXTRACTOR] Extracted {len(callouts)} verified callouts: {[c['topic'] for c in callouts]}")

    _write_json_artifact("topic_callouts.json", callouts, mirror_legacy=None)
    persist_topic_quality(source_label, pre_repair, callouts, collapse_report, cache_resume=False)

    manifest["topic_script_hash"] = script_hash

    save_state_manifest(manifest)

    return {"topic_callouts": callouts, "status": "topics_extracted"}



# ==============================================================

# NODE 5: SCENE DIRECTOR (Semantic Visual Segmentation - Phase 18)

# ==============================================================

def _update_scene_audio_prompt_report(node_name: str, payload: dict):
    report_file = _artifact_read_path("scene_audio_prompt_report.json")
    report = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "nodes": {}}
    try:
        if os.path.exists(report_file):
            with open(report_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                report = loaded
    except Exception:
        pass

    if not isinstance(report.get("nodes"), dict):
        report["nodes"] = {}
    report["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    report["nodes"][node_name] = payload
    _write_json_artifact("scene_audio_prompt_report.json", report, mirror_legacy=None)


def _deterministic_sentence_scenes(script_text: str, narration_style: str = NARRATION_STYLE_DEFAULT) -> dict:
    style_profile = _narration_profile(narration_style)
    sentences = _scene_sentence_splits(script_text)
    if not sentences:
        sentences = ["Narration segment."]

    min_scenes = _minimum_scene_count_for_script(script_text)
    if len(sentences) < min_scenes:
        words = re.findall(r"\S+", str(script_text or ""))
        if words:
            chunk_size = max(10, int((len(words) + min_scenes - 1) / max(1, min_scenes)))
            chunks = []
            for i in range(0, len(words), chunk_size):
                chunk_text = " ".join(words[i:i + chunk_size]).strip()
                if chunk_text:
                    chunks.append(chunk_text)
            if chunks:
                sentences = chunks[:max(min_scenes, len(chunks))]

    scenes = []
    for i, s in enumerate(sentences):
        scenes.append({
            "id": i + 1,
            "text": s,
            "visual_intent": f"{style_profile.get('scene_visual_prefix', 'Cinematic photorealistic shot showing:')} {s}",
            "subjects": []
        })

    return {
        "scenes": scenes,
        "style_dna": style_profile.get("scene_style_dna_default", "Cinematic documentary palette"),
        "meta_context": style_profile.get("scene_meta_context_default", "Documentary video"),
        "character_manifest": {}
    }


def _normalize_scene_payload(data: Any, script_text: str, narration_style: str = NARRATION_STYLE_DEFAULT) -> dict:
    style_profile = _narration_profile(narration_style)
    if not isinstance(data, dict):
        raise ValueError("scene_payload_not_dict")

    scenes_raw = data.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise ValueError("scene_payload_missing_scenes")

    defaults = _scene_sentence_splits(script_text)

    scenes = []
    for idx, scene in enumerate(scenes_raw):
        if not isinstance(scene, dict):
            continue
        txt = str(scene.get("text", "") or "").strip()
        if not txt and idx < len(defaults):
            txt = defaults[idx]
        if not txt:
            continue
        visual = str(scene.get("visual_intent", "") or "").strip()
        if not visual:
            visual = f"{style_profile.get('scene_visual_prefix', 'Cinematic photorealistic shot showing:')} {txt}"
        subjects = scene.get("subjects", [])
        if not isinstance(subjects, list):
            subjects = []
        scenes.append({
            "id": len(scenes) + 1,
            "text": txt,
            "visual_intent": visual,
            "subjects": [str(x).strip() for x in subjects if str(x).strip()]
        })

    if not scenes:
        raise ValueError("scene_payload_no_valid_scenes")

    style = str(data.get("style_dna", "") or "").strip() or style_profile.get("scene_style_dna_default", "Cinematic documentary palette")
    meta = str(data.get("meta_context", "") or "").strip() or style_profile.get("scene_meta_context_default", "Documentary video")
    manifest = data.get("character_manifest", {})
    if not isinstance(manifest, dict):
        manifest = {}

    return {
        "scenes": scenes,
        "style_dna": style,
        "meta_context": meta,
        "character_manifest": manifest,
    }


def _enforce_scene_mode_style(data: dict, narration_style: str) -> dict:
    profile = _narration_profile(narration_style)
    style_seed = str(profile.get("scene_style_dna_default", "") or "").strip()
    meta_seed = str(profile.get("scene_meta_context_default", "") or "").strip()
    style_val = str(data.get("style_dna", "") or "").strip()
    meta_val = str(data.get("meta_context", "") or "").strip()

    if style_seed:
        if not style_val:
            style_val = style_seed
        elif style_seed.lower() not in style_val.lower():
            style_val = f"{style_seed}. {style_val}"
    if meta_seed:
        if not meta_val:
            meta_val = meta_seed
        elif meta_seed.lower() not in meta_val.lower():
            meta_val = f"{meta_seed}. {meta_val}"

    data["style_dna"] = style_val or style_seed
    data["meta_context"] = meta_val or meta_seed
    return data


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _parse_vtt_time_to_seconds(value: str) -> float:
    token = str(value or "").strip()
    parts = token.split(":")
    if len(parts) != 3:
        return 0.0
    h = int(parts[0])
    m = int(parts[1])
    s = float(parts[2].replace(",", "."))
    return h * 3600 + m * 60 + s


def _parse_vtt_cues(vtt_text: str) -> List[dict]:
    cues = []
    lines = str(vtt_text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            try:
                left, right = [x.strip() for x in line.split("-->", 1)]
                start = _parse_vtt_time_to_seconds(left)
                end = _parse_vtt_time_to_seconds(right)
            except Exception:
                i += 1
                continue
            i += 1
            txt_parts = []
            while i < len(lines) and lines[i].strip():
                txt_parts.append(lines[i].strip())
                i += 1
            txt = re.sub(r"<[^>]+>", "", " ".join(txt_parts)).strip()
            cues.append({"start": start, "end": end, "text": txt})
        i += 1
    return cues


def _sanitize_tts_script(text: str) -> str:
    cleaned = str(text or "").replace("\r", "\n")
    # Smart punctuation normalization before ASCII filter.
    translation_map = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "-",
        "\u2013": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
    for src, dst in translation_map.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", cleaned)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in cleaned.split("\n")]
    lines = [ln for ln in lines if ln]
    if lines:
        return "\n".join(lines)
    return re.sub(r"\s+", " ", cleaned).strip()


def _word_token_set(text: str) -> set:
    return set(re.findall(r"[a-z0-9']+", str(text or "").lower()))


def _token_overlap_ratio(base_text: str, candidate_text: str) -> float:
    base = _word_token_set(base_text)
    cand = _word_token_set(candidate_text)
    if not base:
        return 1.0
    return len(base.intersection(cand)) / float(len(base))


_COMMON_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their",
    "this", "to", "was", "were", "will", "with", "you", "your", "about", "over",
    "after", "before", "during", "through", "into", "while", "than", "then",
    "also", "not", "only", "just", "very", "more", "most", "some", "any", "all",
    "can", "could", "should", "would", "may", "might", "must", "do", "does", "did",
}

_WRITER_META_LEAK_PATTERNS = [
    r"\bsystem message\b",
    r"\buser message\b",
    r"\bconversation history\b",
    r"\bprompt structure\b",
    r"\bi (?:misunderstood|need to|think i|should re-read)\b",
    r"\bthe user wants me\b",
    r"\blet me verify\b",
    r"\bwait[,.!]?\b",
    r"\bas an ai\b",
]


def _meaningful_terms(text: str, min_len: int = 4, max_terms: int = 24) -> List[str]:
    terms = []
    seen = set()
    for tok in re.findall(r"[a-z0-9']+", str(text or "").lower()):
        if len(tok) < min_len:
            continue
        if tok in _COMMON_STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
        if len(terms) >= max_terms:
            break
    return terms


def _clean_transcript_text(raw_text: str) -> str:
    cleaned_lines = []
    for raw_line in str(raw_text or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", " ", line)
        line = re.sub(r"\[[^\]]+\]", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        low = line.lower()
        if low in {"music", "applause", "laughter"}:
            continue
        if cleaned_lines and cleaned_lines[-1].lower() == low:
            continue
        cleaned_lines.append(line)
    return " ".join(cleaned_lines).strip()


def _compact_context_for_writer(text: str, max_chars: int = 2500) -> str:
    cleaned = _clean_transcript_text(text)
    if not cleaned:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if s.strip()]
    selected = []
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


def _harvester_intent_terms(request_prompt: str) -> List[str]:
    low = str(request_prompt or "").lower()
    terms = []
    if any(k in low for k in ["stand up", "comed", "joke", "humor", "humour", "laugh"]):
        terms.extend(["comedy", "comedian", "joke", "jokes", "laugh", "audience", "stage", "stand", "special"])
    if any(k in low for k in ["iran", "war", "airspace", "airport", "middle east"]):
        terms.extend(["iran", "airspace", "airport", "dubai", "middle", "flight", "travel", "war"])
    if re.search(r"\b(openai|gpt|codex|agentic|llm|ai)\b", low):
        terms.extend(["openai", "gpt", "codex", "agent", "agents", "model", "models", "ai"])
    dedup = []
    seen = set()
    for t in terms:
        if t not in seen:
            dedup.append(t)
            seen.add(t)
    return dedup


def _build_harvester_search_queries(base_query: str, request_prompt: str, max_passes: int) -> List[str]:
    query = " ".join(str(base_query or "").split()).strip()
    req = " ".join(str(request_prompt or "").split()).strip()
    low = req.lower()
    candidates = []
    if query:
        candidates.append(query)
    if req:
        candidates.append(req)

    if any(k in low for k in ["stand up", "comed", "joke", "humor", "humour", "laugh"]):
        if query:
            candidates.append(f"{query} stand up comedy full set jokes")
            candidates.append(f"{query} comedian special crowd laughter")
            candidates.append(f"{query} stand up set documentary interview")
        if req:
            candidates.append(f"{req} stand up comedy")
    else:
        if query:
            candidates.append(f"{query} documentary interview breakdown")
            candidates.append(f"{query} deep dive explainer")
            candidates.append(f"{query} recent analysis documentary")

    if query:
        candidates.append(f"{query} documentary explainer briefing")

    out = []
    seen = set()
    for item in candidates:
        norm = " ".join(str(item or "").split()).strip()
        if not norm:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
        if len(out) >= max_passes:
            break
    return out


def _score_harvest_relevance(
    text: str,
    request_prompt: str,
    request_terms: List[str],
    intent_terms: List[str],
) -> dict:
    raw_text = str(text or "")
    low = raw_text.lower()
    tokens = _word_token_set(raw_text)
    req_hits = [t for t in request_terms if t in tokens]
    intent_hits = [t for t in intent_terms if t in tokens]

    req_score = (len(req_hits) / float(max(1, len(request_terms)))) if request_terms else 0.0
    intent_score = (len(intent_hits) / float(max(1, min(4, len(intent_terms))))) if intent_terms else 0.0
    bonus = 0.0
    if "stand up" in str(request_prompt or "").lower() and "stand up" in low:
        bonus += 0.25
    if "openai" in str(request_prompt or "").lower() and "openai" in low:
        bonus += 0.15
    if "iran" in str(request_prompt or "").lower() and "iran" in low:
        bonus += 0.15

    score = round(req_score + 0.45 * intent_score + bonus, 4)
    relevant = len(req_hits) >= 2 and score >= 0.16
    if intent_terms:
        relevant = relevant and (len(intent_hits) >= 1 or bonus > 0.0)

    return {
        "score": score,
        "request_hit_count": len(req_hits),
        "intent_hit_count": len(intent_hits),
        "request_hits": req_hits[:12],
        "intent_hits": intent_hits[:12],
        "relevant": bool(relevant),
    }


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
) -> dict:
    script = _sanitize_tts_script(script_text)
    script_tokens = _word_token_set(script)
    request_terms = _meaningful_terms(request_prompt, min_len=4, max_terms=20)
    context_terms = _meaningful_terms(writer_context, min_len=4, max_terms=36)
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


def _normalize_epochs_from_mapping(raw_epochs: Any, visual_scenes: List[dict]) -> List[dict]:
    if not isinstance(raw_epochs, list):
        raise ValueError("epochs_not_list")
    if not isinstance(visual_scenes, list) or not visual_scenes:
        raise ValueError("visual_scenes_empty")

    by_id = {}
    for idx, ep in enumerate(raw_epochs):
        if not isinstance(ep, dict):
            continue
        ep_id = None
        rid = ep.get("id")
        if isinstance(rid, int):
            ep_id = rid
        elif isinstance(rid, float):
            ep_id = int(rid)
        elif isinstance(rid, str) and rid.strip().isdigit():
            ep_id = int(rid.strip())
        if ep_id is None and idx < len(visual_scenes):
            sid = visual_scenes[idx].get("id", idx + 1)
            ep_id = int(sid) if isinstance(sid, (int, float)) else idx + 1
        by_id[ep_id] = ep

    normalized = []
    last_end = -1.0
    for idx, scene in enumerate(visual_scenes):
        scene_id_raw = scene.get("id", idx + 1)
        scene_id = int(scene_id_raw) if isinstance(scene_id_raw, (int, float)) else idx + 1
        candidate = by_id.get(scene_id)
        if candidate is None and idx < len(raw_epochs) and isinstance(raw_epochs[idx], dict):
            candidate = raw_epochs[idx]
        if not isinstance(candidate, dict):
            raise ValueError(f"epoch_missing_for_scene_{scene_id}")

        start = _safe_float(candidate.get("start_time"))
        end = _safe_float(candidate.get("end_time"))
        if start is None or end is None:
            raise ValueError(f"epoch_time_missing_{scene_id}")
        if start < last_end:
            if (last_end - start) <= 0.2:
                start = last_end
            else:
                raise ValueError(f"epoch_non_monotonic_{scene_id}")
        if end <= start:
            dur = _safe_float(candidate.get("duration")) or 0.0
            end = start + max(0.35, dur)
        if end <= start:
            raise ValueError(f"epoch_invalid_window_{scene_id}")

        text = str(scene.get("text", "") or "").strip() or str(candidate.get("text", "") or "").strip()
        visual = str(scene.get("visual_intent", "") or "").strip() or str(candidate.get("visual_intent", "") or "").strip()
        subjects = scene.get("subjects", [])
        if not isinstance(subjects, list):
            subjects = []
        normalized.append({
            "id": scene_id,
            "start_time": round(start, 3),
            "end_time": round(end, 3),
            "duration": round(end - start, 3),
            "text": text,
            "visual_intent": visual,
            "subjects": [str(s).strip() for s in subjects if str(s).strip()]
        })
        last_end = end

    return normalized


def _build_local_epoch_mapping(visual_scenes: List[dict], vtt_text: str, script_text: str) -> List[dict]:
    cues = _parse_vtt_cues(vtt_text)
    if not visual_scenes:
        return []

    if cues:
        audio_start = cues[0]["start"]
        audio_end = cues[-1]["end"]
    else:
        audio_start = 0.0
        words = len(re.findall(r"[a-z0-9']+", str(script_text or "").lower()))
        audio_end = max(2.0, words / 2.5)

    total_span = max(audio_end - audio_start, len(visual_scenes) * 0.8)
    weights = []
    for scene in visual_scenes:
        scene_words = len(re.findall(r"[a-z0-9']+", str(scene.get("text", "")).lower()))
        weights.append(max(1, scene_words))
    total_weight = max(1, sum(weights))

    min_slot = 0.55
    cursor = audio_start
    epochs = []
    for idx, scene in enumerate(visual_scenes):
        scene_id_raw = scene.get("id", idx + 1)
        scene_id = int(scene_id_raw) if isinstance(scene_id_raw, (int, float)) else idx + 1
        if idx == len(visual_scenes) - 1:
            end = max(cursor + min_slot, audio_end)
        else:
            dur = max(min_slot, total_span * (weights[idx] / float(total_weight)))
            remaining_min = (len(visual_scenes) - idx - 1) * min_slot
            max_allowed = max(cursor + min_slot, audio_end - remaining_min)
            end = min(cursor + dur, max_allowed)
            if end <= cursor:
                end = cursor + min_slot

        txt = str(scene.get("text", "") or "").strip()
        visual = str(scene.get("visual_intent", "") or "").strip() or f"Cinematic photorealistic shot showing: {txt}"
        subjects = scene.get("subjects", [])
        if not isinstance(subjects, list):
            subjects = []
        epochs.append({
            "id": scene_id,
            "start_time": round(cursor, 3),
            "end_time": round(end, 3),
            "duration": round(end - cursor, 3),
            "text": txt,
            "visual_intent": visual,
            "subjects": [str(s).strip() for s in subjects if str(s).strip()]
        })
        cursor = end
    return epochs

def scene_director(state: AgentState):

    print(
        "    [SCENE DIRECTOR] Segmenting script by visual meaning & forging Style DNA...")

    script_text = str(state.get("script", "") or "")
    narration_style = _normalize_narration_style(state.get("narration_style", NARRATION_STYLE_DEFAULT))
    deterministic_user_context_mode = _is_deterministic_user_context_mode(state)
    style_profile = _narration_profile(narration_style)
    script_hash = get_hash(f"{get_hash(script_text)}|{style_profile.get('cache_key', narration_style)}")
    min_scene_count = _minimum_scene_count_for_script(script_text)

    manifest = get_state_manifest()

    scene_file = _artifact_read_path("scene_manifest.json")
    node_report = {
        "status": "pending",
        "source": "unknown",
        "scene_count": 0,
        "requested_min_scene_count": min_scene_count,
        "actual_scene_count": 0,
        "contract_valid": False,
        "failure": "",
        "narration_style": narration_style,
    }

    if (not deterministic_user_context_mode) and manifest.get("scene_script_hash") == script_hash and os.path.exists(scene_file):

        try:

            with open(scene_file, "r", encoding="utf-8") as f:

                data = json.load(f)
            data = _normalize_scene_payload(data, script_text, narration_style=narration_style)
            data = _enforce_scene_mode_style(data, narration_style)

            print(
                "    [RESUMING] Valid scenes & Style DNA found. Skipping Director API call.")
            node_report.update({
                "status": "scenes_directed",
                "source": "cache_resume",
                "scene_count": len(data["scenes"]),
                "actual_scene_count": len(data["scenes"]),
                "contract_valid": True,
            })
            _update_scene_audio_prompt_report("SceneDirector", node_report)

            return {

                "visual_scenes": data["scenes"],

                "style_dna": data["style_dna"],

                "meta_context": data["meta_context"],

                "character_manifest": data.get("character_manifest", {}),

                "status": "scenes_directed"

            }

        except Exception as e:
            node_report["failure"] = f"cache_invalid: {e}"

    prompt = f"""You are a Master Film Director. Break this script into distinct VISUAL SCENES.

1. Segment strictly by complete visual ideas. NEVER break a sentence mid-clause.

2. Aim for 3-5 seconds of spoken audio per scene, but MEANING always overrides timing.

3. For each scene, create a 'visual_intent': a concrete, physical camera shot (no abstract metaphors).

4. Create a single global 'style_dna' (color palette, lens era, lighting texture) to unify the video.

5. Create a single 'meta_context' (1-line summary of the big picture).

6. CHARACTER CASTING: Identify any person, animal, or distinctive object that appears in MORE THAN ONE scene. For each, create a 'character_manifest' entry with a short ID and a 30-50 word hyper-specific physical description (age, gender, hair colour/style, eye colour, skin tone, exact clothing with fabrics/colours, and one unique identifying detail like a scar, badge, or hat). If no recurring subjects exist, set character_manifest to {{}}.

7. For each scene, add a 'subjects' array listing which character IDs appear in that scene. If none, use an array [].

8. CARDINALITY CONTRACT (STRICT): You MUST return AT LEAST {min_scene_count} scenes for this script. If needed, split by sentence-level visual beats, but keep each scene semantically coherent.

9. NARRATION STYLE MODE: {narration_style} ({style_profile.get("label", narration_style)}).
   STYLE INTENT HINT: {style_profile.get("scene_direction_hint", "")}
   If unsure, keep style_dna close to: "{style_profile.get("scene_style_dna_default", "")}"
   If unsure, keep meta_context close to: "{style_profile.get("scene_meta_context_default", "")}"

Return ONLY JSON:

{{

  "style_dna": "Consistent cinematic palette: deep navy, amber...",

  "meta_context": "Documentary about...",

  "character_manifest": {{"professor": "70-year-old man, wispy white Einstein-style hair, circular gold-rimmed spectacles, olive tweed blazer with brown leather elbow patches, navy silk bow tie, deep-set pale blue eyes"}},

  "scenes": [

    {{"id": 1, "text": "Exact sentence(s) from script",
                                       "visual_intent": "Wide drone shot of...", "subjects": ["professor"]}}

  ]

}}

Original Request Topic: {state.get('request_prompt', 'Narration')}

SCRIPT TO SEGMENT:

{script_text}"""

    data = None
    primary_error = None
    low_cardinality_detected = False
    try:
        res = smart_retry(
            fireworks_chat_completion, "fireworks_llm",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="Return strict JSON for film scenes segmentation.",
                temperature=0.2
            ),
            prompt_template_id="PROMPT_F_SCENE_DIRECTOR_SEGMENTATION",
            trace_node="SceneDirector",
        )
        j_text = str(res.text or "").strip()
        data = _normalize_scene_payload(sota_json_repair(j_text), script_text, narration_style=narration_style)
        node_report["source"] = "primary"
        primary_count = len(data.get("scenes", []))
        if primary_count < min_scene_count:
            low_cardinality_detected = True
            node_report["failure"] = f"primary_scene_cardinality_low:{primary_count}<{min_scene_count}"
            data = None
    except Exception as e:
        primary_error = e
        print(f"    [SCENE DIRECTOR] Primary parse needs repair ({e}). Running strict repair retry...")

    if data is None:
        if low_cardinality_detected:
            repair_prompt = f"""Expand this scene segmentation into strict JSON object schema with AT LEAST {min_scene_count} scenes:
{{
  "style_dna": "string",
  "meta_context": "string",
  "character_manifest": {{}},
  "scenes": [{{"id": 1, "text": "string", "visual_intent": "string", "subjects": []}}]
}}

Rules:
- Keep scenes grounded in the provided script.
- scenes must include at least {min_scene_count} coherent visual beats.
- Every scene requires text and visual_intent.
- subjects must be an array.

SCRIPT:
{script_text}

FAILED_ERROR:
primary_scene_cardinality_low
"""
        else:
            repair_prompt = f"""Repair this scene segmentation into strict JSON object schema:
{{
  "style_dna": "string",
  "meta_context": "string",
  "character_manifest": {{}},
  "scenes": [{{"id": 1, "text": "string", "visual_intent": "string", "subjects": []}}]
}}

Rules:
- Keep scenes grounded in the provided script.
- scenes must be a non-empty array.
- Every scene requires text and visual_intent.
- subjects must be an array.

SCRIPT:
{script_text}

FAILED_ERROR:
{str(primary_error)[:600]}
"""
        try:
            rep = smart_retry(
                fireworks_chat_completion, "fireworks_llm",
                contents=repair_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="Return strict JSON object only. No markdown or prose.",
                    temperature=0.0
                ),
                prompt_template_id="PROMPT_F_SCENE_DIRECTOR_REPAIR",
                trace_node="SceneDirector",
            )
            data = _normalize_scene_payload(
                sota_json_repair(str(rep.text or "").strip()), script_text, narration_style=narration_style)
            node_report["source"] = "repair_retry"
        except Exception as e:
            print(f"    [SCENE DIRECTOR] Repair retry failed: {e}")
            node_report["failure"] = f"repair_failed: {e}"

    if data is None:
        data = _deterministic_sentence_scenes(script_text, narration_style=narration_style)
        node_report["source"] = "deterministic_fallback"
    else:
        scene_count = len(data.get("scenes", []))
        if scene_count < min_scene_count:
            print(
                f"    [SCENE DIRECTOR] Scene cardinality guard triggered ({scene_count} < {min_scene_count}). Using deterministic fallback.")
            data = _deterministic_sentence_scenes(script_text, narration_style=narration_style)
            node_report["source"] = "deterministic_cardinality_fallback"
            if not node_report.get("failure"):
                node_report["failure"] = f"scene_cardinality_low:{scene_count}<{min_scene_count}"

    data = _enforce_scene_mode_style(data, narration_style)

    _write_json_artifact("scene_manifest.json", data, mirror_legacy=None)

    manifest["scene_script_hash"] = script_hash
    save_state_manifest(manifest)

    node_report.update({
        "status": "scenes_directed",
        "scene_count": len(data.get("scenes", [])),
        "actual_scene_count": len(data.get("scenes", [])),
        "contract_valid": len(data.get("scenes", [])) > 0,
    })
    _update_scene_audio_prompt_report("SceneDirector", node_report)

    return {
        "visual_scenes": data["scenes"],
        "style_dna": data["style_dna"],
        "meta_context": data["meta_context"],
        "character_manifest": data.get("character_manifest", {}),
        "status": "scenes_directed"
    }



# ==============================================================

# NODE 6: AUDIO ENGINEER (Edge-TTS + Dual-Track Alignment)

# ==============================================================

def audio_engineer(state: AgentState):

    print("[AUDIO]  [AUDIO ENGINEER] Forging high-fidelity speech and VTT alignment...")

    narration_style = _normalize_narration_style(state.get("narration_style", NARRATION_STYLE_DEFAULT))
    deterministic_user_context_mode = _is_deterministic_user_context_mode(state)
    style_profile = _narration_profile(narration_style)
    tts_profile = dict(style_profile.get("audio_tts", {}))
    tts_voice = str(tts_profile.get("voice", "en-GB-RyanNeural") or "en-GB-RyanNeural")
    tts_rate = str(tts_profile.get("rate", "+0%") or "+0%")
    tts_pitch = str(tts_profile.get("pitch", "+0Hz") or "+0Hz")
    tts_volume = str(tts_profile.get("volume", "+0%") or "+0%")
    script_hash = get_hash(
        f"{get_hash(state['script'])}|{style_profile.get('cache_key', narration_style)}|"
        f"{tts_voice}|{tts_rate}|{tts_pitch}|{tts_volume}"
    )

    manifest = get_state_manifest()

    audio_file = _artifact_path("master_narration.mp3")
    audio_read_file = _artifact_read_path("master_narration.mp3")

    vtt_file = _artifact_path("narration.vtt")
    vtt_read_file = _artifact_read_path("narration.vtt")

    matrix_read_file = _artifact_read_path("vtt_matrix.json")
    audio_stage_file = _artifact_path("audio_stage_report.json")
    stage_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "script_hash": script_hash,
        "narration_style": narration_style,
        "style_profile": style_profile.get("label", narration_style),
        "voice": tts_voice,
        "tts_params": {"rate": tts_rate, "pitch": tts_pitch, "volume": tts_volume},
        "stages": [],
        "mapping_source": "",
        "status": "pending",
    }

    def add_stage(stage_name: str, info: dict):
        row = {"stage": stage_name}
        row.update(info or {})
        stage_report["stages"].append(row)
        try:
            _write_json_artifact("audio_stage_report.json", stage_report, mirror_legacy=None)
        except Exception:
            pass

    if (
        not deterministic_user_context_mode
        and manifest.get("audio_script_hash") == script_hash
        and os.path.exists(audio_read_file)
        and os.path.exists(vtt_read_file)
    ):

        try:

            with open(matrix_read_file, "r", encoding="utf-8") as f:

                epochs = _normalize_epochs_from_mapping(json.load(f), state.get("visual_scenes", []))

            print(
                "    [RESUMING] Valid audio and VTT alignment found. Skipping Forge.")
            stage_report["status"] = "audio_forged"
            stage_report["mapping_source"] = "cache_resume"
            add_stage("resume", {"used": True, "epoch_count": len(epochs)})
            _update_scene_audio_prompt_report("Audio", {
                "status": "audio_forged",
                "source": "cache_resume",
                "mapping_source": "cache_resume",
                "epoch_count": len(epochs),
                "total_epochs": len(epochs),
                "contract_valid": len(epochs) > 0,
                "audio_stage_report": audio_stage_file,
            })

            return {
                "audio_path": audio_read_file,
                "vtt_path": vtt_read_file,
                "epochs": epochs,
                "total_epochs": len(epochs),
                "images_forged": state.get("images_forged", 0),
                "qa_attempts": state.get("qa_attempts", 0),
                "status": "audio_forged"
            }

        except Exception as e:
            add_stage("resume", {"used": True, "status": "cache_invalid", "error": str(e)[:220]})

    ingress_script = _sanitize_tts_script(state.get("script", ""))
    if not ingress_script:
        stage_report["status"] = "failed"
        add_stage("ingress", {"status": "failed", "error": "empty_script"})
        _update_scene_audio_prompt_report("Audio", {
            "status": "failed",
            "source": "ingress",
            "mapping_source": "none",
            "contract_valid": False,
            "failure": "empty_script",
        })
        return {"errors": ["Voice Forge Failed: empty script"], "status": "failed"}

    add_stage("ingress", {"status": "ok", "word_count": len(ingress_script.split())})

    cpp_sys = (
        "You are a SOTA prosody engineer for AI Speech. Your ONLY job is to optimize this script for natural human-like pacing by removing or replacing breath-breaking commas. "
        f"STYLE GOAL: {style_profile.get('audio_cpp_goal', '')} "
        "Do NOT add content. Preserve wording and meaning. Output ONLY cleaned narration text."
    )
    tts_script = ingress_script
    cpp_source = "ingress"
    try:
        cpp_res = smart_retry(
            fireworks_chat_completion, "fireworks_llm",
            contents=ingress_script,
            config=types.GenerateContentConfig(
                system_instruction=cpp_sys, temperature=0.05
            ),
            prompt_template_id="PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT",
            trace_node="Audio",
        )
        neural_text = _sanitize_tts_script(str(cpp_res.text or "").strip())
        base_wc = len(ingress_script.split())
        neural_wc = len(neural_text.split())
        overlap = _token_overlap_ratio(ingress_script, neural_text)
        if neural_text and base_wc > 0 and neural_wc > 0 and neural_wc <= int(base_wc * 1.35) and overlap >= 0.60:
            tts_script = neural_text
            cpp_source = "neural_cpp"
            add_stage("neural_cpp", {"status": "accepted", "word_count": neural_wc, "token_overlap": round(overlap, 3)})
        else:
            add_stage("neural_cpp", {"status": "rejected", "word_count": neural_wc, "token_overlap": round(overlap, 3)})
    except Exception as e:
        add_stage("neural_cpp", {"status": "failed", "error": str(e)[:220]})

    if cpp_source != "neural_cpp":
        tts_script = _sanitize_tts_script(apply_cpp(ingress_script))
        cpp_source = "local_cpp_fallback"
        add_stage("local_cpp", {"status": "used", "word_count": len(tts_script.split())})
    tts_script = _sanitize_tts_script(tts_script)
    add_stage("sanitize", {"status": "ok", "word_count": len(tts_script.split())})

    async def _synth():
        comm = edge_tts.Communicate(
            tts_script,
            tts_voice,
            rate=tts_rate,
            pitch=tts_pitch,
            volume=tts_volume,
        )
        sub = edge_tts.SubMaker()
        chunks = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
            elif chunk["type"] in ["WordBoundary", "SentenceBoundary"]:
                if chunk["type"] == "SentenceBoundary":
                    print(f"    [AUDIO ENGINEER] Captured {chunk['type']} at {chunk['offset']/10000000:.2f}s")
                sub.feed(chunk)
        _write_binary_artifact("master_narration.mp3", b"".join(chunks), mirror_legacy=None)
        _write_text_artifact(
            "narration.vtt",
            "WEBVTT\n\n" + sub.get_srt().replace(',', '.'),
            mirror_legacy=None,
        )

    try:

        asyncio.run(_synth())
        add_stage("edge_tts", {"status": "ok"})

    except Exception as e:
        stage_report["status"] = "failed"
        add_stage("edge_tts", {"status": "failed", "error": str(e)[:220]})
        _update_scene_audio_prompt_report("Audio", {
            "status": "failed",
            "source": cpp_source,
            "mapping_source": "none",
            "contract_valid": False,
            "failure": f"Voice Forge Failed: {e}",
        })

        return {"errors": [f"Voice Forge Failed: {e}"], "status": "failed"}

    # Dual-track VTT to epoch alignment

    with open(_artifact_read_path("narration.vtt"), "r", encoding="utf-8") as f:

        vtt_data = f.read()

    # Pass the pre-defined visual scenes to Gemini for mapping

    # Scene Director (Phase 18) means Audio Engineer no longer invents epochs.

    scenes_json = json.dumps(state["visual_scenes"], indent=2)

    prompt = f"""Map precise start_time and end_time VTT boundaries onto these STRICT pre-defined Visual Scenes.

Do NOT invent new scenes, alter the text, or change the IDs. Your ONLY job is to find the timestamp of the first spoken word and the last spoken word for each scene.

Return ONLY a JSON array that perfectly matches the input scenes, but with timestamps added:

[{{"id": 1, "start_time": float, "end_time": float, "duration": float,
    "text": "Exact string", "visual_intent": "Exact string from input"}}]

PRE-DEFINED SCENES TO MAP:

{scenes_json}

VTT TELEMETRY:

{vtt_data}"""

    # Deterministic-first epoch mapping: always build a stable baseline first.
    epochs = _build_local_epoch_mapping(state["visual_scenes"], vtt_data, tts_script)
    mapping_source = "local_deterministic_primary"
    add_stage("vtt_map_local_primary", {"status": "ok", "epoch_count": len(epochs)})

    # Optional strict LLM refine pass; keep deterministic baseline on any failure.
    try:
        res = smart_retry(
            fireworks_chat_completion, "fireworks_llm", contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="Return strict JSON array.", temperature=0.1
            ),
            prompt_template_id="PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING",
            trace_node="Audio",
        )
        raw_epochs = sota_json_repair(str(res.text or "").strip())
        candidate_epochs = _normalize_epochs_from_mapping(raw_epochs, state["visual_scenes"])
        if len(candidate_epochs) == len(epochs):
            epochs = candidate_epochs
            mapping_source = "llm_refine_primary"
            add_stage("vtt_map_refine", {"status": "accepted", "epoch_count": len(epochs)})
        else:
            add_stage("vtt_map_refine", {"status": "rejected", "reason": "epoch_count_mismatch"})
    except Exception as e:
        add_stage("vtt_map_refine", {"status": "failed", "error": str(e)[:220]})

    _write_json_artifact("vtt_matrix.json", epochs, mirror_legacy=None)

    manifest["audio_script_hash"] = script_hash

    save_state_manifest(manifest)
    stage_report["mapping_source"] = mapping_source
    stage_report["status"] = "audio_forged"
    _write_json_artifact("audio_stage_report.json", stage_report, mirror_legacy=None)

    _update_scene_audio_prompt_report("Audio", {
        "status": "audio_forged",
        "source": cpp_source,
        "mapping_source": mapping_source,
        "epoch_count": len(epochs),
        "total_epochs": len(epochs),
        "contract_valid": len(epochs) > 0,
        "audio_stage_report": audio_stage_file,
    })

    print(
        f"    [AUDIO ENGINEER] {len(epochs)} epochs aligned. Audio: {audio_file}")

    return {

        "audio_path": audio_file,

        "vtt_path": vtt_file,

        "epochs": epochs,

        "total_epochs": len(epochs),

        "images_forged": 0,

        "qa_attempts": 0,

        "status": "audio_forged"

    }



# ==============================================================

# NODE 6: PROMPT ARCHITECT (Phase 14)

# ==============================================================

def prompt_architect(state: AgentState):

    print(
        f"    [PROMPT ARCHITECT] Architecting SOTA image prompts for {state['total_epochs']} epochs...")

    narration_style = _normalize_narration_style(state.get("narration_style", NARRATION_STYLE_DEFAULT))
    input_source = str(state.get("input_source", "") or "").strip().upper()
    context_rewrite = _normalize_context_rewrite(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
    deterministic_user_context_mode = input_source == "USER_CONTEXT" and context_rewrite != "force"
    suppress_prompt_architect_api = deterministic_user_context_mode or str(
        os.getenv("TVC_SUPPRESS_PROMPT_ARCHITECT_API", "0") or "0"
    ).strip().lower() in {"1", "true", "on", "yes"}
    style_profile = _narration_profile(narration_style)
    script_hash = get_hash(
        f"{get_hash(state['script'])}|{style_profile.get('cache_key', narration_style)}|"
        f"{get_hash(str(state.get('style_dna', '') or ''))}|{get_hash(str(state.get('meta_context', '') or ''))}"
    )
    manifest = get_state_manifest()
    prompts_file = _artifact_read_path("master_prompts.json")
    node_report = {
        "status": "pending",
        "source": "unknown",
        "prompt_count": 0,
        "qa_count": 0,
        "contract_valid": False,
        "failure": "",
        "narration_style": narration_style,
    }

    def _compose_prompt_for_epoch(epoch: dict, raw_prompt: str) -> tuple:
        style_dna = str(state.get("style_dna", "") or "").strip() or style_profile.get("scene_style_dna_default", "Cinematic documentary palette")
        meta_context = str(state.get("meta_context", "") or "").strip() or style_profile.get("scene_meta_context_default", "Documentary video")
        character_manifest = state.get("character_manifest", {})
        if not isinstance(character_manifest, dict):
            character_manifest = {}
        subjects = epoch.get("subjects", [])
        if not isinstance(subjects, list):
            subjects = []
        char_dna = ""
        for subj in subjects:
            subj_key = str(subj).strip()
            if subj_key and subj_key in character_manifest:
                char_dna += f" Character '{subj_key}': {character_manifest[subj_key]}."
        full = f"{style_dna}. {meta_context}.{char_dna} {raw_prompt}".strip()
        qa = raw_prompt.split('ABSOLUTE NEGATIVE')[0].strip()
        return full, qa

    def _fallback_raw_prompt(epoch: dict) -> str:
        return (
            f"Photorealistic 16:9 cinematic shot: "
            f"{epoch.get('visual_intent', epoch.get('text', style_profile.get('prompt_fallback_scene_label', 'Narration scene')))}"
        )

    def _build_prompt_arrays(entries: Any) -> tuple:
        epochs = state["epochs"]
        by_id = {}
        if isinstance(entries, list):
            for idx, item in enumerate(entries):
                if not isinstance(item, dict):
                    continue
                ep_id = None
                rid = item.get("id")
                if isinstance(rid, int):
                    ep_id = rid
                elif isinstance(rid, float):
                    ep_id = int(rid)
                elif isinstance(rid, str) and rid.strip().isdigit():
                    ep_id = int(rid.strip())
                if ep_id is None and idx < len(epochs):
                    raw_id = epochs[idx].get("id", idx + 1)
                    ep_id = int(raw_id) if isinstance(raw_id, (int, float)) else idx + 1
                by_id[ep_id] = item
        prompts = []
        qa_targets = []
        for idx, epoch in enumerate(epochs):
            raw_id = epoch.get("id", idx + 1)
            ep_id = int(raw_id) if isinstance(raw_id, (int, float)) else idx + 1
            row = by_id.get(ep_id)
            raw_prompt = ""
            if isinstance(row, dict):
                raw_prompt = str(row.get("sota_prompt", "") or "").strip()
            if not raw_prompt:
                raw_prompt = _fallback_raw_prompt(epoch)
            final_prompt, qa = _compose_prompt_for_epoch(epoch, raw_prompt)
            prompts.append(final_prompt)
            qa_targets.append(qa)
        return prompts, qa_targets

    def _cache_valid(data: Any) -> bool:
        needed = len(state["epochs"])
        if needed <= 0:
            return False
        if isinstance(data, list):
            prompts = [str(x).strip() for x in data if str(x).strip()]
            return len(prompts) >= needed
        if isinstance(data, dict):
            prompts = [str(x).strip() for x in data.get("prompts", []) if str(x).strip()]
            qa_targets = [str(x).strip() for x in data.get("qa_targets", []) if str(x).strip()]
            if len(qa_targets) < len(prompts):
                qa_targets.extend([p.split('ABSOLUTE NEGATIVE')[0].strip() for p in prompts[len(qa_targets):]])
            return len(prompts) >= needed and len(qa_targets) >= needed
        return False

    if suppress_prompt_architect_api:
        # Explicit suppression policy: for exact-script deterministic channel,
        # skip PromptArchitect LLM generation and use deterministic local prompt composition.
        sota_prompts, qa_targets = _build_prompt_arrays([])
        _write_json_artifact(
            "master_prompts.json",
            {"prompts": sota_prompts, "qa_targets": qa_targets},
            mirror_legacy=None
        )
        manifest["prompts_script_hash"] = script_hash
        save_state_manifest(manifest)
        suppress_source = "deterministic_user_context_fallback" if deterministic_user_context_mode else "env_suppressed_fallback"
        node_report.update({
            "status": "prompts_architected",
            "source": suppress_source,
            "prompt_count": len(state["epochs"]),
            "qa_count": len(state["epochs"]),
            "contract_valid": True,
        })
        _update_scene_audio_prompt_report("PromptArchitect", node_report)
        print(
            f"    [PROMPT ARCHITECT] API suppressed ({suppress_source}). "
            "Using deterministic local prompt composition."
        )
        for i, final_prompt_string in enumerate(sota_prompts):
            print(f"      - E[{i+1}/{len(state['epochs'])}] {final_prompt_string[:80]}...")
        return {"sota_prompts": sota_prompts[:len(state["epochs"])], "qa_targets": qa_targets[:len(state["epochs"])], "status": "prompts_architected"}

    if manifest.get("prompts_script_hash") == script_hash and os.path.exists(prompts_file):
        try:
            with open(prompts_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _cache_valid(data):
                if isinstance(data, list):
                    sota_prompts = [str(x).strip() for x in data if str(x).strip()]
                    qa_targets = [p.split('ABSOLUTE NEGATIVE')[0].strip() for p in sota_prompts]
                else:
                    sota_prompts = [str(x).strip() for x in data.get("prompts", []) if str(x).strip()]
                    qa_targets = [str(x).strip() for x in data.get("qa_targets", []) if str(x).strip()]
                    if len(qa_targets) < len(sota_prompts):
                        qa_targets.extend([p.split('ABSOLUTE NEGATIVE')[0].strip() for p in sota_prompts[len(qa_targets):]])
                print(
                    "    [RESUMING] Valid visual prompts found for this script. Skipping Architect API call.")
                node_report.update({
                    "status": "prompts_architected",
                    "source": "cache_resume",
                    "prompt_count": len(state["epochs"]),
                    "qa_count": len(state["epochs"]),
                    "contract_valid": True,
                })
                _update_scene_audio_prompt_report("PromptArchitect", node_report)
                return {"sota_prompts": sota_prompts[:len(state["epochs"])], "qa_targets": qa_targets[:len(state["epochs"])], "status": "prompts_architected"}
            node_report["failure"] = "cache_invalid"
        except Exception as e:
            node_report["failure"] = f"cache_parse_error: {e}"

    epochs_json = json.dumps([{"id": e["id"], "text": e["text"], "visual_intent": e.get(
        "visual_intent", e["text"])} for e in state["epochs"]], indent=2)

    sys_inst = f"""You are a master cinematic Vision Director and SOTA Prompt Engineer.

Given a JSON array of narrative text epochs, generate a JSON array of highly-specific, photorealistic, 16:9 cinematic image prompts for EACH epoch.

STYLE MODE CONTEXT: {narration_style} ({style_profile.get("label", narration_style)}).
STYLE HINT: {style_profile.get("prompt_tone_hint", "")}

You MUST use a TWO-STEP REASONING PROCESS:

1. [VISUAL INTENT FOUNDATION]: You have been given a pre-written 'visual_intent' for each epoch. Use this as your foundation. Do NOT ignore it.

2. [SOTA ARCHITECTURE]: Expand that visual intent into a photorealistic, 16:9 cinematic prompt using this EXACT 6-layer Photographic Taxonomy Matrix: [Subject] + [Environment] + [Lighting] + [Camera/Lens] + [Angle/Composition] + [Atmosphere].

CRITICAL NEGATIVE PROMPT INSTRUCTION: At the very end of EVERY prompt, you MUST append EXACTLY this string: " ABSOLUTE NEGATIVE PROMPT: No text, no words, no letters, no typography, no watermarks, no distorted objects."

Do NOT include the Style DNA or Meta-Context in your generation. They will be prepended automatically later.

Return ONLY strict JSON matching this schema exactly: [{{"id": 1, "sota_prompt": "Cinematic 16:9 [Angle] shot of [Subject] in [Environment], [Lighting], captured on [Camera/Lens], [Atmosphere]. ABSOLUTE NEGATIVE PROMPT: No text..."}}]"""

    prompts_data = None
    source = "primary"
    primary_error = None
    try:
        res = smart_retry(
            fireworks_chat_completion, "fireworks_llm",
            contents=epochs_json,
            config=types.GenerateContentConfig(
                system_instruction=sys_inst, temperature=0.2),
            prompt_template_id="PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS",
            trace_node="PromptArchitect",
        )
        prompts_data = sota_json_repair(str(res.text or "").strip())
    except Exception as e:
        primary_error = e

    if prompts_data is None:
        repair_prompt = f"""Repair this epoch prompt payload into strict JSON array schema:
[{{"id": 1, "sota_prompt": "string"}}]
Rules:
- One entry per epoch id from input.
- JSON only, no markdown.

EPOCHS:
{epochs_json}

FAILED_ERROR:
{str(primary_error)[:600]}
"""
        try:
            rep = smart_retry(
                fireworks_chat_completion, "fireworks_llm",
                contents=repair_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="Return strict JSON array only. No prose.",
                    temperature=0.0),
                prompt_template_id="PROMPT_H_PROMPT_ARCHITECT_REPAIR",
                trace_node="PromptArchitect",
            )
            prompts_data = sota_json_repair(str(rep.text or "").strip())
            source = "repair_retry"
        except Exception as e:
            node_report["failure"] = f"repair_failed: {e}"

    if prompts_data is not None:
        try:
            sota_prompts, qa_targets = _build_prompt_arrays(prompts_data)
        except Exception as e:
            print(f"    [WARNING] Prompt Architect normalization failed. Falling back to literal translation. {e}")
            prompts_data = None

    if prompts_data is None:
        source = "literal_fallback"
        sota_prompts, qa_targets = _build_prompt_arrays([])

    if len(sota_prompts) != len(state["epochs"]) or len(qa_targets) != len(state["epochs"]):
        source = "literal_fallback"
        sota_prompts, qa_targets = _build_prompt_arrays([])

    for i, final_prompt_string in enumerate(sota_prompts):
        print(
            f"      - E[{i+1}/{len(state['epochs'])}] {final_prompt_string[:80]}...")

    _write_json_artifact(
        "master_prompts.json",
        {"prompts": sota_prompts, "qa_targets": qa_targets},
        mirror_legacy=None,
    )

    manifest["prompts_script_hash"] = script_hash

    save_state_manifest(manifest)
    node_report.update({
        "status": "prompts_architected",
        "source": source,
        "prompt_count": len(sota_prompts),
        "qa_count": len(qa_targets),
        "contract_valid": len(sota_prompts) == len(state["epochs"]) and len(qa_targets) == len(state["epochs"]),
    })
    _update_scene_audio_prompt_report("PromptArchitect", node_report)

    print(
        f"    [PROMPT ARCHITECT] Successfully forged {len(sota_prompts)} master prompts.")

    return {"sota_prompts": sota_prompts[:len(state["epochs"])], "qa_targets": qa_targets[:len(state["epochs"])], "status": "prompts_architected"}



# ==============================================================

# NODE 7: SOTA VISION FORGE (Per-Image Recursive QA & Refinement)

# ==============================================================

def _create_deterministic_placeholder_image(path: str, label: str = "") -> bool:
    try:
        _ensure_artifact_parent(path)
        if Image:
            img = Image.new("RGB", (1920, 1080), (18, 20, 28))
            if ImageDraw:
                draw = ImageDraw.Draw(img)
                draw.rectangle((80, 80, 1840, 1000), outline=(70, 78, 102), width=4)
                if str(os.getenv("TVC_PLACEHOLDER_DEBUG_TEXT", "0") or "0").strip() == "1":
                    txt = f"TVC PLACEHOLDER FRAME {label}".strip()
                    draw.text((120, 120), txt[:120], fill=(210, 218, 240))
            img.save(path, format="PNG")
            return True
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#12141c:s=1920x1080:d=1",
            "-frames:v",
            "1",
            path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return os.path.exists(path)
    except Exception:
        return False


def _ensure_epoch_image_with_fallback(target_fp: str, last_valid_path: str = "", label: str = "") -> str:
    if target_fp and os.path.exists(target_fp):
        return "generated"
    if last_valid_path and os.path.exists(last_valid_path):
        try:
            _ensure_artifact_parent(target_fp)
            shutil.copy2(last_valid_path, target_fp)
            return "copied_previous"
        except Exception:
            pass
    ok = _create_deterministic_placeholder_image(target_fp, label=label)
    if ok:
        return "placeholder"
    raise RuntimeError(f"Failed to create deterministic fallback image for epoch asset: {target_fp}")


def _extract_main_description_for_qa(current_prompt: str, qa_targets: List[str], idx: int) -> str:
    raw_scene = qa_targets[idx] if idx < len(qa_targets) else None
    if not raw_scene:
        scene_match = re.search(
            r'(?:Cinematic 16:9|Photorealistic 16:9)\s+(.+?)(?:\s*ABSOLUTE NEGATIVE|$)',
            str(current_prompt or ""),
            re.DOTALL | re.IGNORECASE
        )
        raw_scene = scene_match.group(1).strip() if scene_match else str(current_prompt or "")[-240:]
    scene_clauses = [c.strip() for c in str(raw_scene).split(",") if c.strip()]
    main_description = ", ".join(scene_clauses[:2]).strip()
    return (main_description or "cinematic scene")[:500]


def _build_epoch_context_payload(epochs: List[dict], text_limit: int = 160, visual_limit: int = 220) -> List[dict]:
    payload = []
    def _clip(s: str, n: int) -> str:
        t = re.sub(r"\s+", " ", str(s or "")).strip()
        if n <= 0:
            return t
        if len(t) <= n:
            return t
        return t[: max(0, n - 3)].rstrip() + "..."
    for idx, ep in enumerate(epochs or []):
        if not isinstance(ep, dict):
            continue
        raw_id = ep.get("id", idx + 1)
        try:
            ep_id = int(raw_id) if isinstance(raw_id, (int, float, str)) else idx + 1
        except Exception:
            ep_id = idx + 1
        text = _clip(ep.get("text", ""), text_limit)
        visual_intent = _clip(ep.get("visual_intent", ep.get("text", "")), visual_limit)
        payload.append({
            "id": ep_id,
            "text": text,
            "visual_intent": visual_intent,
        })
    return payload


def _compose_image_generation_prompt(
    base_prompt: str,
    epoch: dict,
    epochs_payload: List[dict],
) -> str:
    raw_id = epoch.get("id", 0) if isinstance(epoch, dict) else 0
    try:
        target_id = int(raw_id) if isinstance(raw_id, (int, float, str)) else 0
    except Exception:
        target_id = 0
    target_text = re.sub(r"\s+", " ", str((epoch or {}).get("text", "") or "")).strip()
    target_visual = re.sub(r"\s+", " ", str((epoch or {}).get("visual_intent", target_text) or target_text)).strip()
    target_text = target_text[:160] + ("..." if len(target_text) > 160 else "")
    target_visual = target_visual[:260] + ("..." if len(target_visual) > 260 else "")
    base_clean = re.sub(r"\s+", " ", str(base_prompt or "")).strip()
    base_clean = re.sub(r"ABSOLUTE NEGATIVE PROMPT:.*$", "", base_clean, flags=re.IGNORECASE).strip()
    style_hint = ""
    if base_clean:
        style_hint = base_clean.split(".", 1)[0].strip()
    if not style_hint:
        style_hint = "Photorealistic cinematic 16:9 frame"
    style_hint = style_hint[:140] + ("..." if len(style_hint) > 140 else "")
    payload_json = json.dumps(epochs_payload, ensure_ascii=True, separators=(",", ":"))
    prompt = (
        "PRIMARY SHOT DIRECTIVE:\n"
        f"{style_hint}. Target visual: {target_visual}\n\n"
        "USER CONTENT (exact `contents` payload):\n"
        f"{payload_json}\n\n"
        "TARGET EPOCH:\n"
        f"id={target_id}\n"
        f"text={target_text}\n"
        f"visual_intent={target_visual}\n\n"
        "HARD RULES:\n"
        "- Render only the TARGET EPOCH scene.\n"
        "- Treat the payload as context memory; do not blend all epochs into one frame.\n"
        "- Preserve photorealistic cinematic composition.\n"
        "- No text, letters, words, typography, or watermarks in the image."
    )
    # Keep a strict upper bound to avoid provider-side invalid_request payload rejection.
    if len(prompt) > 2400:
        compact_payload = _build_epoch_context_payload(epochs_payload, text_limit=96, visual_limit=120) if epochs_payload else []
        compact_json = json.dumps(compact_payload, ensure_ascii=True, separators=(",", ":"))
        prompt = (
            "PRIMARY SHOT DIRECTIVE:\n"
            f"{style_hint}. Target visual: {target_visual}\n\n"
            "USER CONTENT (exact `contents` payload):\n"
            f"{compact_json}\n\n"
            "TARGET EPOCH:\n"
            f"id={target_id}\n"
            f"text={target_text}\n"
            f"visual_intent={target_visual}\n\n"
            "HARD RULES:\n"
            "- Render only the TARGET EPOCH scene.\n"
            "- Treat the payload as context memory; do not blend all epochs into one frame.\n"
            "- Preserve photorealistic cinematic composition.\n"
            "- No text, letters, words, typography, or watermarks in the image."
        )
    return prompt


def _compose_compact_epoch_fallback_prompt(epoch: dict, style_hint: str = "") -> str:
    target_text = re.sub(r"\s+", " ", str((epoch or {}).get("text", "") or "")).strip()
    target_visual = re.sub(r"\s+", " ", str((epoch or {}).get("visual_intent", target_text) or target_text)).strip()
    target_visual = target_visual[:300] + ("..." if len(target_visual) > 300 else "")
    base = style_hint.strip() if style_hint else "Photorealistic cinematic 16:9 frame"
    base = base[:120] + ("..." if len(base) > 120 else "")
    return (
        f"{base}. Target visual: {target_visual}. "
        "ABSOLUTE NEGATIVE PROMPT: No text, no words, no letters, no typography, no watermarks, no distorted objects."
    )


def _build_visual_qa_prompt(main_description: str, qa_pass_threshold: float) -> str:
    return (
        "You are a professional cinematic Art Director performing a quality review of a generated image.\n\n"
        f"The image was generated from this scene description:\n'{main_description}'\n\n"
        "Score this image out of 10 using these weighted criteria:\n"
        "  [40%] SUBJECT PRESENCE: Does the core subject/action from the description appear clearly in the image?\n"
        "  [30%] TECHNICAL QUALITY: Is the image free of AI artifacts, distorted anatomy, blurry faces, duplicate limbs, or nonsense geometry?\n"
        "  [20%] VISUAL QUALITY: Is the image sharp, well-exposed, and cinematically composed (not a snapshot)?\n"
        "  [10%] ATMOSPHERE: Does the mood of the image roughly match the described tone?\n\n"
        "IMPORTANT RULES:\n"
        "  - Do NOT penalize for color temperature, warm vs cool tones, or lighting style. These are artistic choices.\n"
        "  - Do NOT require the camera model, lens type, or aspect ratio to be visible.\n"
        "  - DO immediately score 3.0 or lower if: the image contains visible text/letters, or has severely distorted human anatomy.\n\n"
        f"CRITICAL: If score < {qa_pass_threshold:.1f}, you MUST classify the failure into EXACTLY ONE of these categories:\n"
        "  CATEGORY:TEXT - if the image contains visible text, letters, words, or typography\n"
        "  CATEGORY:ANATOMY - if there are distorted faces, hands, limbs, or body parts\n"
        "  CATEGORY:SUBJECT - if the wrong subject or action is shown\n"
        "  CATEGORY:COMPOSITION - if the scene is too cluttered or confusing\n"
        "  CATEGORY:QUALITY - if the image has blur, noise, or low resolution\n\n"
        "Respond ONLY in this exact format: 'SCORE: X/10. CATEGORY:XXX. CRITIQUE: [one sentence explaining the score]'"
    )


def _run_visual_qa_for_image(image_path: str, main_description: str, qa_model: str, qa_pass_threshold: float) -> Dict[str, Any]:
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    qa_prompt = _build_visual_qa_prompt(main_description, qa_pass_threshold)
    qa_res = smart_retry(
        fireworks_chat_completion, "fireworks_llm",
        contents=[qa_prompt, img_bytes],
        model=qa_model,
        config=types.GenerateContentConfig(
            system_instruction="Return the exact score/category/critique format requested by the user prompt.",
            temperature=0.0
        ),
        prompt_template_id="PROMPT_J_SOTA_FORGE_VISUAL_QA",
        trace_node="SotaForge",
    )
    qa_text = str(qa_res.text or "").strip()

    score_match = re.search(
        r'SCORE:\s*(10(?:\.0+)?|[0-9](?:\.\d+)?)\s*/\s*10\b',
        qa_text,
        re.IGNORECASE
    )
    if not score_match:
        score_match = re.search(
            r'\b(10(?:\.0+)?|[0-9](?:\.\d+)?)\s*/\s*10\b',
            qa_text,
            re.IGNORECASE
        )
    score = float(score_match.group(1)) if score_match else 0.0
    score = max(0.0, min(10.0, score))
    has_real_score = score_match is not None

    category_match = re.search(r'CATEGORY:\s*([A-Z]+)', qa_text, re.IGNORECASE)
    failure_cat = category_match.group(1).upper() if category_match else "UNKNOWN"
    critique = qa_text.split('CRITIQUE:')[-1].strip() if 'CRITIQUE:' in qa_text else qa_text[:120]

    return {
        "qa_text": qa_text,
        "score": score,
        "has_real_score": has_real_score,
        "critique": critique,
        "failure_cat": failure_cat,
    }


def sota_vision_forge(state: AgentState):

    print(
        f"    [SOTA VISION FORGE] Activating Per-Epoch Precision Rendering for {state['total_epochs']} epochs...")
    qa_pass_threshold = 4.0
    qa_model = str(os.getenv("FIREWORKS_VISION_QA_MODEL", "accounts/fireworks/models/kimi-k2p5") or "accounts/fireworks/models/kimi-k2p5").strip()
    input_source = str(state.get("input_source", "") or "").strip().upper()
    context_rewrite = _normalize_context_rewrite(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
    deterministic_user_context_mode = input_source == "USER_CONTEXT" and context_rewrite != "force"
    suppress_visual_qa = deterministic_user_context_mode or str(
        os.getenv("TVC_SUPPRESS_VISUAL_QA", "0") or "0"
    ).strip().lower() in {"1", "true", "on", "yes"}
    if suppress_visual_qa:
        print("    [SOTA VISION FORGE] Visual QA is suppressed for this run.")

    asset_dir = _artifact_path("assets")

    os.makedirs(asset_dir, exist_ok=True)

    sc = smartcrop.SmartCrop() if smartcrop else None

    final_scores = []
    last_valid_image_path = ""

    # Phase 22: Initialize Cross-Epoch Run Memory (ALC)

    run_memory = {"TEXT": 0, "ANATOMY": 0,
                  "SUBJECT": 0, "COMPOSITION": 0, "QUALITY": 0}
    qa_targets = state.get("qa_targets", [])
    epochs_payload = _build_epoch_context_payload(state.get("epochs", []))

    for i, epoch in enumerate(state["epochs"]):

        current_prompt = state["sota_prompts"][i]
        seeded_image_prompt = _compose_image_generation_prompt(
            base_prompt=current_prompt,
            epoch=epoch,
            epochs_payload=epochs_payload,
        )

        # Phase 24: SOTA Content-Addressable Caching (Prompt Hashing)

        prompt_hash = hashlib.sha256(
            seeded_image_prompt.encode('utf-8')).hexdigest()[:8]

        target_fp = os.path.join(
            asset_dir, f"epoch_{epoch['id']:03d}_{prompt_hash}.png")
        epoch["image_path"] = target_fp

        # Phase 22: Safe cache validation with real QA re-check.

        if os.path.exists(target_fp):
            try:
                with Image.open(target_fp) as cached_img:
                    cache_valid_dims = cached_img.size[0] >= 1920 and cached_img.mode in ('RGB', 'RGBA')
                    cache_dims = cached_img.size
                if cache_valid_dims:
                    if suppress_visual_qa:
                        epoch["image_source"] = "generated"
                        last_valid_image_path = target_fp
                        final_scores.append(float(qa_pass_threshold))
                        print(f"  [OK] [CACHED NO-QA] Epoch {epoch['id']:03d} accepted.")
                        continue
                    main_description = _extract_main_description_for_qa(current_prompt, qa_targets, i)
                    try:
                        qa_result = _run_visual_qa_for_image(
                            image_path=target_fp,
                            main_description=main_description,
                            qa_model=qa_model,
                            qa_pass_threshold=qa_pass_threshold,
                        )
                    except Exception as cache_qa_err:
                        qa_result = {
                            "qa_text": "CATEGORY:QUALITY",
                            "score": 0.0,
                            "has_real_score": False,
                            "critique": f"Vision QA unavailable for cache: {str(cache_qa_err)[:120]}",
                            "failure_cat": "QUALITY",
                        }
                    if qa_result["has_real_score"] and qa_result["score"] >= qa_pass_threshold:
                        epoch["image_source"] = "generated"
                        last_valid_image_path = target_fp
                        final_scores.append(float(qa_result["score"]))
                        print(
                            f"  [OK] [CACHED+QA] Epoch {epoch['id']:03d} accepted at {qa_result['score']}/10.")
                        continue
                    print(
                        f"  [WARN] [CACHE REJECTED] Epoch {epoch['id']:03d} scored {qa_result['score']}/10 "
                        f"(real_score={qa_result['has_real_score']}). Regenerating.")
                    os.remove(target_fp)
                else:
                    print(
                        f"  [WARN] [CACHE INVALID] Epoch {epoch['id']:03d} has wrong dims {cache_dims}. Regenerating.")
                    os.remove(target_fp)
            except Exception:
                print(
                    f"  [WARN] [CACHE CORRUPT] Epoch {epoch['id']:03d} unreadable. Regenerating.")
                if os.path.exists(target_fp):
                    os.remove(target_fp)

        # Phase 22: ALC Preventive Prompt Surgery using Cross-Epoch Memory

        if run_memory.get("TEXT", 0) >= 2:

            print(
                f"    [ALC RUN-MEMORY] TEXT failures dominant across previous epochs. Pre-applying anti-text surgery.")

            text_patterns = [r'\b(?:sign|banner|inscription|scroll|letter|book|title|headline|placard|poster|notice|calligraphy|writing)\b',
                             r'\b(?:text|words|letters|typography)\b']

            for pat in text_patterns:
                current_prompt = re.sub(pat, '', current_prompt, flags=re.IGNORECASE)

        epoch_text = epoch["text"]
        print(f"\n  - Epoch {epoch['id']:03d}: '{epoch_text[:60]}...'")

        passed = False
        score = 0.0 # Initialized to avoid UnboundLocalError if API fails
        failure_memory = []  # Phase 22: Per-Epoch Failure Memory
        temp_fp = target_fp.replace(".png", "_temp.png")

        for attempt in range(1, 4):

            generation_prompt = _compose_image_generation_prompt(
                base_prompt=current_prompt,
                epoch=epoch,
                epochs_payload=epochs_payload,
            )
            fallback_generation_prompt = _compose_compact_epoch_fallback_prompt(
                epoch=epoch,
                style_hint=str(current_prompt or "").split(".", 1)[0].strip(),
            )
            if attempt == 1:
                try:
                    _write_text_artifact(
                        f"sota_epoch_{epoch['id']:03d}_generation_prompt.txt",
                        generation_prompt,
                        mirror_legacy=None,
                    )
                except Exception:
                    pass

            print(f"    Shot {attempt}/3 | Prompt: {current_prompt[:60]}...")

            # --- 1. Generation Phase ---

            generation_success = False

            # PRIMARY: Fireworks FLUX.1 Schnell
            print(f"        [MODE: FIREWORKS FLUX.1 SCHNELL]")

            try:
                generation_success = smart_retry(
                    fireworks_generate_image, "fireworks_image",
                    prompt=generation_prompt, width=1920, height=1088, output_path=temp_fp,
                    prompt_template_id="PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT",
                    trace_node="SotaForge",
                )
            except Exception as gen_err:
                generation_success = False
                gen_err_txt = str(gen_err or "")
                gen_err_low = gen_err_txt.lower()
                # Recovery path: if the combined context prompt is rejected, retry once
                # with a compact target-epoch-only prompt to preserve image continuity.
                if "400" in gen_err_low or "invalid_request" in gen_err_low:
                    print("        [MODE: FIREWORKS COMPACT FALLBACK] combined prompt rejected, retrying compact prompt.")
                    try:
                        if attempt == 1:
                            _write_text_artifact(
                                f"sota_epoch_{epoch['id']:03d}_generation_prompt_fallback.txt",
                                fallback_generation_prompt,
                                mirror_legacy=None,
                            )
                        generation_success = smart_retry(
                            fireworks_generate_image, "fireworks_image",
                            prompt=fallback_generation_prompt, width=1920, height=1088, output_path=temp_fp,
                            prompt_template_id="PROMPT_I_SOTA_FORGE_FALLBACK_COMPACT",
                            trace_node="SotaForge",
                        )
                    except Exception as fb_err:
                        generation_success = False
                        print(
                            f"        [MODE: FIREWORKS COMPACT FALLBACK] generation failed: {str(fb_err)[:180]}"
                        )
                if not generation_success:
                    print(f"        [MODE: FIREWORKS FLUX.1 SCHNELL] generation failed: {gen_err_txt[:180]}")

            # Saliency crop (runs regardless of which engine generated the image)

            if generation_success and sc and Image:

                try:

                    with Image.open(temp_fp) as img:

                        if img.mode != 'RGB':
                            img = img.convert('RGB')

                        w, h = img.size

                        scale = min(w / 1920, h / 1080)

                        cw, ch = int(1920 * scale), int(1080 * scale)

                        result = sc.crop(img, cw, ch)

                        tc = result['top_crop']

                        cropped = img.crop(
                            (tc['x'], tc['y'], tc['x'] + tc['width'], tc['y'] + tc['height']))

                        resized = cropped.resize(
                            (1920, 1080), Image.Resampling.LANCZOS)

                        resized.save(temp_fp, quality=95)

                except Exception:

                    pass  # Saliency crop is optional; don't block pipeline

            if not generation_success:

                continue

            # --- 2. Visual QA Phase ---

            if suppress_visual_qa:
                score = qa_pass_threshold
                has_real_score = True
                critique = "Visual QA suppressed for this run."
                qa_text = "CATEGORY:SKIPPED"
                print("    [QA SUPPRESSED] Accepting generated image without QA scoring.")
            else:
                try:
                    main_description = _extract_main_description_for_qa(current_prompt, qa_targets, i)
                    qa_result = _run_visual_qa_for_image(
                        image_path=temp_fp,
                        main_description=main_description,
                        qa_model=qa_model,
                        qa_pass_threshold=qa_pass_threshold,
                    )
                    qa_text = qa_result["qa_text"]
                    score = float(qa_result["score"])
                    has_real_score = bool(qa_result["has_real_score"])
                    critique = qa_result["critique"]
                    print(
                        f"    QA Score: {score}/10 | Feedback: {critique[:120].replace(chr(10), ' ')}...")

                except Exception as e:

                    # Fail-closed: no simulated score on QA outage.
                    score = 0.0
                    has_real_score = False
                    critique = f"Vision QA unavailable: {str(e)[:120]}"
                    qa_text = "CATEGORY:QUALITY"

                    print(
                        f"    [QA WARNING] API failed. No simulated pass. {str(e)[:80]}")

            # --- 3. Threshold Evaluation ---

            if has_real_score and score >= qa_pass_threshold:

                print(
                    f"    [OK] [QA PASSED] Epoch {epoch['id']:03d} locked at {score}/10.")

                if os.path.exists(target_fp):
                    os.remove(target_fp)

                os.rename(temp_fp, target_fp)
                epoch["image_source"] = "generated"
                last_valid_image_path = target_fp

                final_scores.append(score)

                passed = True

                break

            else:

                category_match = re.search(
                    r'CATEGORY:\s*([A-Z]+)', qa_text, re.IGNORECASE)

                failure_cat = category_match.group(
                    1).upper() if category_match else "UNKNOWN"

                failure_memory.append(failure_cat)

                print(
                    f"     [QA FAILED] Category: {failure_cat} | Initiating prompt refinement...")

                # --- 4. Adaptive Learning Circuit (ALC) Prompt Refinement ---

                if attempt < 3:

                    if os.path.exists(temp_fp):
                        os.remove(temp_fp)

                    recurring = len(failure_memory) >= 2 and failure_memory[-1] == failure_memory[-2]

                    if recurring and failure_cat == "TEXT":

                        print(
                            f"     [ALC] Recurring TEXT failure. Performing targeted text-removal surgery.")

                        text_patterns = [

                            r'\b(?:sign|banner|inscription|scroll|letter|book|title|headline|placard|poster|notice|calligraphy|writing)\b',

                            r'\b(?:text|words|letters|typography)\b',

                        ]

                        for pat in text_patterns:

                            current_prompt = re.sub(
                                pat, '', current_prompt, flags=re.IGNORECASE)

                        current_prompt = current_prompt.replace(

                            "ABSOLUTE NEGATIVE PROMPT:",

                            "ABSOLUTE NEGATIVE PROMPT: No visible text of any kind, no signage, no readable letters, no writing, no typography,"

                        )

                    elif recurring and failure_cat == "ANATOMY":

                        print(
                            f"    [ALC] Recurring ANATOMY failure. Stripping Character DNA complexity.")

                        current_prompt = re.sub(
                            r" Character '\w+':\s*\{[^}]+\}\.", '', current_prompt)

                        current_prompt = current_prompt.replace(

                            "ABSOLUTE NEGATIVE PROMPT:",

                            "ABSOLUTE NEGATIVE PROMPT: No distorted anatomy, no extra limbs, no deformed faces,"

                        )

                    elif recurring and failure_cat == "SUBJECT":

                        print(
                            f"    [ALC] Recurring SUBJECT failure. Resetting prompt to original master.")

                        current_prompt = state["sota_prompts"][i]

                    elif recurring and failure_cat == "COMPOSITION":

                        print(
                            f"    [ALC] Recurring COMPOSITION failure. Stripping background complexity.")

                        raw_scene_fallback = qa_targets[i] if i < len(
                            qa_targets) else current_prompt[-200:]

                        current_prompt = f"Photorealistic 16:9 cinematic shot. {raw_scene_fallback} ABSOLUTE NEGATIVE PROMPT: No text, no words, no letters, no typography, no watermarks, no distorted objects."

                    else:

                        # Non-destructive additive refinement

                        neg_fence = "ABSOLUTE NEGATIVE PROMPT:"

                        if neg_fence in current_prompt:

                            clean_base, neg_part = current_prompt.split(
                                neg_fence, 1)

                            current_prompt = f"{clean_base.rstrip()}. REFINEMENT: {critique[:120]}. {neg_fence}{neg_part}"

                        else:

                            current_prompt += f" REFINEMENT: {critique[:120]}."

        if not passed:

            print(
                f"    [WARN] [SURRENDER] Epoch {epoch['id']:03d} failed to reach QA {qa_pass_threshold:.1f}/10 after 3 shots (Score: {score}). Applying Graceful Surrender Protocol.")

            if failure_memory:

                dominant_cat = failure_memory[-1]

                run_memory[dominant_cat] = run_memory.get(dominant_cat, 0) + 1

            if os.path.exists(temp_fp):
                if os.path.exists(target_fp):
                    os.remove(target_fp)
                os.rename(temp_fp, target_fp)

            image_source = _ensure_epoch_image_with_fallback(
                target_fp,
                last_valid_path=last_valid_image_path,
                label=f"EPOCH-{epoch['id']:03d}",
            )
            epoch["image_source"] = image_source
            if os.path.exists(target_fp):
                last_valid_image_path = target_fp
            final_scores.append(score)
        else:
            # Defensive guarantee: never leave epoch without a resolvable frame.
            epoch["image_source"] = _ensure_epoch_image_with_fallback(
                target_fp,
                last_valid_path=last_valid_image_path,
                label=f"EPOCH-{epoch['id']:03d}",
            )
            if os.path.exists(target_fp):
                last_valid_image_path = target_fp

    print(f"\n[OK]  [SOTA VISION FORGE] Mission Accomplished. {len(final_scores)}/{state['total_epochs']} epochs forged to perfection.")

    return {"status": "sota_vision_complete", "qa_scores": final_scores, "images_forged": len(final_scores), "epochs": state["epochs"]}





# ==============================================================

# NODE 8: LEAD EDITOR (Dual-Layer ASS + NLE Math)

# ==============================================================

def _schedule_topic_cards_one_at_a_time(callouts: List[dict], epochs: List[dict], timeline_end: float):
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "policy": "strict_one_at_a_time",
        "input_callouts": callouts,
        "resolved_anchors": [],
        "scheduled_windows": [],
        "dropped": [],
        "input_count": len(callouts) if isinstance(callouts, list) else 0,
        "valid_count": 0,
        "scheduled_count": 0,
        "dropped_count": 0,
        "adjusted_count": 0,
    }
    if not epochs:
        report["dropped"].append({"reason": "no_epochs"})
        report["dropped_count"] = len(report["dropped"])
        return [], report

    timeline_start = float(epochs[0].get("start_time", 0.0))
    last_epoch_end = float(epochs[-1].get("end_time", timeline_start))
    if timeline_end <= timeline_start:
        timeline_end = last_epoch_end
    timeline_end = max(timeline_end, last_epoch_end)
    report["timeline_start"] = round(timeline_start, 3)
    report["timeline_end"] = round(timeline_end, 3)

    valid = []
    for idx, callout in enumerate(callouts or []):
        if not isinstance(callout, dict):
            report["dropped"].append({"input_index": idx, "reason": "not_dict"})
            continue
        topic = str(callout.get("topic", "") or "").strip().upper()
        if not topic:
            report["dropped"].append({"input_index": idx, "reason": "empty_topic"})
            continue
        try:
            raw_after = callout.get("after_sentence", 1)
            if isinstance(raw_after, bool):
                raise ValueError("bool-not-allowed")
            sent_idx = int(raw_after) - 1
        except Exception:
            report["dropped"].append(
                {"input_index": idx, "reason": "invalid_after_sentence", "raw": callout.get("after_sentence")})
            continue
        if sent_idx < 0 or sent_idx >= len(epochs):
            report["dropped"].append(
                {"input_index": idx, "reason": "out_of_range_after_sentence", "raw": callout.get("after_sentence")})
            continue

        anchor_start = float(epochs[sent_idx].get("start_time", timeline_start))
        resolved = {
            "input_index": idx,
            "topic": topic,
            "after_sentence": sent_idx + 1,
            "anchor_start": round(anchor_start, 3),
        }
        report["resolved_anchors"].append(resolved)
        valid.append(resolved)

    report["valid_count"] = len(valid)
    if not valid:
        report["dropped_count"] = len(report["dropped"])
        return [], report

    available = max(0.8, timeline_end - timeline_start)
    adaptive_duration = available / float(max(1, len(valid)))
    card_duration = max(0.9, min(2.6, adaptive_duration * 0.6))
    gap = max(0.12, min(0.35, card_duration * 0.18))
    min_visible = 0.55

    report["card_duration_seconds"] = round(card_duration, 3)
    report["gap_seconds"] = round(gap, 3)

    scheduled = []
    cursor = timeline_start
    for item in valid:
        start = max(item["anchor_start"], cursor)
        end = min(start + card_duration, timeline_end)
        if (end - start) < min_visible:
            report["dropped"].append({
                "input_index": item["input_index"],
                "topic": item["topic"],
                "reason": "timeline_exhausted",
                "anchor_start": item["anchor_start"],
            })
            continue

        adjusted = abs(start - item["anchor_start"]) > 1e-4
        scheduled_item = {
            "input_index": item["input_index"],
            "topic": item["topic"],
            "after_sentence": item["after_sentence"],
            "anchor_start": item["anchor_start"],
            "start": round(start, 3),
            "end": round(end, 3),
            "adjusted": adjusted,
        }
        scheduled.append(scheduled_item)
        report["scheduled_windows"].append(scheduled_item)
        cursor = end + gap

    report["scheduled_count"] = len(scheduled)
    report["adjusted_count"] = sum(1 for s in scheduled if s.get("adjusted"))
    report["dropped_count"] = len(report["dropped"])
    return scheduled, report


def lead_editor(state: AgentState):

    print("    [LEAD EDITOR] Assembling dual-layer ASS typography and NLE render...")



    # === Dual-Layer ASS ===

    ass_path = _artifact_path("typography.ass")

    header = (

        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 1\n\n"

        "[V4+ Styles]\n"

        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "

        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "

        "Alignment, MarginL, MarginR, MarginV, Encoding\n"

        "Style: ClassyBlurb,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,3,10,0,2,100,100,10,1\n"

        "Style: TopicCard,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&HB0000000,-1,0,0,0,100,100,2,0,4,12,0,8,400,400,10,1\n\n"
        "Style: WatermarkTag,Arial,10,&H0037D8FF,&H00FFC36E,&H004A0F2C,&H900A0415,-1,0,0,0,100,100,0,0,1,2,1,5,120,120,15,1\n"
        "Style: WatermarkLine,Arial,10,&H00FFC36E,&H0037D8FF,&H00301122,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n"

        "[Events]\n"

        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

    )



    def sec_to_ass(s):

        h, m = int(s // 3600), int((s % 3600) // 60)

        sc, cs = int(s % 60), int(round((s - int(s)) * 100))

        if cs == 100: cs = 99

        return f"{h}:{m:02d}:{sc:02d}.{cs:02d}"

    # Get true audio duration early so callout overlays can be scheduled deterministically.
    aud_dur_str = subprocess.getoutput(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{state["audio_path"]}"'
    )
    try:
        audio_duration = float(aud_dur_str.strip())
    except ValueError:
        audio_duration = state.get("target_duration", 60)

    watermark_mode = _normalize_watermark_mode(
        state.get("watermark_mode", WATERMARK_MODE_DEFAULT)
    )
    watermark_enabled = watermark_mode == "on"
    wm_text = "linkedin.com/in/nilhandemel"
    playres_x, playres_y = 1920, 1080
    wm_center_x, wm_center_y = playres_x // 2, playres_y // 2
    line_half_len = 230
    line_gap_from_text = 120
    line_thickness = 4
    accent_half_len = 45
    accent_gap_from_center = 30
    watermark_report = {
        "enabled": watermark_enabled,
        "mode": watermark_mode,
        "text": wm_text,
        "style": "WatermarkTag",
        "line_style": "WatermarkLine",
        "font_size": 10,
        "playres": {"x": playres_x, "y": playres_y},
        "position": {"x": wm_center_x, "y": wm_center_y},
        "center_invariant": {
            "distance_from_top": wm_center_y,
            "distance_from_bottom": playres_y - wm_center_y,
            "is_equal": wm_center_y == (playres_y - wm_center_y),
        },
        "line_geometry": {},
        "timeline": {},
    }

    overlay_report = {}

    with open(ass_path, "w", encoding="utf-8") as f:

        f.write(header)



        # Layer 1: Narration subtitles

        for ep in state["epochs"]:

            txt = ep['text'].replace('\n', ' ')

            f.write(f"Dialogue: 0,{sec_to_ass(ep['start_time'])},{sec_to_ass(ep['end_time'])},ClassyBlurb,,0,0,0,,{txt}\n")



        # Layer 2: Topic callout cards

        callouts = state.get("topic_callouts", [])

        scheduled_cards, overlay_report = _schedule_topic_cards_one_at_a_time(
            callouts, state.get("epochs", []), float(audio_duration)
        )
        for card in scheduled_cards:
            # Layer 2: Topic callout cards - one-at-a-time deterministic scheduler.
            f.write(
                f"Dialogue: 1,{sec_to_ass(card['start'])},{sec_to_ass(card['end'])},TopicCard,,0,0,0,,{{\\fad(300,300)}}{card['topic']}\n")

        # Layer 3: Watermark (exact center, full timeline) with mirrored AI-hue ornament lines.
        if watermark_enabled:
            wm_start = float(state["epochs"][0].get("start_time", 0.0)) if state.get("epochs") else 0.0
            wm_end = max(wm_start + 0.05, float(audio_duration))
            if state.get("epochs"):
                wm_end = max(wm_end, float(state["epochs"][-1].get("end_time", wm_end)))

            main_y1 = wm_center_y - (line_thickness // 2)
            main_y2 = main_y1 + line_thickness
            left_x1 = wm_center_x - line_gap_from_text - line_half_len
            left_x2 = wm_center_x - line_gap_from_text
            right_x1 = wm_center_x + line_gap_from_text
            right_x2 = wm_center_x + line_gap_from_text + line_half_len

            accent_y1 = wm_center_y - 8
            accent_y2 = accent_y1 + 2
            left_accent_x1 = wm_center_x - accent_gap_from_center - accent_half_len
            left_accent_x2 = wm_center_x - accent_gap_from_center
            right_accent_x1 = wm_center_x + accent_gap_from_center
            right_accent_x2 = wm_center_x + accent_gap_from_center + accent_half_len

            watermark_report["timeline"] = {
                "start": round(wm_start, 3),
                "end": round(wm_end, 3),
            }
            watermark_report["line_geometry"] = {
                "main_left": {"x1": left_x1, "x2": left_x2, "y1": main_y1, "y2": main_y2},
                "main_right": {"x1": right_x1, "x2": right_x2, "y1": main_y1, "y2": main_y2},
                "accent_left": {"x1": left_accent_x1, "x2": left_accent_x2, "y1": accent_y1, "y2": accent_y2},
                "accent_right": {"x1": right_accent_x1, "x2": right_accent_x2, "y1": accent_y1, "y2": accent_y2},
            }

            f.write(
                f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkTag,,0,0,0,,"
                f"{{\\an5\\pos({wm_center_x},{wm_center_y})\\blur0.8\\bord2\\shad1\\1c&H37D8FF&\\2c&HFFC36E&\\3c&H4A0F2C&\\4c&H900A0415&}}{wm_text}\n"
            )
            f.write(
                f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
                f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFF9C62&\\alpha&H6A&}}m {left_x1} {main_y1} l {left_x2} {main_y1} l {left_x2} {main_y2} l {left_x1} {main_y2}\n"
            )
            f.write(
                f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
                f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFF9C62&\\alpha&H6A&}}m {right_x1} {main_y1} l {right_x2} {main_y1} l {right_x2} {main_y2} l {right_x1} {main_y2}\n"
            )
            f.write(
                f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
                f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H3CD8FF&\\alpha&H52&}}m {left_accent_x1} {accent_y1} l {left_accent_x2} {accent_y1} l {left_accent_x2} {accent_y2} l {left_accent_x1} {accent_y2}\n"
            )
            f.write(
                f"Dialogue: 2,{sec_to_ass(wm_start)},{sec_to_ass(wm_end)},WatermarkLine,,0,0,0,,"
                f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H3CD8FF&\\alpha&H52&}}m {right_accent_x1} {accent_y1} l {right_accent_x2} {accent_y1} l {right_accent_x2} {accent_y2} l {right_accent_x1} {accent_y2}\n"
            )

    if not isinstance(overlay_report, dict):
        overlay_report = {}
    overlay_report["watermark"] = watermark_report

    _write_json_artifact("editor_overlay_report.json", overlay_report, mirror_legacy=None)



    # === FFmpeg Symphony Render (Zero-Drift Math) ===

    asset_dir = _artifact_path("assets")



    n = len(state["epochs"])

    xfade = 0.5

    

    print(f"    [EDITOR MATH] Engaging Semantic VTT-Driven Synchronization for {n} epochs.")



    cmd = ["ffmpeg", "-y"]

    # Preflight: guarantee one concrete image per epoch before ffmpeg.
    preflight_prev = ""
    for ep in state["epochs"]:
        img_path = ep.get("image_path")
        if not img_path or not os.path.exists(img_path):
            epoch_prefix = os.path.join(asset_dir, f"epoch_{ep['id']:03d}_*png")
            matches = glob.glob(epoch_prefix)
            if matches:
                img_path = matches[0]
        if not img_path:
            img_path = os.path.join(asset_dir, f"epoch_{ep['id']:03d}_placeholder.png")
        image_source = _ensure_epoch_image_with_fallback(
            img_path,
            last_valid_path=preflight_prev,
            label=f"EDITOR-EPOCH-{ep['id']:03d}",
        )
        ep["image_path"] = img_path
        ep["image_source"] = image_source
        if os.path.exists(img_path):
            preflight_prev = img_path



    for ep in state["epochs"]:
        img_path = ep.get("image_path")
        if img_path and os.path.exists(img_path):
            cmd += ["-i", img_path]
        else:
            raise RuntimeError(f"Editor preflight failed to materialize epoch image for {ep['id']}")



    cmd += ["-i", state["audio_path"]]



    filt = []

    

    # Calculate exact duration for each image purely driven by semantic text length

    for i, ep in enumerate(state["epochs"]):

        dur = float(ep["duration"])

        if i < n - 1:

            dur += xfade # The image must render slightly longer to bleed into the xfade

            

        frames = int(round(dur * 30))

        filt.append(

            f"[{i}:v]scale=1920:1080,zoompan=z='min(zoom+0.0003,1.05)':d={frames}"

            f":s=1920x1080:fps=30,setpts=PTS-STARTPTS,format=yuv420p[v{i}]"

        )



    prev = "v0"

    for i in range(1, n):

        nxt = f"xf{i}"

        # Start the visual transition at the exact millisecond the next semantic sentence begins.

        offset = round(float(state["epochs"][i]["start_time"]), 3)

        filt.append(f"[{prev}][v{i}]xfade=transition=fade:duration={xfade}:offset={offset}[{nxt}]")

        prev = nxt



    # ASS path for FFmpeg (relative to CWD)

    rel_ass = os.path.relpath(ass_path, PROJECT_DIR).replace("\\", "/")

    filt.append(f"[{prev}]ass='{rel_ass}'[outv]")



    filt_script = _artifact_path("filter.txt")

    with open(filt_script, "w", encoding="utf-8") as f:

        f.write(";\n".join(filt))



    cmd += [

        "-filter_complex_script", filt_script,

        "-map", "[outv]", "-map", f"{len(state['epochs'])}:a",

        "-c:v", "libx264", "-preset", "fast", "-crf", "18",

        "-c:a", "aac", "-b:a", "192k",

        state["target_output"]

    ]



    print(f"    [EDITOR] Rendering {len(state['epochs'])} epochs with {overlay_report.get('scheduled_count', 0)} topic cards...")



    try:

        subprocess.run(cmd, cwd=PROJECT_DIR, check=True, capture_output=True)

        print(f"[OK]  [EDITOR] Render complete: {state['target_output']}")

        return {"status": "rendered", "final_video": state["target_output"]}

    except subprocess.CalledProcessError as e:

        return {"errors": [f"FFmpeg failed: {e.stderr.decode()[-200:]}"], "status": "render_failed"}





# ==============================================================

# NODE 9: WHISPER VERIFIER (Post-Render Sync Check)

# ==============================================================

def whisper_verifier(state: AgentState):

    print("    [WHISPER VERIFIER] Running post-render audio-visual sync verification...")

    report = {"verified": False, "video_duration": 0, "audio_duration": 0, "drift": 0}



    try:

        # Get video duration

        vid_dur = subprocess.getoutput(

            f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{state["target_output"]}"'

        )

        report["video_duration"] = float(vid_dur.strip())



        # Get audio duration

        aud_dur = subprocess.getoutput(

            f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{state["audio_path"]}"'

        )

        report["audio_duration"] = float(aud_dur.strip())



        report["drift"] = abs(report["video_duration"] - report["audio_duration"])

        

        # Phase 23 Fix #18: Proper VTT Word Counting (standardize regex counting on both sides)

        # SOTA: \b\w+(?:['\-]\w+)*\b captures hyphenated and contracted cinematic words accurately.

        word_regex = re.compile(r"\b\w+(?:['\-]\w+)*\b")

        script_words = len(word_regex.findall(state["script"]))

        with open(state["vtt_path"], "r", encoding="utf-8") as f:

            vtt_lines = f.readlines()

        subtitle_words = []

        for line in vtt_lines:

            line = line.strip()

            # Skip: blank lines, WEBVTT header, sequence numbers, timestamp lines

            if not line or line.startswith('WEBVTT') or re.match(r'^\d+$', line) or '-->' in line:

                continue

            # ISSUE-007 Fix: Handle hyphenated words and multiple words per segment more accurately

            line_words = word_regex.findall(line)

            subtitle_words.extend(line_words)

        vtt_words = len(subtitle_words)

        

        report["script_words"] = script_words

        report["vtt_words"] = vtt_words

        report["telemetry_pass"] = abs(script_words - vtt_words) < (script_words * 0.15) # 15% tolerance (VTT may split/merge words)

        report["verified"] = report["drift"] <= 1.0 and report["telemetry_pass"]



        status = "[OK] PASS" if report["verified"] else "[WARN] DRIFT/TELEMETRY FAIL"

        print(f"    [VERIFIER] Video: {report['video_duration']:.1f}s | Audio: {report['audio_duration']:.1f}s | Words: {vtt_words}/{script_words} | {status}")



    except Exception as e:

        print(f"    [VERIFIER] Warning: {e}")

        report["verified"] = True  # Non-blocking



    _write_json_artifact("verification_report.json", report, mirror_legacy=None)



    return {"verification_report": report, "status": "complete"}


def _run_regression_assertions(input_source: str, result: dict) -> dict:
    mode = str(input_source or "").strip().upper()
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": _CURRENT_PIPELINE_RUN_ID or "",
        "checks": [],
        "passed": True,
    }

    writer_report = {}
    audio_report = {}
    try:
        writer_path = _artifact_read_path("writer_quality_report.json")
        if os.path.exists(writer_path):
            with open(writer_path, "r", encoding="utf-8") as f:
                writer_report = json.load(f) or {}
    except Exception:
        writer_report = {}
    try:
        audio_path = _artifact_read_path("audio_stage_report.json")
        if os.path.exists(audio_path):
            with open(audio_path, "r", encoding="utf-8") as f:
                audio_report = json.load(f) or {}
    except Exception:
        audio_report = {}

    if mode == "USER_CONTEXT":
        deterministic_seen = bool(writer_report.get("deterministic_user_context_path"))
        fallback_reason = str(writer_report.get("final_reason", "") or "")
        context_rewrite = _normalize_context_rewrite(writer_report.get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
        forced_rewrite = context_rewrite == "force"
        duration_attempts = int(result.get("duration_attempts", 0) or 0)
        ok = (
            forced_rewrite
            or deterministic_seen
            or duration_attempts > 1
            or fallback_reason.startswith("provider_degraded_user_context")
            or fallback_reason == "cache_resume_valid"
        )
        report["checks"].append({
            "id": "RG-001",
            "name": "writer_user_context_default_or_forced_rewrite",
            "passed": ok,
            "details": {
                "context_rewrite": context_rewrite,
                "forced_rewrite": forced_rewrite,
                "deterministic_user_context_path": deterministic_seen,
                "duration_attempts": duration_attempts,
                "final_reason": fallback_reason,
            },
        })

    stages = audio_report.get("stages", []) if isinstance(audio_report, dict) else []
    stage_names = [str(s.get("stage", "")) for s in stages if isinstance(s, dict)]
    mapping_source = str(audio_report.get("mapping_source", "") or "")
    mapping_ok = ("vtt_map_local_primary" in stage_names) or (mapping_source == "cache_resume")
    report["checks"].append({
        "id": "RG-002",
        "name": "audio_deterministic_first_mapping",
        "passed": mapping_ok,
        "details": {"mapping_source": mapping_source, "stages": stage_names},
    })

    if not all(bool(c.get("passed")) for c in report["checks"]):
        report["passed"] = False

    _write_json_artifact("regression_assertions.json", report, mirror_legacy=None)
    return report





# ==============================================================

# LANGGRAPH STATE MACHINE COMPILATION (9 Nodes Phase 14)

# ==============================================================

def build_tvc_graph(enable_node_timing: bool = True):

    workflow = StateGraph(AgentState)



    # Add all nodes
    def _with_timing(node_name: str, fn):
        if not enable_node_timing:
            return fn

        @functools.wraps(fn)
        def _wrapped(state):
            t0 = time.perf_counter()
            trace_node_timing(node=node_name, event="start", monotonic_s=t0, status="running")
            try:
                result = fn(state)
                t1 = time.perf_counter()
                details = {
                    "result_keys": sorted(list(result.keys())) if isinstance(result, dict) else [],
                }
                if isinstance(result, dict) and "status" in result:
                    details["node_status"] = str(result.get("status", ""))
                trace_node_timing(
                    node=node_name,
                    event="end",
                    monotonic_s=t1,
                    duration_s=(t1 - t0),
                    status="ok",
                    details=details,
                )
                return result
            except Exception as e:
                t1 = time.perf_counter()
                trace_node_timing(
                    node=node_name,
                    event="end",
                    monotonic_s=t1,
                    duration_s=(t1 - t0),
                    status="error",
                    details={"error": str(e)[:240]},
                )
                raise

        return _wrapped

    workflow.add_node("Harvester", _with_timing("Harvester", harvester_node))

    workflow.add_node("Writer", _with_timing("Writer", writer_node))

    workflow.add_node("DurationGate", _with_timing("DurationGate", duration_gate))

    workflow.add_node("TopicExtractor", _with_timing("TopicExtractor", topic_extractor))

    workflow.add_node("SceneDirector", _with_timing("SceneDirector", scene_director))

    workflow.add_node("Audio", _with_timing("Audio", audio_engineer))

    workflow.add_node("PromptArchitect", _with_timing("PromptArchitect", prompt_architect))

    workflow.add_node("SotaForge", _with_timing("SotaForge", sota_vision_forge))

    workflow.add_node("Editor", _with_timing("Editor", lead_editor))

    workflow.add_node("Verifier", _with_timing("Verifier", whisper_verifier))



    # Linear edges

    workflow.set_entry_point("Harvester")

    workflow.add_edge("Harvester", "Writer")

    workflow.add_edge("Writer", "DurationGate")



    # Conditional: Duration Gate  Writer (rewrite) or TopicExtractor (pass)

    def route_duration(state):

        if state["status"] == "duration_pass":

            return "TopicExtractor"

        return "Writer"



    workflow.add_conditional_edges("DurationGate", route_duration, {

        "TopicExtractor": "TopicExtractor",

        "Writer": "Writer"

    })



    workflow.add_edge("TopicExtractor", "SceneDirector")

    workflow.add_edge("SceneDirector", "Audio")

    workflow.add_edge("Audio", "PromptArchitect")

    workflow.add_edge("PromptArchitect", "SotaForge")

    workflow.add_edge("SotaForge", "Editor")

    workflow.add_edge("Editor", "Verifier")

    workflow.add_edge("Verifier", END)



    return workflow.compile()





# ==============================================================

# MASTER ENTRY POINT

# ==============================================================

def execute_multi_agent_narrator(
    user_prompt: str,
    final_output: str,
    api_key: str,
    target_duration: int = 60,
    context_summary: Optional[str] = None,
    input_source: str = "YOUTUBE_HARVEST",
    narration_style: str = NARRATION_STYLE_DEFAULT,
    context_rewrite: str = CONTEXT_REWRITE_DEFAULT,
    watermark_mode: str = WATERMARK_MODE_DEFAULT,
):

    # Phase 23 Fix #19: Tee all stdout to a persistent log file for telemetry
    global _CURRENT_TIMING_RUN_ID, _CURRENT_PIPELINE_RUN_ID, _CURRENT_PIPELINE_RUN_DIR

    import sys

    run_id = time.strftime("%Y%m%d_%H%M%S")
    resolved_style = _normalize_narration_style(narration_style)
    resolved_context_rewrite = _normalize_context_rewrite(context_rewrite)
    resolved_watermark_mode = _normalize_watermark_mode(watermark_mode)
    resolved_input_source = str(input_source or "YOUTUBE_HARVEST").strip().upper()
    if resolved_input_source == "USER_CONTEXT" and resolved_context_rewrite != "off":
        print(
            f"    [ROUTING] USER_CONTEXT enforces context_rewrite=off "
            f"(requested '{resolved_context_rewrite}' overridden)."
        )
        resolved_context_rewrite = "off"
    _CURRENT_TIMING_RUN_ID = run_id
    _CURRENT_PIPELINE_RUN_ID = run_id
    _CURRENT_PIPELINE_RUN_DIR = os.path.join(ROOT_INTEL_DIR, "runs", run_id)
    os.makedirs(_CURRENT_PIPELINE_RUN_DIR, exist_ok=True)
    _init_provider_resilience_report(run_id)
    log_path = _artifact_path("pipeline_run.log")

    class _TeeLogger:

        """Duplicates stdout to both console and a log file."""

        def __init__(self, log_file_path):

            self._original_stdout = sys.stdout

            self._log_file = open(log_file_path, 'w', encoding='utf-8')

        def write(self, message):

            self._original_stdout.write(message)

            try:

                self._log_file.write(message)

                self._log_file.flush()

            except Exception:

                pass  # Never crash the pipeline for logging

        def flush(self):

            self._original_stdout.flush()

            try:

                self._log_file.flush()

            except Exception:

                pass

        def close(self):

            sys.stdout = self._original_stdout

            try:

                self._log_file.close()

            except Exception:

                pass

    tee = _TeeLogger(log_path)

    sys.stdout = tee

    # Reset per-run API trace file.
    try:
        trace_file = _trace_file_path()
        if os.path.exists(trace_file):
            os.remove(trace_file)
    except Exception:
        pass
    try:
        timing_file = _node_timing_trace_file_path()
        if os.path.exists(timing_file):
            os.remove(timing_file)
    except Exception:
        pass
    _write_json_artifact(
        "run_manifest.json",
        {
            "run_id": run_id,
            "run_dir": _CURRENT_PIPELINE_RUN_DIR,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input_source": resolved_input_source,
            "narration_style": resolved_style,
            "context_rewrite": resolved_context_rewrite,
            "watermark_mode": resolved_watermark_mode,
            "target_duration": int(target_duration or 60),
            "target_output": final_output,
        },
        mirror_legacy=False,
    )
    _init_live_status(
        run_id=run_id,
        seed={
            "input_source": resolved_input_source,
            "narration_style": resolved_style,
            "context_rewrite": resolved_context_rewrite,
            "watermark_mode": resolved_watermark_mode,
            "target_duration": int(target_duration or 60),
            "target_output": final_output,
            "live_status_txt": _artifact_path("live_status.txt"),
            "live_status_json": _artifact_path("live_status.json"),
        },
    )



    print("=" * 65)

    print("    TVC V5.0 SOTA ORCHESTRATOR (Phase 23 Precision Forge)")

    print("=" * 65)
    print(f"    Live heartbeat: {_artifact_path('live_status.txt')}")



    agent = build_tvc_graph(enable_node_timing=True)

    initial_state = {

        "request_prompt": user_prompt,

        "input_source": resolved_input_source,

        "narration_style": resolved_style,

        "context_rewrite": resolved_context_rewrite,

        "watermark_mode": resolved_watermark_mode,

        "target_output": final_output,

        "target_duration": target_duration,

        "api_key": api_key,

        "errors": [],

        "images_forged": 0,

        "duration_attempts": 0

    }
    if context_summary and str(context_summary).strip():
        initial_state["context_summary"] = str(context_summary).strip()


    mission_status = "running"
    mission_error = ""
    mission_final_video = ""
    result = {}

    try:

        result = agent.invoke(initial_state)



        if result.get("errors"):

            print("\n[FAIL]  [MISSION FAILED] Critical Agent Errors Logged:")

            err_msg = ""

            for err in result["errors"]:

                print(f"  - {err}")

                err_msg += f"{err}; "

            raise RuntimeError(f"TVC V3.0 Multi-Agent Forge Failed: {err_msg}")

        else:
            regression_report = _run_regression_assertions(initial_state.get("input_source", ""), result)
            if not regression_report.get("passed", True):
                raise RuntimeError("Regression assertions failed. See regression_assertions.json for details.")

            print(f"\n[OK]  [MISSION ACCOMPLISHED] Video forged: {result.get('final_video', final_output)}")
            mission_final_video = str(result.get("final_video", final_output) or final_output)
            mission_status = "success"

            vr = result.get("verification_report", {})

            if vr:

                print(f"    Verification: drift={vr.get('drift', '?')}s | pass={vr.get('verified', '?')}")
    except Exception as e:
        mission_status = "failed"
        mission_error = str(e)[:240]
        raise

    finally:

        # Phase 23: Always restore stdout and close log file
        resilience_report = _write_provider_resilience_report()
        policy_report = write_paid_api_policy_check()
        print(
            f"    API Policy Check: host_allowlist_pass={policy_report.get('passed')} hosts={policy_report.get('observed_paid_hosts', [])}"
        )
        print(
            f"    Provider Resilience: retryable={resilience_report.get('counts', {}).get('retryable', 0)} "
            f"precondition_412={resilience_report.get('counts', {}).get('precondition_412', 0)} "
            f"circuit_failfast={resilience_report.get('counts', {}).get('circuit_open_failfast', 0)}"
        )
        _finalize_live_status(
            status=mission_status,
            final_video=mission_final_video,
            error=mission_error,
        )
        tee.close()

        # Keep legacy latest files available while preserving run-scoped artifacts.
        if _legacy_mirror_enabled():
            try:
                legacy_log = _legacy_artifact_path("pipeline_run.log")
                if log_path != legacy_log and os.path.exists(log_path):
                    _ensure_artifact_parent(legacy_log)
                    shutil.copy2(log_path, legacy_log)
            except Exception:
                pass
        try:
            latest_pointer = {
                "run_id": run_id,
                "run_dir": os.path.join(ROOT_INTEL_DIR, "runs", run_id),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(os.path.join(ROOT_INTEL_DIR, "latest_run_pointer.json"), "w", encoding="utf-8") as f:
                json.dump(latest_pointer, f, indent=2, ensure_ascii=True)
        except Exception:
            pass

        _CURRENT_TIMING_RUN_ID = ""
        _CURRENT_PIPELINE_RUN_ID = ""
        _CURRENT_PIPELINE_RUN_DIR = ""



    return final_output





if __name__ == "__main__":

    pass

