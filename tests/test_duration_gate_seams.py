import importlib
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import DurationGateInput, DurationGateOutput
from tvc_nodes.duration_gate import run_duration_gate
from tvc_nodes.services import DurationGateServices


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


def _sample_input(**overrides):
    payload = dict(
        input_source="YOUTUBE_HARVEST",
        context_rewrite="off",
        script="Apply now for a polished executive assistant role in Nawala.",
        duration_attempts=1,
        duration_mode="manual",
        requested_target_duration_seconds=60,
        estimated_duration_seconds=22,
        target_duration=22,
        actual_audio_duration_seconds=None,
    )
    payload.update(overrides)
    return DurationGateInput(**payload)


def _capturing_services():
    captured = {}

    def write_text(name, payload, mirror_legacy=None):
        captured[name] = str(payload)
        return name

    services = DurationGateServices(
        normalize_context_rewrite=lambda value: (value or "auto").strip().lower(),
        duration_meta_from_state=lambda payload: {
            "duration_mode": payload.get("duration_mode", "manual"),
            "requested_target_duration_seconds": payload.get("requested_target_duration_seconds"),
            "estimated_duration_seconds": payload.get("estimated_duration_seconds"),
            "effective_planning_duration_seconds": payload.get("target_duration", 60),
            "actual_audio_duration_seconds": payload.get("actual_audio_duration_seconds"),
        },
        write_text_artifact=write_text,
    )
    return services, captured


def test_duration_gate_module_bypasses_for_deterministic_user_context():
    services, captured = _capturing_services()

    result = run_duration_gate(
        _sample_input(input_source="USER_CONTEXT", context_rewrite="off"),
        services,
    )

    assert result.status == "duration_pass"
    assert result.script == ""
    assert captured == {}


def test_duration_gate_module_passes_when_within_tolerance():
    services, _ = _capturing_services()

    result = run_duration_gate(
        _sample_input(
            script="Apply now for a polished executive assistant role in Nawala with calm professional presence.",
            target_duration=4,
            estimated_duration_seconds=4,
            requested_target_duration_seconds=4,
        ),
        services,
    )

    assert result.status == "duration_pass"
    assert result.script == ""


def test_duration_gate_module_truncates_after_three_attempts_and_writes_script():
    services, captured = _capturing_services()
    long_script = (
        "Apply now for an exciting executive assistant role in Nawala. "
        "Step into polished offices, important meetings, and premium client coordination every day. "
        "Support leadership, manage schedules, and keep complex business priorities moving."
    )

    result = run_duration_gate(
        _sample_input(
            script=long_script,
            duration_attempts=3,
            target_duration=2,
            estimated_duration_seconds=40,
            requested_target_duration_seconds=2,
        ),
        services,
    )

    assert result.status == "duration_pass"
    assert result.script
    assert len(result.script.split()) < len(long_script.split())
    assert captured["master_script.txt"] == result.script


def test_duration_gate_module_rejects_before_attempt_limit():
    services, captured = _capturing_services()
    long_script = " ".join(["Executive"] * 80)

    result = run_duration_gate(
        _sample_input(
            script=long_script,
            duration_attempts=2,
            target_duration=8,
            estimated_duration_seconds=40,
            requested_target_duration_seconds=8,
        ),
        services,
    )

    assert result.status == "duration_fail"
    assert result.script == ""
    assert captured == {}


def test_duration_gate_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return DurationGateOutput(status="duration_pass", script="Trimmed script.")

    monkeypatch.setattr(core, "run_duration_gate", fake_run)

    result = core.duration_gate(
        {
            "input_source": "YOUTUBE_HARVEST",
            "context_rewrite": "off",
            "script": "Apply now for a polished executive assistant role in Nawala.",
            "duration_attempts": 1,
            "duration_mode": "manual",
            "requested_target_duration_seconds": 22,
            "estimated_duration_seconds": 22,
            "target_duration": 22,
            "actual_audio_duration_seconds": None,
        }
    )

    assert isinstance(captured["input"], DurationGateInput)
    assert result["status"] == "duration_pass"
    assert result["script"] == "Trimmed script."
