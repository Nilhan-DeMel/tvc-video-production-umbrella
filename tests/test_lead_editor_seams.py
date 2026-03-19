import importlib
import json
import os
import subprocess
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import LeadEditorInput, LeadEditorOutput
from tvc_nodes.services import ArtifactStore, LeadEditorServices
from tvc_nodes.lead_editor import run_lead_editor


def _load_langgraph_core(monkeypatch):
    uname_result = namedtuple("uname_result", ["sysname", "nodename", "release", "version", "machine"])(
        "Linux",
        "codex",
        "5.15.0",
        "",
        "x86_64",
    )
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        os,
        "uname",
        lambda: uname_result,
        raising=False,
    )
    if "tvc_langgraph_core" in sys.modules:
        del sys.modules["tvc_langgraph_core"]
    import tvc_langgraph_core

    importlib.reload(tvc_langgraph_core)
    return tvc_langgraph_core


def _sample_input(tmp_path, **overrides):
    audio_path = tmp_path / "master_narration.mp3"
    audio_path.write_bytes(b"ID3")
    target_output = tmp_path / "final.mp4"
    payload = dict(
        audio_path=str(audio_path),
        epochs=[
            {
                "id": 1,
                "text": "Apply now for an exciting executive assistant role.",
                "start_time": 0.1,
                "end_time": 3.6,
                "duration": 3.5,
                "image_path": "",
            },
            {
                "id": 2,
                "text": "Step into polished offices and important meetings.",
                "start_time": 3.615,
                "end_time": 8.241,
                "duration": 4.626,
                "image_path": "",
            },
        ],
        topic_callouts=[
            {"topic": "EXECUTIVE ASSISTANT", "after_sentence": 1},
            {"topic": "POLISHED OFFICES", "after_sentence": 2},
        ],
        watermark_mode="on",
        target_output=str(target_output),
        duration_mode="auto",
        requested_target_duration_seconds=None,
        estimated_duration_seconds=12.0,
        target_duration=12.0,
        actual_audio_duration_seconds=None,
    )
    payload.update(overrides)
    return LeadEditorInput(**payload)


def _capturing_services(tmp_path, ffmpeg_runner, *, ffprobe_output="12.0", watermark_font_size=14):
    captured_json = {}
    captured_text = {}
    ensured = []

    def write_json(name, payload, mirror_legacy=None):
        captured_json[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def write_text(name, payload, mirror_legacy=None):
        captured_text[name] = str(payload)
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(payload), encoding="utf-8")
        return str(path)

    def ensure_epoch_image_with_fallback(target_fp, last_valid_path="", label=""):
        ensured.append({"target_fp": target_fp, "last_valid_path": last_valid_path, "label": label})
        path = tmp_path / os.path.relpath(target_fp, tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if last_valid_path and os.path.exists(last_valid_path):
            with open(last_valid_path, "rb") as src, open(path, "wb") as dst:
                dst.write(src.read())
            return "copied_previous"
        path.write_bytes(b"PNG")
        return "placeholder"

    services = LeadEditorServices(
        artifacts=ArtifactStore(
            path=lambda name: str(tmp_path / name),
            read_path=lambda name: str(tmp_path / name),
            write_json=write_json,
        ),
        write_text_artifact=write_text,
        ensure_epoch_image_with_fallback=ensure_epoch_image_with_fallback,
        normalize_watermark_mode=lambda value: (value or "on").strip().lower(),
        duration_meta_from_state=lambda payload: {
            "duration_mode": payload.get("duration_mode", "manual"),
            "requested_target_duration_seconds": payload.get("requested_target_duration_seconds"),
            "estimated_duration_seconds": payload.get("estimated_duration_seconds"),
            "effective_planning_duration_seconds": payload.get("target_duration", 60.0),
            "actual_audio_duration_seconds": payload.get("actual_audio_duration_seconds"),
        },
        subprocess_getoutput=lambda cmd: ffprobe_output,
        subprocess_run=ffmpeg_runner,
        project_dir=str(tmp_path),
        watermark_mode_default="on",
        watermark_font_size=watermark_font_size,
    )
    return services, captured_json, captured_text, ensured


def test_lead_editor_module_success_path_writes_artifacts_and_returns_rendered(tmp_path):
    ffmpeg_calls = []

    def fake_run(cmd, cwd, check, capture_output):
        ffmpeg_calls.append({"cmd": list(cmd), "cwd": cwd, "check": check, "capture_output": capture_output})
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    services, captured_json, captured_text, _ = _capturing_services(tmp_path, fake_run)
    node_input = _sample_input(tmp_path)

    result = run_lead_editor(node_input, services)

    assert result.status == "rendered"
    assert result.final_video == node_input.target_output
    assert "typography.ass" in captured_text
    assert "filter.txt" in captured_text
    assert "editor_overlay_report.json" in captured_json
    assert ffmpeg_calls[0]["cmd"][0] == "ffmpeg"


def test_lead_editor_module_schedules_topic_cards_deterministically(tmp_path):
    services, captured_json, _, _ = _capturing_services(
        tmp_path,
        lambda cmd, cwd, check, capture_output: subprocess.CompletedProcess(cmd, 0, b"", b""),
    )
    node_input = _sample_input(tmp_path)

    result = run_lead_editor(node_input, services)
    overlay = captured_json["editor_overlay_report.json"]

    assert result.status == "rendered"
    assert overlay["policy"] == "strict_one_at_a_time"
    assert overlay["scheduled_count"] == 2
    assert overlay["scheduled_windows"][0]["topic"] == "EXECUTIVE ASSISTANT"
    assert overlay["scheduled_windows"][1]["start"] >= overlay["scheduled_windows"][0]["end"]


def test_lead_editor_module_reports_centered_watermark_geometry(tmp_path):
    services, captured_json, _, _ = _capturing_services(
        tmp_path,
        lambda cmd, cwd, check, capture_output: subprocess.CompletedProcess(cmd, 0, b"", b""),
        watermark_font_size=17,
    )
    node_input = _sample_input(tmp_path)

    result = run_lead_editor(node_input, services)
    watermark = captured_json["editor_overlay_report.json"]["watermark"]

    assert result.status == "rendered"
    assert watermark["font_size"] == 17
    assert watermark["position"] == {"x": 960, "y": 540}
    assert watermark["center_invariant"]["is_equal"] is True


def test_lead_editor_module_preflights_missing_epoch_images_and_preserves_image_source(tmp_path):
    services, _, _, ensured = _capturing_services(
        tmp_path,
        lambda cmd, cwd, check, capture_output: subprocess.CompletedProcess(cmd, 0, b"", b""),
    )
    node_input = _sample_input(
        tmp_path,
        epochs=[
            {
                "id": 1,
                "text": "Apply now for an exciting executive assistant role.",
                "start_time": 0.1,
                "end_time": 3.6,
                "duration": 3.5,
                "image_path": "",
            }
        ],
    )

    result = run_lead_editor(node_input, services)

    assert result.status == "rendered"
    assert ensured
    assert node_input.epochs[0]["image_source"] == "placeholder"
    assert os.path.exists(node_input.epochs[0]["image_path"])


def test_lead_editor_module_uses_duration_metadata_when_ffprobe_is_invalid(tmp_path):
    services, captured_json, _, _ = _capturing_services(
        tmp_path,
        lambda cmd, cwd, check, capture_output: subprocess.CompletedProcess(cmd, 0, b"", b""),
        ffprobe_output="not-a-float",
    )
    node_input = _sample_input(tmp_path, target_duration=19.5)

    result = run_lead_editor(node_input, services)
    overlay = captured_json["editor_overlay_report.json"]

    assert result.status == "rendered"
    assert overlay["timeline_end"] == 19.5
    assert overlay["watermark"]["timeline"]["end"] == 19.5


def test_lead_editor_module_returns_render_failed_on_ffmpeg_error(tmp_path):
    def failing_run(cmd, cwd, check, capture_output):
        raise subprocess.CalledProcessError(1, cmd, stderr=b"simulated ffmpeg failure output")

    services, _, _, _ = _capturing_services(tmp_path, failing_run)
    node_input = _sample_input(tmp_path)

    result = run_lead_editor(node_input, services)

    assert result.status == "render_failed"
    assert result.errors
    assert "FFmpeg failed" in result.errors[0]


def test_lead_editor_core_wrapper_delegates_to_node_module(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return LeadEditorOutput(status="rendered", final_video=str(tmp_path / "delegated.mp4"))

    monkeypatch.setattr(core, "run_lead_editor", fake_run)

    result = core.lead_editor(
        {
            "audio_path": str(tmp_path / "audio.mp3"),
            "epochs": [{"id": 1, "text": "One", "start_time": 0.0, "end_time": 1.0, "duration": 1.0}],
            "topic_callouts": [{"topic": "ONE", "after_sentence": 1}],
            "watermark_mode": "on",
            "target_output": str(tmp_path / "output.mp4"),
            "duration_mode": "auto",
            "requested_target_duration_seconds": None,
            "estimated_duration_seconds": 1.0,
            "target_duration": 1.0,
            "actual_audio_duration_seconds": None,
        }
    )

    assert isinstance(captured["input"], LeadEditorInput)
    assert captured["input"].target_output.endswith("output.mp4")
    assert result["status"] == "rendered"
    assert result["final_video"].endswith("delegated.mp4")
