from tvc_vault import get_secret
from tvc_duration import (
    DURATION_MODE_AUTO,
    DURATION_MODE_MANUAL,
    estimate_duration_seconds,
    resolve_duration_plan,
)
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
from tvc_voice_registry import DEFAULT_VOICE_PRESET_ID, resolve_voice_preset
from tvc_nodes.audio_engineer import run_audio_engineer
from tvc_nodes.contracts import (
    AudioEngineerInput,
    DurationGateInput,
    LeadEditorInput,
    PromptArchitectInput,
    SceneDirectorInput,
    SotaForgeInput,
    TopicExtractorInput,
    VerifierInput,
    WriterInput,
)
from tvc_nodes.duration_gate import run_duration_gate
from tvc_nodes.lead_editor import run_lead_editor
from tvc_nodes.pronunciation import resolve_pronunciation
from tvc_nodes.prompt_architect import run_prompt_architect
from tvc_nodes.scene_director import run_scene_director
from tvc_nodes.sota_forge import run_sota_forge
from tvc_nodes.services import (
    AudioEngineerServices,
    ArtifactStore,
    DurationGateServices,
    LeadEditorServices,
    ManifestStore,
    PromptArchitectServices,
    SceneDirectorServices,
    SotaForgeServices,
    TopicExtractorServices,
    VerifierServices,
    WriterServices,
)
from tvc_nodes.topic_extractor import run_topic_extractor
from tvc_nodes.verifier import run_verifier
from tvc_nodes.writer import run_writer


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


def _root_artifact_path(name: str) -> str:
    return os.path.join(ROOT_INTEL_DIR, name)


def _write_root_text_artifact(name: str, content: str, encoding: str = "utf-8") -> str:
    target = _root_artifact_path(name)
    _ensure_artifact_parent(target)
    with open(target, "w", encoding=encoding) as f:
        f.write(content)
    return target


def _write_root_json_artifact(name: str, payload: Any) -> str:
    return _write_root_text_artifact(name, json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_active_run_pointer(run_id: str, status: str) -> None:
    try:
        payload = {
            "run_id": str(run_id or ""),
            "run_dir": os.path.join(ROOT_INTEL_DIR, "runs", str(run_id or "")),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": str(status or ""),
        }
        _write_root_json_artifact("active_run_pointer.json", payload)
    except Exception:
        pass


def _write_latest_run_pointer(run_id: str) -> None:
    try:
        payload = {
            "run_id": str(run_id or ""),
            "run_dir": os.path.join(ROOT_INTEL_DIR, "runs", str(run_id or "")),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _write_root_json_artifact("latest_run_pointer.json", payload)
    except Exception:
        pass


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


def _append_jsonl_artifact(name: str, payload: Dict[str, Any], mirror_legacy: Optional[bool] = None) -> str:
    target = _artifact_path(name)
    _ensure_artifact_parent(target)
    line = json.dumps(payload, ensure_ascii=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if mirror_legacy is None:
        mirror_legacy = _legacy_mirror_enabled()
    if mirror_legacy:
        legacy = _legacy_artifact_path(name)
        if legacy != target:
            _ensure_artifact_parent(legacy)
            with open(legacy, "a", encoding="utf-8") as f:
                f.write(line + "\n")
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
        "message": str(message or "")[:1200],
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
        active_contribution = 0.35
        raw_ratio = status_obj.get("current_node_progress_ratio")
        try:
            ratio = max(0.0, min(1.0, float(raw_ratio)))
        except Exception:
            ratio = None
        if ratio is not None:
            active_contribution = 0.35 + (0.60 * ratio)
        progress_nodes += active_contribution
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
        f"node_progress_ratio: {status_obj.get('current_node_progress_ratio')}",
        f"node_units_completed: {status_obj.get('current_node_units_completed')}",
        f"node_units_total: {status_obj.get('current_node_units_total')}",
        f"node_units_label: {status_obj.get('current_node_units_label', '')}",
        f"node_detail: {status_obj.get('current_node_detail', '')}",
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
        _write_json_artifact("live_status.json", status_obj, mirror_legacy=True)
        _write_text_artifact("live_status.txt", "\n".join(lines) + "\n", mirror_legacy=True)
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
        "current_node_progress_ratio": None,
        "current_node_units_completed": None,
        "current_node_units_total": None,
        "current_node_units_label": "",
        "current_node_detail": "",
        "seed_is_initial_snapshot": True,
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


def _clear_live_status_node_subprogress() -> Dict[str, Any]:
    return {
        "current_node_progress_ratio": None,
        "current_node_units_completed": None,
        "current_node_units_total": None,
        "current_node_units_label": "",
        "current_node_detail": "",
    }


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
    _LIVE_STATUS.update(_clear_live_status_node_subprogress())
    _write_live_status(force=True)


# ==============================================================

# PHASE 20: API KEYS & IMAGE GENERATION MODE

# ==============================================================


# SEC-001: Moved to vault (D:\AI\API\Secrets\runware_sota.json)
_FIREWORKS_API_KEY_CACHE = ""
_BFL_IMAGE_API_KEY_CACHE = ""


def _get_fireworks_api_key() -> str:
    global _FIREWORKS_API_KEY_CACHE
    if _FIREWORKS_API_KEY_CACHE:
        return _FIREWORKS_API_KEY_CACHE
    _FIREWORKS_API_KEY_CACHE = get_secret("key_HGmChvaB")
    return _FIREWORKS_API_KEY_CACHE


def _get_bfl_image_api_key() -> str:
    global _BFL_IMAGE_API_KEY_CACHE
    if _BFL_IMAGE_API_KEY_CACHE:
        return _BFL_IMAGE_API_KEY_CACHE
    _BFL_IMAGE_API_KEY_CACHE = get_secret("BLF_FLUX2PRO")
    return _BFL_IMAGE_API_KEY_CACHE

RUNWARE_FLUX_MODEL = "runware:100@1"  # FLUX.1 Schnell (Verified SOTA)

RUNWARE_ENDPOINT = "https://api.runware.ai/v1"

IMAGE_GEN_MODE = "BFL"  # Options: "BFL" or legacy


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


def _estimate_prompt_chars(contents) -> int:
    if isinstance(contents, str):
        return len(contents)
    if isinstance(contents, list):
        total = 0
        for part in contents:
            if isinstance(part, str):
                total += len(part)
            elif isinstance(part, dict):
                if part.get("type") == "text":
                    total += len(str(part.get("text", "") or ""))
                elif isinstance(part.get("text"), str):
                    total += len(str(part.get("text", "") or ""))
        return total
    return len(str(contents or ""))


def trace_api_call(
    node: str,
    endpoint_url: str,
    model: str,
    prompt_template_id: str,
    prompt_preview: str,
    call_type: str,
    prompt_char_count: int = 0,
):
    call_id = uuid.uuid4().hex[:12]
    try:
        os.makedirs(_active_intel_dir(), exist_ok=True)
        host = urlparse(endpoint_url).netloc or endpoint_url
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "request",
            "call_id": call_id,
            "node": node or "Unknown",
            "call_type": call_type,
            "endpoint_url": endpoint_url,
            "endpoint_host": host,
            "model": model,
            "prompt_template_id": prompt_template_id or "UNSPECIFIED",
            "prompt_preview": (prompt_preview or "")[:280],
            "prompt_char_count": int(max(0, prompt_char_count or 0)),
        }
        _append_jsonl_artifact("api_call_trace.jsonl", entry, mirror_legacy=None)
        if _LIVE_STATUS:
            _update_live_status({
                "last_api_call": {
                    "call_id": call_id,
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
    return call_id


def trace_api_error(
    call_id: str,
    node: str,
    endpoint_url: str,
    model: str,
    prompt_template_id: str,
    call_type: str,
    error_text: str,
):
    try:
        err = str(error_text or "")
        host = urlparse(endpoint_url).netloc or endpoint_url
        host_low = str(host or "").lower()
        if host_low == "api.fireworks.ai":
            error_class = _classify_fireworks_error(err)
        elif host_low == "api.bfl.ai" or host_low.endswith(".bfl.ai"):
            error_class = _classify_bfl_error(err)
        else:
            error_class = "error"
        status_match = re.search(r"\b(4\d\d|5\d\d)\b", err)
        http_status = int(status_match.group(1)) if status_match else None
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "error",
            "call_id": str(call_id or ""),
            "node": node or "Unknown",
            "call_type": call_type or "",
            "endpoint_url": endpoint_url,
            "endpoint_host": host,
            "model": model,
            "prompt_template_id": prompt_template_id or "UNSPECIFIED",
            "error_class": error_class,
            "http_status": http_status,
            "error_excerpt": err[:1200],
        }
        _append_jsonl_artifact("api_call_trace.jsonl", entry, mirror_legacy=None)
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
                live_payload = {
                    "current_node": node_name,
                    "current_node_event": "start",
                }
                live_payload.update(_clear_live_status_node_subprogress())
                _update_live_status(live_payload, force=True)
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

    def _host_allowed(host: str) -> bool:
        h = str(host or "").strip().lower()
        if not h:
            return False
        if h == "api.fireworks.ai":
            return True
        if h == "api.bfl.ai" or h.endswith(".bfl.ai"):
            return True
        if "bfldelivery" in h and h.endswith(".blob.core.windows.net"):
            return True
        return False

    disallowed_hosts = sorted([h for h in observed_hosts if not _host_allowed(h)])
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "policy": "paid_model_api_host_allowlist",
        "allowed_paid_hosts": [
            "api.fireworks.ai",
            "api.bfl.ai",
            "*.bfl.ai",
            "*bfldelivery*.blob.core.windows.net",
        ],
        "observed_paid_hosts": sorted(observed_hosts),
        "disallowed_paid_hosts": disallowed_hosts,
        "passed": len(disallowed_hosts) == 0,
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
    endpoint_url = "https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-1-schnell-fp8/text_to_image"
    model_name = "accounts/fireworks/models/flux-1-schnell-fp8"
    call_id = ""
    headers = {
        "Authorization": f"Bearer {_get_fireworks_api_key()}",
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
        call_id = trace_api_call(
            node=trace_node,
            endpoint_url=endpoint_url,
            model=model_name,
            prompt_template_id=prompt_template_id,
            prompt_preview=_extract_prompt_preview(prompt),
            call_type="image_generation",
            prompt_char_count=len(str(prompt or "")),
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
        trace_api_error(
            call_id=call_id,
            node=trace_node,
            endpoint_url=endpoint_url,
            model=model_name,
            prompt_template_id=prompt_template_id,
            call_type="image_generation",
            error_text=err_msg,
        )
        print(f"    [FIREWORKS IMAGE] API Error: {err_msg[:250]}")
        raise RuntimeError(err_msg) from e


def _bfl_terminal_status(status_text: str) -> str:
    low = str(status_text or "").strip().lower()
    if low in {"ready", "done", "completed", "complete"}:
        return "ready"
    if any(k in low for k in ["error", "failed", "failure"]):
        return "failed"
    if any(k in low for k in ["moderated", "blocked", "rejected"]):
        return "moderated"
    if any(k in low for k in ["pending", "running", "processing", "queued", "requesting"]):
        return "pending"
    return "unknown"


def _adaptive_bfl_poll_delay(current_delay_s: float) -> float:
    """
    Deterministic backoff to reduce noisy poll traffic while preserving readiness checks.
    """
    base = max(0.6, float(current_delay_s or 0.0))
    return min(6.0, round(base * 1.3, 3))


def bfl_generate_image(
    prompt: str,
    width: int = 1920,
    height: int = 1088,
    output_path: str = "",
    prompt_template_id: str = "UNSPECIFIED",
    trace_node: str = "Unknown",
) -> bool:
    submit_url = "https://api.bfl.ai/v1/flux-2-pro"
    model_name = "bfl:flux-2-pro"
    submit_call_id = ""
    headers = {
        "x-key": str(_get_bfl_image_api_key() or ""),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "prompt": str(prompt or ""),
        "width": int(width),
        "height": int(height),
    }
    try:
        submit_call_id = trace_api_call(
            node=trace_node,
            endpoint_url=submit_url,
            model=model_name,
            prompt_template_id=prompt_template_id,
            prompt_preview=_extract_prompt_preview(prompt),
            call_type="image_generation_submit",
            prompt_char_count=len(str(prompt or "")),
        )
        submit_resp = _requests.post(
            submit_url, headers=headers, json=payload, timeout=60
        )
        submit_resp.raise_for_status()
        submit_data = submit_resp.json() if submit_resp.content else {}
        poll_url = str(submit_data.get("polling_url", "") or "").strip()
        if not poll_url:
            task_id = str(submit_data.get("id", "") or "").strip()
            if task_id:
                poll_url = f"https://api.bfl.ai/v1/get_result?id={task_id}"
        if not poll_url:
            raise RuntimeError("BFL submit response missing polling_url/id")

        start = time.time()
        timeout_s = 180.0
        poll_delay_s = 0.9
        last_status = ""
        while (time.time() - start) < timeout_s:
            poll_call_id = trace_api_call(
                node=trace_node,
                endpoint_url=poll_url,
                model=model_name,
                prompt_template_id=f"{prompt_template_id}::poll",
                prompt_preview="bfl_poll",
                call_type="image_generation_poll",
                prompt_char_count=0,
            )
            try:
                poll_resp = _requests.get(poll_url, headers={"x-key": str(_get_bfl_image_api_key() or "")}, timeout=45)
                poll_resp.raise_for_status()
            except Exception as poll_err:
                poll_err_txt = str(poll_err)
                if hasattr(poll_err, "response") and poll_err.response is not None:
                    poll_err_txt += f". Response: {poll_err.response.text}"
                trace_api_error(
                    call_id=poll_call_id,
                    node=trace_node,
                    endpoint_url=poll_url,
                    model=model_name,
                    prompt_template_id=f"{prompt_template_id}::poll",
                    call_type="image_generation_poll",
                    error_text=poll_err_txt,
                )
                raise RuntimeError(poll_err_txt) from poll_err

            poll_data = poll_resp.json() if poll_resp.content else {}
            last_status = str(poll_data.get("status", "") or "")
            terminal = _bfl_terminal_status(last_status)
            if terminal == "pending" or terminal == "unknown":
                elapsed_s = max(0.0, time.time() - start)
                remaining_s = max(0.0, timeout_s - elapsed_s)
                sleep_s = min(poll_delay_s, remaining_s)
                if sleep_s > 0:
                    time.sleep(sleep_s)
                poll_delay_s = _adaptive_bfl_poll_delay(poll_delay_s)
                continue
            if terminal == "moderated":
                raise RuntimeError(f"BFL image request moderated: status={last_status}")
            if terminal == "failed":
                err_obj = poll_data.get("error") if isinstance(poll_data, dict) else None
                raise RuntimeError(f"BFL image generation failed: status={last_status} error={str(err_obj)[:220]}")
            if terminal == "ready":
                result_obj = poll_data.get("result", {}) if isinstance(poll_data, dict) else {}
                sample_url = ""
                if isinstance(result_obj, dict):
                    sample_url = str(result_obj.get("sample", "") or "").strip()
                if not sample_url:
                    sample_url = str(poll_data.get("sample", "") or "").strip()
                if not sample_url:
                    raise RuntimeError("BFL ready response missing result.sample URL")
                sample_call_id = trace_api_call(
                    node=trace_node,
                    endpoint_url=sample_url,
                    model=model_name,
                    prompt_template_id=f"{prompt_template_id}::download",
                    prompt_preview="bfl_sample_download",
                    call_type="image_generation_download",
                    prompt_char_count=0,
                )
                try:
                    sample_resp = _requests.get(sample_url, timeout=120)
                    sample_resp.raise_for_status()
                except Exception as sample_err:
                    sample_err_txt = str(sample_err)
                    if hasattr(sample_err, "response") and sample_err.response is not None:
                        sample_err_txt += f". Response: {sample_err.response.text}"
                    trace_api_error(
                        call_id=sample_call_id,
                        node=trace_node,
                        endpoint_url=sample_url,
                        model=model_name,
                        prompt_template_id=f"{prompt_template_id}::download",
                        call_type="image_generation_download",
                        error_text=sample_err_txt,
                    )
                    raise RuntimeError(sample_err_txt) from sample_err
                _ensure_artifact_parent(output_path)
                with open(output_path, "wb") as f:
                    f.write(sample_resp.content)
                print(f"    [BFL IMAGE] Generated image: {output_path}")
                return True

        raise RuntimeError(f"BFL image polling timeout after {int(timeout_s)}s (last_status={last_status})")
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            err_msg += f". Response: {e.response.text}"
        trace_api_error(
            call_id=submit_call_id,
            node=trace_node,
            endpoint_url=submit_url,
            model=model_name,
            prompt_template_id=prompt_template_id,
            call_type="image_generation_submit",
            error_text=err_msg,
        )
        print(f"    [BFL IMAGE] API Error: {err_msg[:250]}")
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
    "bfl_image":    {"base": 2.0, "max_delay": 30, "max_retries": 4},

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


def _classify_bfl_error(err_text: str) -> str:
    low = str(err_text or "").lower()
    if any(k in low for k in ["429", "rate", "throttl", "503", "502", "504", "408", "timeout", "connection", "unavailable", "network"]):
        return "retryable"
    if "400" in low or "422" in low or "invalid" in low or "bad request" in low:
        return "invalid_request_400"
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
    endpoint_url = "https://api.fireworks.ai/inference/v1/chat/completions"
    call_id = ""
    if api_key is None:
        api_key = _get_fireworks_api_key()
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

    try:
        call_id = trace_api_call(
            node=trace_node,
            endpoint_url=endpoint_url,
            model=model,
            prompt_template_id=prompt_template_id,
            prompt_preview=_extract_prompt_preview(contents),
            call_type="chat_completion",
            prompt_char_count=_estimate_prompt_chars(contents),
        )
        resp = _requests.post(endpoint_url,
                              headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return DummyRes(data["choices"][0]["message"]["content"])
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            err_msg += f". Response: {e.response.text}"
        trace_api_error(
            call_id=call_id,
            node=trace_node,
            endpoint_url=endpoint_url,
            model=model,
            prompt_template_id=prompt_template_id,
            call_type="chat_completion",
            error_text=err_msg,
        )
        raise

# FIREWORKS_LLM_INJECTED


def smart_retry(fn, endpoint="default", *args, **kwargs):

    cfg = RETRY_CONFIGS.get(endpoint, RETRY_CONFIGS["default"])
    last_exception = None
    call_kwargs = dict(kwargs or {})
    endpoint_name = str(endpoint or "")
    fireworks_endpoint = endpoint_name.startswith("fireworks_")
    bfl_endpoint = endpoint_name.startswith("bfl_")
    tracked_provider_endpoint = fireworks_endpoint or bfl_endpoint
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
            if tracked_provider_endpoint:
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

            if tracked_provider_endpoint:
                category = _classify_fireworks_error(err_low) if fireworks_endpoint else _classify_bfl_error(err_low)
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
WATERMARK_FONT_SIZE = 14
UNIFIED_NEGATIVE_PROMPT = (
    "ABSOLUTE NEGATIVE PROMPT: No text, no words, no letters, no typography, "
    "no watermarks, no distorted objects, no figure morphing, no face morphing."
)

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


def _duration_meta_from_state(state: Any, actual_audio_duration: Any = None) -> Dict[str, Any]:
    payload = dict(state or {})
    input_source = str(payload.get("input_source", "") or "YOUTUBE_HARVEST").strip().upper()
    context_rewrite = _normalize_context_rewrite(payload.get("context_rewrite", CONTEXT_REWRITE_DEFAULT))
    narration_style = _normalize_narration_style(payload.get("narration_style", NARRATION_STYLE_DEFAULT))
    context_text = str(
        payload.get("context_summary")
        or payload.get("script")
        or payload.get("request_prompt")
        or ""
    ).strip()
    duration_mode = str(payload.get("duration_mode", "") or "").strip().lower()
    requested_target = payload.get("requested_target_duration_seconds", None)
    planning_duration = payload.get("target_duration", None)
    estimated_duration = payload.get("estimated_duration_seconds", None)
    actual_duration = actual_audio_duration if actual_audio_duration is not None else payload.get("actual_audio_duration_seconds", None)

    requested_for_plan = requested_target
    if requested_for_plan is None and duration_mode != DURATION_MODE_AUTO:
        requested_for_plan = planning_duration

    base_plan = resolve_duration_plan(
        input_source=input_source,
        context_rewrite=context_rewrite,
        narration_style=narration_style,
        context_text=context_text,
        requested_target_duration=requested_for_plan,
        actual_audio_duration=actual_duration,
    )
    if duration_mode not in {DURATION_MODE_AUTO, DURATION_MODE_MANUAL}:
        duration_mode = str(base_plan.get("duration_mode", DURATION_MODE_MANUAL))
    if requested_target is None and duration_mode == DURATION_MODE_MANUAL and planning_duration is not None:
        try:
            requested_target = int(planning_duration)
        except Exception:
            requested_target = base_plan.get("requested_target_duration_seconds")
    elif requested_target is None:
        requested_target = base_plan.get("requested_target_duration_seconds")
    if estimated_duration is None:
        estimated_duration = base_plan.get("estimated_duration_seconds")
    if planning_duration is None:
        planning_duration = base_plan.get("effective_planning_duration_seconds")
    else:
        try:
            planning_duration = int(planning_duration)
        except Exception:
            planning_duration = base_plan.get("effective_planning_duration_seconds")

    return {
        "duration_mode": duration_mode,
        "requested_target_duration_seconds": requested_target,
        "estimated_duration_seconds": estimated_duration,
        "effective_planning_duration_seconds": int(planning_duration or 60),
        "actual_audio_duration_seconds": base_plan.get("actual_audio_duration_seconds"),
    }


def _update_run_manifest_duration_fields(duration_meta: Dict[str, Any]):
    manifest_path = _artifact_path("run_manifest.json")
    if not os.path.exists(manifest_path):
        return
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh) or {}
    except Exception:
        return
    payload["duration_mode"] = duration_meta.get("duration_mode")
    payload["requested_target_duration_seconds"] = duration_meta.get("requested_target_duration_seconds")
    payload["estimated_duration_seconds"] = duration_meta.get("estimated_duration_seconds")
    payload["effective_planning_duration_seconds"] = duration_meta.get("effective_planning_duration_seconds")
    payload["actual_audio_duration_seconds"] = duration_meta.get("actual_audio_duration_seconds")
    if payload.get("duration_mode") == DURATION_MODE_MANUAL:
        payload["target_duration"] = duration_meta.get("effective_planning_duration_seconds")
    _write_json_artifact("run_manifest.json", payload, mirror_legacy=False)


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
    voice_preset: str

    target_output: str

    target_duration: Optional[int]  # effective planning duration in seconds
    duration_mode: str
    requested_target_duration_seconds: Optional[int]
    estimated_duration_seconds: Optional[int]
    actual_audio_duration_seconds: Optional[float]

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

def _build_writer_services() -> WriterServices:
    return WriterServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        manifest=ManifestStore(
            load=get_state_manifest,
            save=save_state_manifest,
        ),
        smart_retry=smart_retry,
        fireworks_chat_completion=fireworks_chat_completion,
        generate_content_config=types.GenerateContentConfig,
        duration_meta_from_state=_duration_meta_from_state,
        normalize_narration_style=_normalize_narration_style,
        normalize_context_rewrite=_normalize_context_rewrite,
        is_deterministic_user_context_mode=_is_deterministic_user_context_mode,
        narration_profile=_narration_profile,
        apply_cpp=apply_cpp,
        sanitize_tts_script=_sanitize_tts_script,
        clean_transcript_text=_clean_transcript_text,
        word_token_set=_word_token_set,
        meaningful_terms=_meaningful_terms,
        get_hash=get_hash,
        getenv=os.getenv,
        write_text_artifact=_write_text_artifact,
        narration_style_default=NARRATION_STYLE_DEFAULT,
    )


def writer_node(state: AgentState):

    print("[WRITE]  [WRITER] Synthesizing duration-aware script with real CPP...")
    node_input = WriterInput(
        request_prompt=str(state.get("request_prompt", "") or ""),
        context_summary=str(state.get("context_summary", "") or ""),
        harvested_intelligence=str(state.get("harvested_intelligence", "") or ""),
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
        narration_style=str(state.get("narration_style", NARRATION_STYLE_DEFAULT) or NARRATION_STYLE_DEFAULT),
        status=str(state.get("status", "") or ""),
        duration_attempts=int(state.get("duration_attempts", 0) or 0),
        duration_mode=str(state.get("duration_mode", "manual") or "manual"),
        requested_target_duration_seconds=state.get("requested_target_duration_seconds"),
        estimated_duration_seconds=state.get("estimated_duration_seconds"),
        target_duration=state.get("target_duration"),
        actual_audio_duration_seconds=state.get("actual_audio_duration_seconds"),
    )
    result = run_writer(node_input, _build_writer_services())
    return result.to_state_update()


def _build_duration_gate_services() -> DurationGateServices:
    return DurationGateServices(
        normalize_context_rewrite=_normalize_context_rewrite,
        duration_meta_from_state=_duration_meta_from_state,
        write_text_artifact=_write_text_artifact,
    )


def duration_gate(state: AgentState):
    node_input = DurationGateInput(
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
        script=str(state.get("script", "") or ""),
        duration_attempts=int(state.get("duration_attempts", 0) or 0),
        duration_mode=str(state.get("duration_mode", "manual") or "manual"),
        requested_target_duration_seconds=state.get("requested_target_duration_seconds"),
        estimated_duration_seconds=state.get("estimated_duration_seconds"),
        target_duration=state.get("target_duration"),
        actual_audio_duration_seconds=state.get("actual_audio_duration_seconds"),
    )
    result = run_duration_gate(node_input, _build_duration_gate_services())
    return result.to_state_update()


# ==============================================================

# NODE 4: TOPIC EXTRACTOR (Headline Callouts)

# ==============================================================

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


def _build_topic_extractor_services() -> TopicExtractorServices:
    return TopicExtractorServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        manifest=ManifestStore(
            load=get_state_manifest,
            save=save_state_manifest,
        ),
        smart_retry=smart_retry,
        fireworks_chat_completion=fireworks_chat_completion,
        generate_content_config=types.GenerateContentConfig,
        is_deterministic_user_context_mode=_is_deterministic_user_context_mode,
        get_hash=get_hash,
        json_repair=sota_json_repair,
    )


def topic_extractor(state: AgentState):

    print("    [TOPIC EXTRACTOR] Extracting on-screen topic callouts...")
    node_input = TopicExtractorInput(
        script=str(state.get("script", "") or ""),
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
    )
    result = run_topic_extractor(node_input, _build_topic_extractor_services())
    return result.to_state_update()



# ==============================================================

# NODE 5: SCENE DIRECTOR (Semantic Visual Segmentation - Phase 18)

# ==============================================================

def _update_scene_audio_prompt_report(node_name: str, payload: dict):
    report_file = _artifact_path("scene_audio_prompt_report.json")
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": str(_CURRENT_PIPELINE_RUN_ID or ""),
        "nodes": {},
    }
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
    report["run_id"] = str(_CURRENT_PIPELINE_RUN_ID or report.get("run_id", "") or "")
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


def _summarize_cpp_alignment(base_text: str, candidate_text: str) -> Dict[str, float]:
    base = _word_token_set(base_text)
    cand = _word_token_set(candidate_text)
    intersection = base.intersection(cand)
    if not base:
        base_token_recall = 1.0
    else:
        base_token_recall = len(intersection) / float(len(base))
    union = base.union(cand)
    symmetric_token_overlap = 1.0 if not union else len(intersection) / float(len(union))
    base_wc = max(1, len([token for token in str(base_text or "").split() if token.strip()]))
    cand_wc = len([token for token in str(candidate_text or "").split() if token.strip()])
    candidate_growth_ratio = cand_wc / float(base_wc)
    return {
        "token_overlap": round(base_token_recall, 3),
        "base_token_recall": round(base_token_recall, 3),
        "symmetric_token_overlap": round(symmetric_token_overlap, 3),
        "candidate_growth_ratio": round(candidate_growth_ratio, 3),
    }


_COMMON_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their",
    "this", "to", "was", "were", "will", "with", "you", "your", "about", "over",
    "after", "before", "during", "through", "into", "while", "than", "then",
    "also", "not", "only", "just", "very", "more", "most", "some", "any", "all",
    "can", "could", "should", "would", "may", "might", "must", "do", "does", "did",
}

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

def _build_scene_director_services() -> SceneDirectorServices:
    return SceneDirectorServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        manifest=ManifestStore(
            load=get_state_manifest,
            save=save_state_manifest,
        ),
        update_scene_audio_prompt_report=_update_scene_audio_prompt_report,
        smart_retry=smart_retry,
        fireworks_chat_completion=fireworks_chat_completion,
        generate_content_config=types.GenerateContentConfig,
        normalize_scene_payload=_normalize_scene_payload,
        enforce_scene_mode_style=_enforce_scene_mode_style,
        deterministic_scene_builder=_deterministic_sentence_scenes,
        sentence_scene_recovery=_scene_sentence_splits,
        narration_profile=_narration_profile,
        normalize_narration_style=_normalize_narration_style,
        is_deterministic_user_context_mode=_is_deterministic_user_context_mode,
        minimum_scene_count_for_script=_minimum_scene_count_for_script,
        get_hash=get_hash,
        json_repair=sota_json_repair,
        unified_negative_prompt=UNIFIED_NEGATIVE_PROMPT,
        narration_style_default=NARRATION_STYLE_DEFAULT,
    )


def scene_director(state: AgentState):
    print(
        "    [SCENE DIRECTOR] Segmenting script by visual meaning & forging Style DNA..."
    )
    node_input = SceneDirectorInput(
        request_prompt=str(state.get("request_prompt", "") or ""),
        script=str(state.get("script", "") or ""),
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
        narration_style=str(state.get("narration_style", NARRATION_STYLE_DEFAULT) or NARRATION_STYLE_DEFAULT),
    )
    result = run_scene_director(node_input, _build_scene_director_services())
    return result.to_state_update()



# ==============================================================

# NODE 6: AUDIO ENGINEER (Edge-TTS + Dual-Track Alignment)

# ==============================================================

def _probe_audio_duration_seconds(audio_path: str) -> Optional[float]:
    duration_str = subprocess.getoutput(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{audio_path}"'
    )
    try:
        return float(duration_str.strip())
    except ValueError:
        return None


def _build_audio_engineer_services() -> AudioEngineerServices:
    return AudioEngineerServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        manifest=ManifestStore(
            load=get_state_manifest,
            save=save_state_manifest,
        ),
        update_scene_audio_prompt_report=_update_scene_audio_prompt_report,
        smart_retry=smart_retry,
        fireworks_chat_completion=fireworks_chat_completion,
        generate_content_config=types.GenerateContentConfig,
        duration_meta_from_state=_duration_meta_from_state,
        update_run_manifest_duration_fields=_update_run_manifest_duration_fields,
        sanitize_tts_script=_sanitize_tts_script,
        summarize_cpp_alignment=_summarize_cpp_alignment,
        is_deterministic_user_context_mode=_is_deterministic_user_context_mode,
        normalize_narration_style=_normalize_narration_style,
        narration_profile=_narration_profile,
        resolve_voice_preset=resolve_voice_preset,
        normalize_epochs_from_mapping=_normalize_epochs_from_mapping,
        build_local_epoch_mapping=_build_local_epoch_mapping,
        update_live_status=_update_live_status,
        apply_cpp=apply_cpp,
        ffprobe_duration=_probe_audio_duration_seconds,
        communicate_factory=edge_tts.Communicate,
        submaker_factory=edge_tts.SubMaker,
        write_text_artifact=_write_text_artifact,
        write_binary_artifact=_write_binary_artifact,
        json_repair=sota_json_repair,
        get_hash=get_hash,
        pronunciation_resolver=resolve_pronunciation,
        narration_style_default=NARRATION_STYLE_DEFAULT,
        voice_preset_default=DEFAULT_VOICE_PRESET_ID,
    )


def audio_engineer(state: AgentState):

    print("[AUDIO]  [AUDIO ENGINEER] Forging high-fidelity speech and VTT alignment...")

    node_input = AudioEngineerInput(
        script=str(state.get("script", "") or ""),
        context_summary=str(state.get("context_summary", "") or ""),
        request_prompt=str(state.get("request_prompt", "") or ""),
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
        narration_style=str(state.get("narration_style", NARRATION_STYLE_DEFAULT) or NARRATION_STYLE_DEFAULT),
        voice_preset=str(state.get("voice_preset", DEFAULT_VOICE_PRESET_ID) or DEFAULT_VOICE_PRESET_ID),
        visual_scenes=list(state.get("visual_scenes", []) or []),
        images_forged=int(state.get("images_forged", 0) or 0),
        qa_attempts=int(state.get("qa_attempts", 0) or 0),
        duration_mode=str(state.get("duration_mode", "") or ""),
        requested_target_duration_seconds=state.get("requested_target_duration_seconds"),
        estimated_duration_seconds=state.get("estimated_duration_seconds"),
        target_duration=state.get("target_duration"),
        actual_audio_duration_seconds=state.get("actual_audio_duration_seconds"),
    )
    result = run_audio_engineer(node_input, _build_audio_engineer_services())
    return result.to_state_update()



# ==============================================================

# NODE 6: PROMPT ARCHITECT (Phase 14)

# ==============================================================

def _build_prompt_architect_services() -> PromptArchitectServices:
    return PromptArchitectServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        manifest=ManifestStore(
            load=get_state_manifest,
            save=save_state_manifest,
        ),
        update_scene_audio_prompt_report=_update_scene_audio_prompt_report,
        smart_retry=smart_retry,
        fireworks_chat_completion=fireworks_chat_completion,
        generate_content_config=types.GenerateContentConfig,
        json_repair=sota_json_repair,
        normalize_narration_style=_normalize_narration_style,
        normalize_context_rewrite=_normalize_context_rewrite,
        narration_profile=_narration_profile,
        get_hash=get_hash,
        getenv=os.getenv,
        narration_style_default=NARRATION_STYLE_DEFAULT,
    )


def prompt_architect(state: AgentState):

    print(
        f"    [PROMPT ARCHITECT] Architecting SOTA image prompts for {state['total_epochs']} epochs...")

    node_input = PromptArchitectInput(
        script=str(state.get("script", "") or ""),
        epochs=list(state.get("epochs", []) or []),
        total_epochs=int(state.get("total_epochs", len(state.get("epochs", []) or [])) or 0),
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
        narration_style=str(state.get("narration_style", NARRATION_STYLE_DEFAULT) or NARRATION_STYLE_DEFAULT),
        style_dna=str(state.get("style_dna", "") or ""),
        meta_context=str(state.get("meta_context", "") or ""),
        character_manifest=state.get("character_manifest", {}) if isinstance(state.get("character_manifest", {}), dict) else {},
    )
    result = run_prompt_architect(node_input, _build_prompt_architect_services())
    return result.to_state_update()



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


def _normalize_pre_scene_manifest_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    style_dna = re.sub(r"\s+", " ", str(payload.get("style_dna", "") or "")).strip()
    meta_context = re.sub(r"\s+", " ", str(payload.get("meta_context", "") or "")).strip()
    scenes = payload.get("scenes")
    if not style_dna or not meta_context:
        return None
    if not isinstance(scenes, list) or not scenes:
        return None
    scene_map: Dict[int, Dict[str, Any]] = {}
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        raw_id = scene.get("id", idx + 1)
        try:
            scene_id = int(raw_id)
        except Exception:
            continue
        text = re.sub(r"\s+", " ", str(scene.get("text", "") or "")).strip()
        visual = re.sub(r"\s+", " ", str(scene.get("visual_intent", text) or text)).strip()
        if not visual:
            continue
        subjects = scene.get("subjects", [])
        if not isinstance(subjects, list):
            subjects = []
        scene_map[scene_id] = {
            "id": scene_id,
            "text": text,
            "visual_intent": visual,
            "subjects": [str(s).strip() for s in subjects if str(s).strip()],
        }
    if not scene_map:
        return None
    return {
        "style_dna": style_dna,
        "meta_context": meta_context,
        "scenes": scene_map,
    }


def _compose_pre_scene_primary_prompt(pre_scene_payload: Dict[str, Any], epoch: dict) -> str:
    raw_id = epoch.get("id", 0) if isinstance(epoch, dict) else 0
    try:
        epoch_id = int(raw_id) if isinstance(raw_id, (int, float, str)) else 0
    except Exception:
        epoch_id = 0
    scene_map = dict(pre_scene_payload.get("scenes", {}) or {})
    scene_row = scene_map.get(epoch_id, {})
    style_dna = str(pre_scene_payload.get("style_dna", "") or "").strip()
    meta_context = str(pre_scene_payload.get("meta_context", "") or "").strip()
    scene_text = re.sub(r"\s+", " ", str(scene_row.get("text", epoch.get("text", "")) or "")).strip()
    scene_visual = re.sub(r"\s+", " ", str(scene_row.get("visual_intent", scene_text) or scene_text)).strip()
    scene_visual = scene_visual[:420] + ("..." if len(scene_visual) > 420 else "")
    subjects = scene_row.get("subjects", [])
    if not isinstance(subjects, list):
        subjects = []
    subjects_block = f"Subjects: {', '.join(subjects[:8])}. " if subjects else ""
    return (
        f"STYLE DNA: {style_dna}. "
        f"META CONTEXT: {meta_context}. "
        f"TARGET SCENE ID: {epoch_id}. "
        f"TARGET VISUAL: {scene_visual}. "
        f"{subjects_block}"
        "Render exactly one photorealistic cinematic 16:9 frame for the target scene only. "
        f"{UNIFIED_NEGATIVE_PROMPT}"
    )


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
        f"{UNIFIED_NEGATIVE_PROMPT}"
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


def _build_sota_forge_services() -> SotaForgeServices:
    return SotaForgeServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        update_scene_audio_prompt_report=_update_scene_audio_prompt_report,
        update_live_status=_update_live_status,
        smart_retry=smart_retry,
        bfl_generate_image=bfl_generate_image,
        normalize_context_rewrite=_normalize_context_rewrite,
        getenv=os.getenv,
        build_epoch_context_payload=_build_epoch_context_payload,
        normalize_pre_scene_manifest_payload=_normalize_pre_scene_manifest_payload,
        compose_pre_scene_primary_prompt=_compose_pre_scene_primary_prompt,
        compose_image_generation_prompt=_compose_image_generation_prompt,
        compose_compact_epoch_fallback_prompt=_compose_compact_epoch_fallback_prompt,
        extract_main_description_for_qa=_extract_main_description_for_qa,
        run_visual_qa_for_image=_run_visual_qa_for_image,
        ensure_epoch_image_with_fallback=_ensure_epoch_image_with_fallback,
        append_jsonl_artifact=_append_jsonl_artifact,
        write_text_artifact=_write_text_artifact,
        smartcrop_factory=(lambda: smartcrop.SmartCrop()) if smartcrop else (lambda: None),
        pil_image_module=Image,
        unified_negative_prompt=UNIFIED_NEGATIVE_PROMPT,
    )


def sota_vision_forge(state: AgentState):

    print(
        f"    [SOTA VISION FORGE] Activating Per-Epoch Precision Rendering for {state['total_epochs']} epochs..."
    )
    node_input = SotaForgeInput(
        input_source=str(state.get("input_source", "") or ""),
        context_rewrite=str(state.get("context_rewrite", CONTEXT_REWRITE_DEFAULT) or CONTEXT_REWRITE_DEFAULT),
        total_epochs=int(state.get("total_epochs", len(state.get("epochs", []) or [])) or 0),
        epochs=list(state.get("epochs", []) or []),
        sota_prompts=list(state.get("sota_prompts", []) or []),
        qa_targets=list(state.get("qa_targets", []) or []),
    )
    result = run_sota_forge(node_input, _build_sota_forge_services())
    return result.to_state_update()


def _build_lead_editor_services() -> LeadEditorServices:
    return LeadEditorServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        write_text_artifact=_write_text_artifact,
        ensure_epoch_image_with_fallback=_ensure_epoch_image_with_fallback,
        normalize_watermark_mode=_normalize_watermark_mode,
        duration_meta_from_state=_duration_meta_from_state,
        subprocess_getoutput=subprocess.getoutput,
        subprocess_run=subprocess.run,
        project_dir=PROJECT_DIR,
        watermark_mode_default=WATERMARK_MODE_DEFAULT,
        watermark_font_size=WATERMARK_FONT_SIZE,
    )


def lead_editor(state: AgentState):

    print("    [LEAD EDITOR] Assembling dual-layer ASS typography and NLE render...")
    node_input = LeadEditorInput(
        audio_path=str(state.get("audio_path", "") or ""),
        epochs=list(state.get("epochs", []) or []),
        topic_callouts=list(state.get("topic_callouts", []) or []),
        watermark_mode=str(state.get("watermark_mode", WATERMARK_MODE_DEFAULT) or WATERMARK_MODE_DEFAULT),
        target_output=str(state.get("target_output", "") or ""),
        duration_mode=str(state.get("duration_mode", "manual") or "manual"),
        requested_target_duration_seconds=state.get("requested_target_duration_seconds"),
        estimated_duration_seconds=state.get("estimated_duration_seconds"),
        target_duration=state.get("target_duration"),
        actual_audio_duration_seconds=state.get("actual_audio_duration_seconds"),
    )
    result = run_lead_editor(node_input, _build_lead_editor_services())
    return result.to_state_update()


def _build_verifier_services() -> VerifierServices:
    return VerifierServices(
        artifacts=ArtifactStore(
            path=_artifact_path,
            read_path=_artifact_read_path,
            write_json=_write_json_artifact,
        ),
        subprocess_getoutput=subprocess.getoutput,
    )





# ==============================================================

# NODE 9: WHISPER VERIFIER (Post-Render Sync Check)

# ==============================================================

def whisper_verifier(state: AgentState):

    print("    [WHISPER VERIFIER] Running post-render audio-visual sync verification...")
    node_input = VerifierInput(
        target_output=str(state.get("target_output", "") or ""),
        audio_path=str(state.get("audio_path", "") or ""),
        script=str(state.get("script", "") or ""),
        vtt_path=str(state.get("vtt_path", "") or ""),
    )
    result = run_verifier(node_input, _build_verifier_services())
    report = result.verification_report
    try:
        status = "[OK] PASS" if report.get("verified") else "[WARN] DRIFT/TELEMETRY FAIL"
        print(
            f"    [VERIFIER] Video: {report.get('video_duration', 0):.1f}s | "
            f"Audio: {report.get('audio_duration', 0):.1f}s | "
            f"Words: {report.get('vtt_words', '?')}/{report.get('script_words', '?')} | {status}"
        )
    except Exception:
        pass
    return result.to_state_update()


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
    target_duration: Optional[int] = None,
    duration_mode: str = DURATION_MODE_MANUAL,
    requested_target_duration_seconds: Optional[int] = None,
    estimated_duration_seconds: Optional[int] = None,
    context_summary: Optional[str] = None,
    input_source: str = "YOUTUBE_HARVEST",
    narration_style: str = NARRATION_STYLE_DEFAULT,
    context_rewrite: str = CONTEXT_REWRITE_DEFAULT,
    watermark_mode: str = WATERMARK_MODE_DEFAULT,
    voice_preset: str = DEFAULT_VOICE_PRESET_ID,
):

    # Phase 23 Fix #19: Tee all stdout to a persistent log file for telemetry
    global _CURRENT_TIMING_RUN_ID, _CURRENT_PIPELINE_RUN_ID, _CURRENT_PIPELINE_RUN_DIR

    import sys

    run_id = time.strftime("%Y%m%d_%H%M%S")
    resolved_style = _normalize_narration_style(narration_style)
    resolved_context_rewrite = _normalize_context_rewrite(context_rewrite)
    resolved_watermark_mode = _normalize_watermark_mode(watermark_mode)
    resolved_voice_preset = str(voice_preset or DEFAULT_VOICE_PRESET_ID).strip()
    resolved_input_source = str(input_source or "YOUTUBE_HARVEST").strip().upper()
    duration_meta = resolve_duration_plan(
        input_source=resolved_input_source,
        context_rewrite=resolved_context_rewrite,
        narration_style=resolved_style,
        context_text=(str(context_summary or "").strip() or str(user_prompt or "").strip()),
        requested_target_duration=requested_target_duration_seconds,
    )
    if str(duration_mode or "").strip().lower() in {DURATION_MODE_AUTO, DURATION_MODE_MANUAL}:
        duration_meta["duration_mode"] = str(duration_mode).strip().lower()
    if estimated_duration_seconds is not None:
        duration_meta["estimated_duration_seconds"] = int(estimated_duration_seconds)
    if target_duration is not None:
        duration_meta["effective_planning_duration_seconds"] = int(target_duration)
        if duration_meta.get("duration_mode") == DURATION_MODE_MANUAL:
            duration_meta["target_duration"] = int(target_duration)
    elif duration_meta.get("duration_mode") == DURATION_MODE_AUTO:
        duration_meta["target_duration"] = None
    if resolved_input_source == "USER_CONTEXT" and resolved_context_rewrite != "off":
        print(
            f"    [ROUTING] USER_CONTEXT enforces context_rewrite=off "
            f"(requested '{resolved_context_rewrite}' overridden)."
        )
        resolved_context_rewrite = "off"
        duration_meta = resolve_duration_plan(
            input_source=resolved_input_source,
            context_rewrite=resolved_context_rewrite,
            narration_style=resolved_style,
            context_text=(str(context_summary or "").strip() or str(user_prompt or "").strip()),
            requested_target_duration=duration_meta.get("requested_target_duration_seconds"),
        )
        if estimated_duration_seconds is not None:
            duration_meta["estimated_duration_seconds"] = int(estimated_duration_seconds)
    _CURRENT_TIMING_RUN_ID = run_id
    _CURRENT_PIPELINE_RUN_ID = run_id
    _CURRENT_PIPELINE_RUN_DIR = os.path.join(ROOT_INTEL_DIR, "runs", run_id)
    os.makedirs(_CURRENT_PIPELINE_RUN_DIR, exist_ok=True)
    _write_active_run_pointer(run_id, "running")
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
            "voice_preset": resolved_voice_preset,
            "duration_mode": duration_meta.get("duration_mode"),
            "target_duration": duration_meta.get("target_duration"),
            "requested_target_duration_seconds": duration_meta.get("requested_target_duration_seconds"),
            "estimated_duration_seconds": duration_meta.get("estimated_duration_seconds"),
            "effective_planning_duration_seconds": duration_meta.get("effective_planning_duration_seconds"),
            "actual_audio_duration_seconds": duration_meta.get("actual_audio_duration_seconds"),
            "target_output": final_output,
        },
        mirror_legacy=False,
    )
    _write_json_artifact(
        "scene_audio_prompt_report.json",
        {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "run_id": run_id,
            "nodes": {},
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
            "voice_preset": resolved_voice_preset,
            "duration_mode": duration_meta.get("duration_mode"),
            "target_duration": duration_meta.get("target_duration"),
            "requested_target_duration_seconds": duration_meta.get("requested_target_duration_seconds"),
            "estimated_duration_seconds": duration_meta.get("estimated_duration_seconds"),
            "effective_planning_duration_seconds": duration_meta.get("effective_planning_duration_seconds"),
            "actual_audio_duration_seconds": duration_meta.get("actual_audio_duration_seconds"),
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
        "voice_preset": resolved_voice_preset,

        "target_output": final_output,

        "target_duration": duration_meta.get("effective_planning_duration_seconds"),
        "duration_mode": duration_meta.get("duration_mode"),
        "requested_target_duration_seconds": duration_meta.get("requested_target_duration_seconds"),
        "estimated_duration_seconds": duration_meta.get("estimated_duration_seconds"),
        "actual_audio_duration_seconds": duration_meta.get("actual_audio_duration_seconds"),

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
            _write_active_run_pointer(run_id, mission_status)
            _write_latest_run_pointer(run_id)
        except Exception:
            pass

        _CURRENT_TIMING_RUN_ID = ""
        _CURRENT_PIPELINE_RUN_ID = ""
        _CURRENT_PIPELINE_RUN_DIR = ""



    return final_output





if __name__ == "__main__":

    pass

