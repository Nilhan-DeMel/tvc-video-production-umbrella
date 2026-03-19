import importlib
import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_voice_registry import resolve_voice_preset


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


def _make_json_writer(tmp_path, captured):
    def _write_json_artifact(name, payload, mirror_legacy=None):
        captured[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    return _write_json_artifact


def _make_text_writer(tmp_path):
    def _write_text_artifact(name, payload, mirror_legacy=None):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(payload), encoding="utf-8")
        return str(path)

    return _write_text_artifact


def _make_binary_writer(tmp_path):
    def _write_binary_artifact(name, payload, mirror_legacy=None):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return str(path)

    return _write_binary_artifact


def test_topic_extractor_bypasses_fireworks_for_deterministic_user_context(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    monkeypatch.setattr(core, "smart_retry", lambda *args, **kwargs: pytest.fail("smart_retry should not run"))
    monkeypatch.setattr(core, "get_state_manifest", lambda: {})
    monkeypatch.setattr(core, "save_state_manifest", lambda manifest: None)
    monkeypatch.setattr(core, "_artifact_read_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(core, "_write_json_artifact", _make_json_writer(tmp_path, captured))

    result = core.topic_extractor(
        {
            "script": "Morning light fills the office. A founder walks in with purpose. The team starts moving fast.",
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
        }
    )

    diagnostics = captured["topic_extractor_diagnostics.json"]
    quality = captured["topic_callout_quality_report.json"]

    assert result["status"] == "topics_extracted"
    assert result["topic_callouts"]
    assert diagnostics["api_bypassed"] is True
    assert diagnostics["bypass_reason"] == "deterministic_user_context_mode"
    assert quality["api_bypassed"] is True
    assert quality["bypass_reason"] == "deterministic_user_context_mode"


def test_topic_extractor_keeps_fireworks_path_for_non_deterministic_runs(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}
    calls = []

    class _Resp:
        text = '[{"topic":"OFFICE","after_sentence":1}]'

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs.get("prompt_template_id"))
        return _Resp()

    monkeypatch.setattr(core, "smart_retry", fake_retry)
    monkeypatch.setattr(core, "get_state_manifest", lambda: {})
    monkeypatch.setattr(core, "save_state_manifest", lambda manifest: None)
    monkeypatch.setattr(core, "_artifact_read_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(core, "_write_json_artifact", _make_json_writer(tmp_path, captured))

    result = core.topic_extractor(
        {
            "script": "Morning light fills the office. A founder walks in with purpose.",
            "input_source": "YOUTUBE_HARVEST",
            "context_rewrite": "off",
        }
    )

    assert result["status"] == "topics_extracted"
    assert "PROMPT_TOPIC_EXTRACTOR_CALLOUTS" in calls


def test_audio_engineer_bypasses_fireworks_for_deterministic_user_context(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    class FakeCommunicate:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def stream(self):
            yield {"type": "audio", "data": b"ID3"}

    class FakeSubMaker:
        def feed(self, chunk):
            return None

        def get_srt(self):
            return "1\n00:00:00,000 --> 00:00:01,000\nLaunch now.\n"

    monkeypatch.setattr(core, "smart_retry", lambda *args, **kwargs: pytest.fail("smart_retry should not run"))
    monkeypatch.setattr(core.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(core.edge_tts, "SubMaker", FakeSubMaker)
    monkeypatch.setattr(core, "get_state_manifest", lambda: {})
    monkeypatch.setattr(core, "save_state_manifest", lambda manifest: None)
    monkeypatch.setattr(core, "_artifact_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(core, "_artifact_read_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(core, "_write_json_artifact", _make_json_writer(tmp_path, captured))
    monkeypatch.setattr(core, "_write_text_artifact", _make_text_writer(tmp_path))
    monkeypatch.setattr(core, "_write_binary_artifact", _make_binary_writer(tmp_path))
    monkeypatch.setattr(core, "_build_local_epoch_mapping", lambda scenes, vtt, script: [
        {
            "id": 1,
            "start_time": 0.0,
            "end_time": 12.34,
            "duration": 12.34,
            "text": scenes[0]["text"],
            "visual_intent": scenes[0]["visual_intent"],
            "subjects": [],
        }
    ])
    monkeypatch.setattr(core, "apply_cpp", lambda text: text)
    monkeypatch.setattr(core.subprocess, "getoutput", lambda cmd: "12.34")
    monkeypatch.setattr(core, "_update_run_manifest_duration_fields", lambda payload: None)
    monkeypatch.setattr(core, "_update_live_status", lambda fields, force=False: None)
    monkeypatch.setattr(core, "_update_scene_audio_prompt_report", lambda node, payload: None)

    result = core.audio_engineer(
        {
            "script": "Launch now.",
            "context_summary": "Launch now.",
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "narration_style": "sales_saas",
            "voice_preset": "jenny_marketing",
            "visual_scenes": [{"id": 1, "text": "Launch now.", "visual_intent": "Polished office"}],
        }
    )

    stage = captured["audio_stage_report.json"]
    stages = {item["stage"]: item for item in stage["stages"]}

    assert result["status"] == "audio_forged"
    assert stage["api_bypassed"] is True
    assert stage["bypass_reason"] == "deterministic_user_context_mode"
    assert stages["neural_cpp"]["status"] == "bypassed"
    assert stages["vtt_map_refine"]["status"] == "bypassed"
    assert stage["voice"] == "en-US-JennyNeural"
    assert stage["voice_style_base"]["rate"] == "+12%"
    assert stage["voice_preset_overlay"]["rate"] == "+6%"
    assert stage["tts_params"]["rate"] == "+18%"
    assert stage["tts_params"]["pitch"] == "+8Hz"
    assert stage["tts_params"]["volume"] == "+10%"


def test_audio_engineer_keeps_fireworks_path_for_non_deterministic_runs(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}
    calls = []

    class FakeCommunicate:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def stream(self):
            yield {"type": "audio", "data": b"ID3"}

    class FakeSubMaker:
        def feed(self, chunk):
            return None

        def get_srt(self):
            return "1\n00:00:00,000 --> 00:00:01,000\nLaunch now.\n"

    class _Resp:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        prompt_template_id = kwargs.get("prompt_template_id")
        calls.append(prompt_template_id)
        if prompt_template_id == "PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT":
            return _Resp("Launch now.")
        if prompt_template_id == "PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING":
            return _Resp(json.dumps([{
                "id": 1,
                "start_time": 0.0,
                "end_time": 12.34,
                "duration": 12.34,
                "text": "Launch now.",
                "visual_intent": "Polished office",
            }]))
        raise AssertionError(f"unexpected prompt template: {prompt_template_id}")

    monkeypatch.setattr(core, "smart_retry", fake_retry)
    monkeypatch.setattr(core.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(core.edge_tts, "SubMaker", FakeSubMaker)
    monkeypatch.setattr(core, "get_state_manifest", lambda: {})
    monkeypatch.setattr(core, "save_state_manifest", lambda manifest: None)
    monkeypatch.setattr(core, "_artifact_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(core, "_artifact_read_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(core, "_write_json_artifact", _make_json_writer(tmp_path, captured))
    monkeypatch.setattr(core, "_write_text_artifact", _make_text_writer(tmp_path))
    monkeypatch.setattr(core, "_write_binary_artifact", _make_binary_writer(tmp_path))
    monkeypatch.setattr(core, "_build_local_epoch_mapping", lambda scenes, vtt, script: [
        {
            "id": 1,
            "start_time": 0.0,
            "end_time": 12.34,
            "duration": 12.34,
            "text": scenes[0]["text"],
            "visual_intent": scenes[0]["visual_intent"],
            "subjects": [],
        }
    ])
    monkeypatch.setattr(core, "apply_cpp", lambda text: text)
    monkeypatch.setattr(core.subprocess, "getoutput", lambda cmd: "12.34")
    monkeypatch.setattr(core, "_update_run_manifest_duration_fields", lambda payload: None)
    monkeypatch.setattr(core, "_update_live_status", lambda fields, force=False: None)
    monkeypatch.setattr(core, "_update_scene_audio_prompt_report", lambda node, payload: None)

    result = core.audio_engineer(
        {
            "script": "Launch now.",
            "context_summary": "Launch now.",
            "input_source": "YOUTUBE_HARVEST",
            "context_rewrite": "off",
            "narration_style": "documentary",
            "voice_preset": "style_default",
            "visual_scenes": [{"id": 1, "text": "Launch now.", "visual_intent": "Polished office"}],
        }
    )

    assert result["status"] == "audio_forged"
    assert "PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT" in calls
    assert "PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING" in calls


def test_sales_style_shapes_explicit_edge_voice():
    documentary = {"voice": "en-GB-RyanNeural", "rate": "+0%", "pitch": "+0Hz", "volume": "+0%"}
    sales = {"voice": "en-GB-RyanNeural", "rate": "+12%", "pitch": "+6Hz", "volume": "+8%"}

    documentary_voice = resolve_voice_preset("andrew_corporate", documentary)
    sales_voice = resolve_voice_preset("andrew_corporate", sales)

    assert documentary_voice["voice"] == sales_voice["voice"] == "en-US-AndrewNeural"
    assert documentary_voice["rate"] != sales_voice["rate"]
    assert documentary_voice["pitch"] != sales_voice["pitch"]
    assert documentary_voice["volume"] != sales_voice["volume"]
    assert sales_voice["style_base"]["rate"] == "+12%"
    assert sales_voice["preset_overlay"]["rate"] == "+1%"


def test_external_voice_fallback_keeps_style_overlay(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    sales = {"voice": "en-GB-RyanNeural", "rate": "+12%", "pitch": "+6Hz", "volume": "+8%"}

    resolved = resolve_voice_preset("elevenlabs_premium_scaffold", sales)

    assert resolved["fallback_used"] is True
    assert resolved["effective_preset_id"] == "jenny_marketing"
    assert resolved["voice"] == "en-US-JennyNeural"
    assert resolved["style_base"]["rate"] == "+12%"
    assert resolved["preset_overlay"]["rate"] == "+6%"
    assert resolved["rate"] == "+18%"


def test_live_status_seed_is_explicitly_initial_snapshot(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    monkeypatch.setattr(core, "_write_json_artifact", _make_json_writer(tmp_path, captured))
    monkeypatch.setattr(core, "_write_text_artifact", _make_text_writer(tmp_path))

    core._init_live_status("run-123", {"actual_audio_duration_seconds": None})

    assert core._LIVE_STATUS["seed_is_initial_snapshot"] is True
    assert captured["live_status.json"]["seed_is_initial_snapshot"] is True
    assert captured["live_status.json"]["seed"]["actual_audio_duration_seconds"] is None
