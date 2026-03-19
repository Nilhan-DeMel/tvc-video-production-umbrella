import importlib
import json
import os
import re
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import WriterInput, WriterOutput
from tvc_nodes.services import ArtifactStore, ManifestStore, WriterServices
from tvc_nodes.writer import run_writer


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


def _token_set(text):
    return set(re.findall(r"\b[a-zA-Z][a-zA-Z'-]*\b", str(text or "").lower()))


def _meaningful_terms(text, min_len=4, max_terms=24):
    terms = []
    seen = set()
    for token in re.findall(r"\b[a-zA-Z][a-zA-Z'-]*\b", str(text or "").lower()):
        if len(token) < min_len or token in seen:
            continue
        seen.add(token)
        terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def _sample_input(**overrides):
    payload = dict(
        request_prompt="Executive assistant role in Nawala supporting client events and office operations.",
        context_summary=(
            "Apply now for an executive assistant role in Nawala with polished offices, client events, "
            "calendar management, premium communication, office operations, project coordination, and "
            "professional support for leadership decisions every day across meetings and business activity."
        ),
        harvested_intelligence="",
        input_source="USER_CONTEXT",
        context_rewrite="off",
        narration_style="sales_saas",
        status="harvested",
        duration_attempts=0,
        duration_mode="auto",
        requested_target_duration_seconds=None,
        estimated_duration_seconds=48,
        target_duration=48,
        actual_audio_duration_seconds=None,
    )
    payload.update(overrides)
    return WriterInput(**payload)


def _capturing_services(tmp_path, smart_retry, *, env=None):
    env = env or {}
    captured_json = {}
    captured_text = {}
    manifest_box = {}

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

    services = WriterServices(
        artifacts=ArtifactStore(
            path=lambda name: str(tmp_path / name),
            read_path=lambda name: str(tmp_path / name),
            write_json=write_json,
        ),
        manifest=ManifestStore(
            load=lambda: dict(manifest_box),
            save=lambda data: manifest_box.update(dict(data)),
        ),
        smart_retry=smart_retry,
        fireworks_chat_completion=lambda *args, **kwargs: None,
        generate_content_config=lambda **kwargs: kwargs,
        duration_meta_from_state=lambda payload: {
            "duration_mode": payload.get("duration_mode", "manual"),
            "requested_target_duration_seconds": payload.get("requested_target_duration_seconds"),
            "estimated_duration_seconds": payload.get("estimated_duration_seconds"),
            "effective_planning_duration_seconds": payload.get("target_duration", 60),
            "actual_audio_duration_seconds": payload.get("actual_audio_duration_seconds"),
        },
        normalize_narration_style=lambda style: style or "sales_saas",
        normalize_context_rewrite=lambda value: (value or "auto").strip().lower(),
        is_deterministic_user_context_mode=lambda payload: (
            str(payload.get("input_source", "")).upper() == "USER_CONTEXT"
            and str(payload.get("context_rewrite", "")).lower() != "force"
        ),
        narration_profile=lambda style: {
            "cache_key": style,
            "label": style,
            "writer_role": "a master narration scriptwriter",
            "writer_tone_instruction": "Keep the narration modern and polished.",
            "writer_output_label": "voiceover narration",
            "writer_temperature": 0.5,
            "writer_cpp_goal": "Keep clauses smooth and natural.",
        },
        apply_cpp=lambda text: str(text or ""),
        sanitize_tts_script=lambda text: re.sub(r"\s+", " ", str(text or "")).strip(),
        clean_transcript_text=lambda text: re.sub(r"\s+", " ", str(text or "")).strip(),
        word_token_set=_token_set,
        meaningful_terms=_meaningful_terms,
        get_hash=lambda text: f"hash::{text}",
        getenv=lambda name, default=None: env.get(name, default),
        write_text_artifact=write_text,
        narration_style_default="sales_saas",
    )
    return services, captured_json, captured_text, manifest_box


def test_writer_module_bypasses_llm_in_deterministic_user_context_mode(tmp_path):
    services, captured_json, captured_text, manifest_box = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )

    result = run_writer(_sample_input(), services)

    assert result.status == "drafted"
    assert result.script == captured_text["master_script.txt"]
    assert result.duration_attempts == 1
    assert captured_json["writer_quality_report.json"]["deterministic_clamp_policy"] == "disabled"
    assert captured_json["writer_quality_report.json"]["clamp_applied"] is False
    assert captured_json["writer_quality_report.json"]["final_reason"] == "user_context_deterministic_default"
    assert manifest_box["writer_prompt_hash"].startswith("hash::")


def test_writer_module_resumes_from_valid_cache_when_not_deterministic(tmp_path):
    services, captured_json, captured_text, manifest_box = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )
    node_input = _sample_input(
        input_source="YOUTUBE_HARVEST",
        context_summary="",
        harvested_intelligence=(
            "Executive assistant role in Nawala with office operations, client events, leadership support, "
            "calendar management, premium communication, business coordination, and professional office presence."
        ),
    )
    cached_script = (
        "Executive assistant support in Nawala keeps office operations moving through client events, leadership "
        "coordination, calendar management, premium communication, business support, office presence, project "
        "support, and professional daily operations for meetings, clients, and polished executive momentum."
    )
    manifest_box["writer_prompt_hash"] = (
        f"hash::{node_input.request_prompt}|YOUTUBE_HARVEST|harvested_intelligence|"
        f"sales_saas|off|hash::{services.clean_transcript_text(node_input.harvested_intelligence)[:2500]}"
    )
    (tmp_path / "master_script.txt").write_text(cached_script, encoding="utf-8")

    result = run_writer(node_input, services)

    assert result.status == "drafted"
    assert result.script == cached_script
    assert captured_json["writer_quality_report.json"]["cache_resume_used"] is True
    assert captured_json["writer_quality_report.json"]["final_reason"] == "cache_resume_valid"
    assert "master_script.txt" not in captured_text


def test_writer_module_uses_primary_api_path_when_not_deterministic(tmp_path):
    calls = []

    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs.get("prompt_template_id"))
        return _Response(
            "Executive assistant support in Nawala keeps office operations moving through client events, leadership "
            "coordination, calendar management, premium communication, business support, office presence, project "
            "support, and professional daily operations for meetings, clients, and polished executive momentum."
        )

    services, captured_json, captured_text, manifest_box = _capturing_services(tmp_path, smart_retry=fake_retry)
    node_input = _sample_input(
        input_source="YOUTUBE_HARVEST",
        context_summary="",
        harvested_intelligence=(
            "Executive assistant role in Nawala with office operations, client events, leadership support, "
            "calendar management, premium communication, business coordination, and professional office presence."
        ),
    )

    result = run_writer(node_input, services)

    assert result.status == "drafted"
    assert calls == ["PROMPT_D_WRITER_SCRIPT_DRAFT"]
    assert captured_json["writer_quality_report.json"]["final_reason"] == "quality_gate_passed"
    assert manifest_box["writer_prompt_hash"].startswith("hash::")
    assert "office operations" in captured_text["master_script.txt"].lower()


def test_writer_module_runs_strict_retry_after_first_invalid_draft(tmp_path):
    calls = []

    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs.get("prompt_template_id"))
        if len(calls) == 1:
            return _Response("system message analysis of prompt structure")
        return _Response(
            "Executive assistant support in Nawala keeps office operations moving through client events, leadership "
            "coordination, calendar management, premium communication, business support, office presence, project "
            "support, and professional daily operations for meetings, clients, and polished executive momentum."
        )

    services, captured_json, _, _ = _capturing_services(
        tmp_path,
        smart_retry=fake_retry,
        env={"TVC_WRITER_CPP_MODE": "local"},
    )
    node_input = _sample_input(
        input_source="YOUTUBE_HARVEST",
        context_summary="",
        harvested_intelligence=(
            "Executive assistant role in Nawala with office operations, client events, leadership support, "
            "calendar management, premium communication, business coordination, and professional office presence."
        ),
    )

    result = run_writer(node_input, services)

    assert result.status == "drafted"
    assert calls == ["PROMPT_D_WRITER_SCRIPT_DRAFT", "PROMPT_D_WRITER_SCRIPT_DRAFT"]
    assert len(captured_json["writer_quality_report.json"]["attempts"]) == 2
    assert captured_json["writer_quality_report.json"]["attempts"][0]["valid"] is False
    assert captured_json["writer_quality_report.json"]["attempts"][1]["valid"] is True


def test_writer_module_falls_back_to_direct_script_on_user_context_provider_degradation(tmp_path):
    def fake_retry(func, endpoint, **kwargs):
        raise RuntimeError("412 precondition failed circuit open")

    services, captured_json, captured_text, manifest_box = _capturing_services(tmp_path, smart_retry=fake_retry)
    node_input = _sample_input(context_rewrite="force")

    result = run_writer(node_input, services)

    assert result.status == "drafted"
    assert result.script == captured_text["master_script.txt"]
    assert captured_json["writer_quality_report.json"]["fallback_mode"] == "user_context_provider_degraded_direct_script"
    assert captured_json["writer_quality_report.json"]["final_reason"] == "provider_degraded_user_context_local_path"
    assert manifest_box["writer_prompt_hash"].startswith("hash::")


def test_writer_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return WriterOutput(
            script="Final script",
            status="drafted",
            duration_attempts=2,
        )

    monkeypatch.setattr(core, "run_writer", fake_run)

    result = core.writer_node(
        {
            "request_prompt": "Executive assistant role in Nawala supporting client events and office operations.",
            "context_summary": "Direct user context for the writer.",
            "harvested_intelligence": "",
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "narration_style": "sales_saas",
            "status": "harvested",
            "duration_attempts": 1,
            "duration_mode": "auto",
            "requested_target_duration_seconds": None,
            "estimated_duration_seconds": 48,
            "target_duration": 48,
            "actual_audio_duration_seconds": None,
        }
    )

    assert isinstance(captured["input"], WriterInput)
    assert captured["input"].duration_attempts == 1
    assert result["script"] == "Final script"
    assert result["status"] == "drafted"
    assert result["duration_attempts"] == 2
