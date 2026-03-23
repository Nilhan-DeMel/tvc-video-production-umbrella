from __future__ import annotations

import glob
import json
import os
import re
import time
from typing import Dict, Iterable, List

from .paths import DB_ROOT, EVIDENCE_ROOT, RUNS_ROOT, UI_PAYLOAD_ROOT
from tvc_launch_contract import LaunchPayloadV2, persist_launch_payload, write_context_file


def _active_run_pointer_path() -> str:
    return os.path.join(DB_ROOT, "active_run_pointer.json")


def _latest_run_pointer_path() -> str:
    return os.path.join(DB_ROOT, "latest_run_pointer.json")


def _root_live_status_path() -> str:
    return os.path.join(DB_ROOT, "live_status.json")


def _run_exists(run_id: str) -> bool:
    run_id = str(run_id or "").strip()
    return bool(run_id) and os.path.isdir(os.path.join(RUNS_ROOT, run_id))


def _normalize_run_ids(run_ids: Iterable[str] | None) -> set[str]:
    if not run_ids:
        return set()
    return {str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()}


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_json(path: str, payload):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)


def _coerce_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _provider_failure_total(resilience: Dict) -> int:
    counts = resilience.get("counts", {}) if isinstance(resilience, dict) else {}
    if isinstance(counts, dict) and counts:
        return sum(
            _coerce_int(counts.get(key))
            for key in (
                "retryable",
                "precondition_412",
                "invalid_request_400",
                "circuit_open_failfast",
                "sanitized_retry",
                "permanent_failures",
            )
        )
    return _coerce_int((resilience or {}).get("failure_count", (resilience or {}).get("failures", 0)))


def _humanize_signal(source: str, api_bypassed: bool) -> tuple[str, str]:
    src = str(source or "").strip().lower()
    if api_bypassed:
        return "API BYPASSED", "info"
    if src == "cache_resume":
        return "CACHE RESUME", "info"
    if src == "repair_retry":
        return "REPAIR RETRY", "warning"
    if src in {"deterministic_primary", "deterministic_user_context_fallback", "local_deterministic_primary", "local_cpp_primary"}:
        return "DETERMINISTIC LOCAL", "info"
    return "LIVE COMPUTE", "live"


def _enrich_sotaforge_detail(detail: str, eta: str, completed, total) -> str:
    enriched = str(detail or "").strip()
    if enriched:
        if re.search(r"\bgenerating\b", enriched, flags=re.IGNORECASE) and "image" not in enriched.lower():
            enriched = re.sub(r"\bgenerating\b", "generating images", enriched, count=1, flags=re.IGNORECASE)
    elif total:
        current = max(1, min(_coerce_int(total), _coerce_int(completed) + (0 if _coerce_int(completed) >= _coerce_int(total) else 1)))
        enriched = f"Epoch {current}/{_coerce_int(total)} · generating images"
    if eta and eta != "--" and f"ETA {eta}" not in enriched:
        enriched = f"{enriched} · ETA {eta}" if enriched else f"ETA {eta}"
    return enriched


def _node_observability(run_dir: str, node_name: str, detail: str, eta: str, completed, total) -> Dict[str, str]:
    node = str(node_name or "").strip()
    observed = {
        "node_detail": str(detail or "").strip(),
        "node_signal_text": "",
        "node_signal_tone": "",
    }
    if not run_dir or not os.path.isdir(run_dir):
        return observed

    scene_audio = read_json(os.path.join(run_dir, "scene_audio_prompt_report.json"), {})
    scene_nodes = scene_audio.get("nodes", {}) if isinstance(scene_audio, dict) else {}

    if node == "Writer":
        writer_report = read_json(os.path.join(run_dir, "writer_quality_report.json"), {})
        if writer_report.get("deterministic_user_context_path"):
            observed["node_detail"] = "Deterministic primary · exact USER_CONTEXT script preserved"
            observed["node_signal_text"], observed["node_signal_tone"] = "DETERMINISTIC PRIMARY", "info"
        elif writer_report.get("cache_resume_used"):
            observed["node_detail"] = "Cache resume · writer output reused"
            observed["node_signal_text"], observed["node_signal_tone"] = "CACHE RESUME", "info"
        return observed

    if node == "TopicExtractor":
        topic_report = read_json(os.path.join(run_dir, "topic_callout_quality_report.json"), {})
        source = str(topic_report.get("source", "") or "").strip()
        api_bypassed = bool(topic_report.get("api_bypassed", False))
        if source or api_bypassed:
            observed["node_detail"] = "Deterministic primary · API bypassed" if api_bypassed else source.replace("_", " ")
            observed["node_signal_text"], observed["node_signal_tone"] = _humanize_signal(source, api_bypassed)
        return observed

    if node in scene_nodes:
        node_report = scene_nodes.get(node, {}) if isinstance(scene_nodes, dict) else {}
        source = str(node_report.get("source", "") or node_report.get("mapping_source", "") or "").strip()
        api_bypassed = bool(node_report.get("api_bypassed", False))
        if node == "SotaForge":
            observed["node_detail"] = _enrich_sotaforge_detail(observed["node_detail"], eta, completed, total)
            observed["node_signal_text"], observed["node_signal_tone"] = "LIVE COMPUTE", "live"
            return observed
        if node == "PromptArchitect" and source == "deterministic_user_context_fallback":
            observed["node_detail"] = "Deterministic local prompt composition active"
        elif api_bypassed:
            observed["node_detail"] = "Deterministic primary · API bypassed"
        elif source:
            observed["node_detail"] = source.replace("_", " ")
        if source or api_bypassed:
            observed["node_signal_text"], observed["node_signal_tone"] = _humanize_signal(source, api_bypassed)
        return observed

    if node == "Audio":
        audio_report = read_json(os.path.join(run_dir, "audio_stage_report.json"), {})
        if audio_report:
            source = str(audio_report.get("mapping_source", "") or "").strip()
            api_bypassed = bool(audio_report.get("api_bypassed", False))
            observed["node_detail"] = (
                "Deterministic local audio path · API bypassed"
                if api_bypassed
                else source.replace("_", " ")
            )
            observed["node_signal_text"], observed["node_signal_tone"] = _humanize_signal(source, api_bypassed)
        return observed

    if node == "SotaForge":
        observed["node_detail"] = _enrich_sotaforge_detail(observed["node_detail"], eta, completed, total)
        observed["node_signal_text"], observed["node_signal_tone"] = "LIVE COMPUTE", "live"

    return observed


def resolve_latest_run_id() -> str:
    pointer = read_json(_latest_run_pointer_path(), {})
    run_id = str(pointer.get("run_id", "") or "").strip()
    if run_id and os.path.isdir(os.path.join(RUNS_ROOT, run_id)):
        return run_id
    run_ids = list_run_ids()
    return run_ids[0] if run_ids else ""


def resolve_current_run_id() -> str:
    live = read_json(_root_live_status_path(), {})
    run_id = str(live.get("run_id", "") or "").strip()
    if run_id and os.path.isdir(os.path.join(RUNS_ROOT, run_id)):
        return run_id

    active = read_json(_active_run_pointer_path(), {})
    run_id = str(active.get("run_id", "") or "").strip()
    if run_id and os.path.isdir(os.path.join(RUNS_ROOT, run_id)):
        return run_id

    run_id = resolve_latest_run_id()
    if run_id:
        return run_id

    run_ids = list_run_ids()
    return run_ids[0] if run_ids else ""


def resolve_active_run_binding(
    bound_run_id: str = "",
    launch_stamp: str = "",
    prelaunch_run_ids: Iterable[str] | None = None,
) -> Dict[str, str]:
    bound_run_id = str(bound_run_id or "").strip()
    if _run_exists(bound_run_id):
        return {"run_id": bound_run_id, "source": "bound"}

    live = read_json(_root_live_status_path(), {})
    run_id = str(live.get("run_id", "") or "").strip()
    if _run_exists(run_id):
        return {"run_id": run_id, "source": "root_live"}

    active = read_json(_active_run_pointer_path(), {})
    run_id = str(active.get("run_id", "") or "").strip()
    if _run_exists(run_id):
        return {"run_id": run_id, "source": "active_pointer"}

    known_runs = _normalize_run_ids(prelaunch_run_ids)
    run_ids = list_run_ids()
    if launch_stamp:
        fresh_candidates = [
            run_id
            for run_id in run_ids
            if run_id not in known_runs and run_id >= str(launch_stamp).strip()
        ]
    else:
        fresh_candidates = [run_id for run_id in run_ids if run_id not in known_runs]
    if fresh_candidates:
        return {"run_id": fresh_candidates[0], "source": "fresh_after_launch"}

    run_id = resolve_latest_run_id()
    if _run_exists(run_id):
        return {"run_id": run_id, "source": "latest_pointer"}

    if run_ids:
        return {"run_id": run_ids[0], "source": "run_list"}

    return {"run_id": "", "source": "none"}


def list_run_ids() -> List[str]:
    try:
        return sorted(
            [d for d in os.listdir(RUNS_ROOT) if os.path.isdir(os.path.join(RUNS_ROOT, d))],
            reverse=True,
        )
    except Exception:
        return []


def run_thumbnail(run_dir: str) -> str:
    assets = os.path.join(run_dir, "assets")
    if os.path.isdir(assets):
        candidates = sorted(glob.glob(os.path.join(assets, "epoch_001_*.png")))
        if candidates:
            return candidates[-1]
    post = sorted(glob.glob(os.path.join(run_dir, "postproduction", "placeholder_*.png")))
    if post:
        return post[0]
    return ""


def list_run_cards(limit: int = 24) -> List[Dict]:
    rows: List[Dict] = []
    for run_id in list_run_ids():
        run_dir = os.path.join(RUNS_ROOT, run_id)
        manifest = read_json(os.path.join(run_dir, "run_manifest.json"), {})
        verifier = read_json(os.path.join(run_dir, "verification_report.json"), {})
        resilience = read_json(os.path.join(run_dir, "provider_resilience_report.json"), {})
        output = str(manifest.get("target_output", "") or "")
        if output and not os.path.exists(output):
            output = ""
        rows.append(
            {
                "run_id": run_id,
                "run_dir": run_dir,
                "timestamp": str(manifest.get("timestamp", "") or ""),
                "output_video": output,
                "duration": verifier.get("video_duration"),
                "verified": verifier.get("verified"),
                "telemetry_pass": verifier.get("telemetry_pass"),
                "api_failures": _provider_failure_total(resilience),
                "fallback_count": resilience.get("fallback_count", 0),
                "thumbnail": run_thumbnail(run_dir),
            }
        )
        if len(rows) >= int(limit):
            break
    return rows

def attach_payload_to_run(payload_path: str, run_id: str, process_exit_code: int, ui_state: Dict):
    if not payload_path or not os.path.exists(payload_path):
        return
    payload = read_json(payload_path, {})
    payload["run_id"] = run_id
    payload["process_exit_code"] = int(process_exit_code)
    payload["persisted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    run_dir = os.path.join(RUNS_ROOT, run_id)
    write_json(os.path.join(run_dir, "ui_launch_payload.json"), payload)

    fp_source = "|".join(
        [
            str(payload.get("mode", "")),
            str(payload.get("duration_mode", "")),
            str(payload.get("target_duration", "")),
            str(payload.get("estimated_duration_seconds", "")),
            str(payload.get("requested_target_duration_seconds", "")),
            str(payload.get("narration_style", "")),
            str(payload.get("context_rewrite", "")),
            str(payload.get("watermark_mode", "")),
            str(payload.get("voice_preset", "")),
            str(payload.get("request_prompt", "")),
            str(payload.get("context_file", "")),
        ]
    )
    import hashlib

    fingerprint = hashlib.sha1(fp_source.encode("utf-8", errors="ignore")).hexdigest()
    snapshot = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "theme_id": ui_state.get("theme_id", "aurora_graphite"),
        "density": ui_state.get("density", "cozy"),
        "layout_mode": ui_state.get("layout_mode", "command_deck"),
        "motion_profile": ui_state.get("motion_profile", "cinematic"),
        "selected_mode": "NARRATE",
        "panel_visibility": ui_state.get("panel_visibility", {}),
        "launch_fingerprint": fingerprint,
        "launch_source": "studio_agent_ui_v2",
    }
    write_json(os.path.join(run_dir, "run_ui_snapshot.json"), snapshot)


def mark_run_terminal(run_id: str, status: str, error: str = ""):
    run_id = str(run_id or "").strip()
    if not run_id:
        return
    active = read_json(_active_run_pointer_path(), {})
    if str(active.get("run_id", "") or "").strip() == run_id:
        active["status"] = str(status or "")
        active["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_json(_active_run_pointer_path(), active)

    live = read_json(_root_live_status_path(), {})
    if str(live.get("run_id", "") or "").strip() == run_id:
        live["pipeline_status"] = str(status or "")
        live["last_error"] = str(error or live.get("last_error", "") or "")[:240]
        live["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        live["current_node_progress_ratio"] = None
        live["current_node_units_completed"] = None
        live["current_node_units_total"] = None
        live["current_node_units_label"] = ""
        live["current_node_detail"] = ""
        write_json(_root_live_status_path(), live)


def read_live_metrics(preferred_run_id: str = "") -> Dict:
    live = read_json(_root_live_status_path(), {})
    binding = resolve_active_run_binding(bound_run_id=preferred_run_id)
    run_id = str(binding.get("run_id", "") or live.get("run_id", "") or resolve_current_run_id() or "--")
    eta = str(live.get("eta", "") or live.get("eta_human", "") or "--")
    detail = str(live.get("current_node_detail", "") or "")
    node_name = str(live.get("node", "") or live.get("current_node", "") or live.get("stage", "") or "idle")
    metrics = {
        "run_id": run_id,
        "node": node_name,
        "retries": int(live.get("retries", 0) or live.get("retries_total", 0) or 0),
        "eta": eta,
        "api_failures": 0,
        "output_video": "",
        "progress_pct": float(live.get("progress_pct", 0.0) or 0.0),
        "node_detail": detail,
        "node_units_completed": live.get("current_node_units_completed"),
        "node_units_total": live.get("current_node_units_total"),
        "actual_audio_duration_seconds": live.get("actual_audio_duration_seconds"),
        "seed_is_initial_snapshot": bool(live.get("seed_is_initial_snapshot", False)),
        "node_signal_text": "",
        "node_signal_tone": "",
        "run_binding_source": str(binding.get("source", "") or ""),
    }
    if run_id and run_id != "--":
        run_dir = os.path.join(RUNS_ROOT, run_id)
        resilience = read_json(os.path.join(run_dir, "provider_resilience_report.json"), {})
        metrics["api_failures"] = _provider_failure_total(resilience)
        metrics.update(
            _node_observability(
                run_dir,
                node_name,
                detail,
                eta,
                metrics.get("node_units_completed"),
                metrics.get("node_units_total"),
            )
        )
        final_video = str(live.get("final_video", "") or "")
        if final_video and os.path.exists(final_video):
            metrics["output_video"] = final_video
        if os.path.isdir(run_dir):
            mp4s = sorted([f for f in os.listdir(run_dir) if f.lower().endswith(".mp4")])
            if mp4s and not metrics["output_video"]:
                metrics["output_video"] = os.path.join(run_dir, mp4s[-1])
    return metrics
