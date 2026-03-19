import importlib
import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import VerifierInput, VerifierOutput
from tvc_nodes.services import ArtifactStore, VerifierServices
from tvc_nodes.verifier import run_verifier


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
    video_path = tmp_path / "final.mp4"
    audio_path = tmp_path / "audio.mp3"
    vtt_path = tmp_path / "narration.vtt"
    video_path.write_bytes(b"VIDEO")
    audio_path.write_bytes(b"ID3")
    vtt_path.write_text(
        "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nApply now for a polished role.\n",
        encoding="utf-8",
    )
    payload = dict(
        target_output=str(video_path),
        audio_path=str(audio_path),
        script="Apply now for a polished role.",
        vtt_path=str(vtt_path),
    )
    payload.update(overrides)
    return VerifierInput(**payload)


def _capturing_services(tmp_path, ffprobe_lookup):
    captured_json = {}

    def write_json(name, payload, mirror_legacy=None):
        captured_json[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def subprocess_getoutput(cmd):
        return ffprobe_lookup(cmd)

    services = VerifierServices(
        artifacts=ArtifactStore(
            path=lambda name: str(tmp_path / name),
            read_path=lambda name: str(tmp_path / name),
            write_json=write_json,
        ),
        subprocess_getoutput=subprocess_getoutput,
    )
    return services, captured_json


def test_verifier_module_marks_matching_render_as_verified(tmp_path):
    def ffprobe_lookup(cmd):
        if "final.mp4" in cmd:
            return "10.0"
        if "audio.mp3" in cmd:
            return "9.6"
        raise AssertionError(cmd)

    services, captured_json = _capturing_services(tmp_path, ffprobe_lookup)
    node_input = _sample_input(tmp_path)

    result = run_verifier(node_input, services)

    assert result.status == "complete"
    assert result.verification_report["verified"] is True
    assert result.verification_report["telemetry_pass"] is True
    assert captured_json["verification_report.json"]["script_words"] == 6


def test_verifier_module_flags_drift_or_word_mismatch_without_crashing(tmp_path):
    def ffprobe_lookup(cmd):
        if "final.mp4" in cmd:
            return "15.0"
        if "audio.mp3" in cmd:
            return "10.0"
        raise AssertionError(cmd)

    services, captured_json = _capturing_services(tmp_path, ffprobe_lookup)
    node_input = _sample_input(
        tmp_path,
        script="Apply now for a polished role with calm executive presence.",
    )

    result = run_verifier(node_input, services)

    assert result.status == "complete"
    assert result.verification_report["verified"] is False
    assert result.verification_report["drift"] == 5.0
    assert captured_json["verification_report.json"]["verified"] is False


def test_verifier_module_stays_non_blocking_on_probe_error(tmp_path):
    services, captured_json = _capturing_services(
        tmp_path,
        lambda cmd: (_ for _ in ()).throw(RuntimeError("ffprobe missing")),
    )
    node_input = _sample_input(tmp_path)

    result = run_verifier(node_input, services)

    assert result.status == "complete"
    assert result.verification_report["verified"] is True
    assert captured_json["verification_report.json"]["verified"] is True


def test_verifier_core_wrapper_delegates_to_node_module(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return VerifierOutput(
            verification_report={"verified": True, "drift": 0.0},
            status="complete",
        )

    monkeypatch.setattr(core, "run_verifier", fake_run)

    result = core.whisper_verifier(
        {
            "target_output": str(tmp_path / "final.mp4"),
            "audio_path": str(tmp_path / "audio.mp3"),
            "script": "Apply now for a polished role.",
            "vtt_path": str(tmp_path / "narration.vtt"),
        }
    )

    assert isinstance(captured["input"], VerifierInput)
    assert result["status"] == "complete"
    assert result["verification_report"]["verified"] is True
