import importlib
import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import AudioEngineerInput, AudioEngineerOutput
from tvc_nodes.services import ArtifactStore, AudioEngineerServices, ManifestStore
from tvc_nodes.audio_engineer import run_audio_engineer


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
        script="Launch now.",
        context_summary="Launch now.",
        request_prompt="Launch now.",
        input_source="USER_CONTEXT",
        context_rewrite="off",
        narration_style="sales_saas",
        voice_preset="style_default",
        visual_scenes=[{"id": 1, "text": "Launch now.", "visual_intent": "Polished office", "subjects": []}],
        images_forged=0,
        qa_attempts=0,
        duration_mode="manual",
        requested_target_duration_seconds=60,
        estimated_duration_seconds=60,
        target_duration=60,
        actual_audio_duration_seconds=None,
    )
    payload.update(overrides)
    return AudioEngineerInput(**payload)


def _capturing_services(tmp_path, smart_retry, *, synth_failure=None):
    captured = {}
    reports = []
    manifest_box = {}
    communicate_inputs = []

    def fake_hash(text):
        return f"hash::{text}"

    def write_json(name, payload, mirror_legacy=None):
        captured[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def write_text(name, payload, mirror_legacy=None):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(payload), encoding="utf-8")
        return str(path)

    def write_binary(name, payload, mirror_legacy=None):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return str(path)

    class FakeCommunicate:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            communicate_inputs.append({"args": args, "kwargs": kwargs})

        async def stream(self):
            if synth_failure:
                raise RuntimeError(synth_failure)
            yield {"type": "audio", "data": b"ID3"}

    class FakeSubMaker:
        def feed(self, chunk):
            return None

        def get_srt(self):
            return "1\n00:00:00,000 --> 00:00:01,000\nLaunch now.\n"

    services = AudioEngineerServices(
        artifacts=ArtifactStore(
            path=lambda name: str(tmp_path / name),
            read_path=lambda name: str(tmp_path / name),
            write_json=write_json,
        ),
        manifest=ManifestStore(
            load=lambda: dict(manifest_box),
            save=lambda data: manifest_box.update(dict(data)),
        ),
        update_scene_audio_prompt_report=lambda node, payload: reports.append((node, payload)),
        smart_retry=smart_retry,
        fireworks_chat_completion=lambda *args, **kwargs: None,
        generate_content_config=lambda **kwargs: kwargs,
        duration_meta_from_state=lambda payload, actual_audio_duration=None: {
            "duration_mode": payload.get("duration_mode"),
            "requested_target_duration_seconds": payload.get("requested_target_duration_seconds"),
            "estimated_duration_seconds": payload.get("estimated_duration_seconds"),
            "effective_planning_duration_seconds": payload.get("target_duration"),
            "actual_audio_duration_seconds": actual_audio_duration,
        },
        update_run_manifest_duration_fields=lambda duration_meta: None,
        sanitize_tts_script=lambda text: str(text or "").strip(),
        summarize_cpp_alignment=lambda base, candidate: {"base_token_recall": 1.0},
        is_deterministic_user_context_mode=lambda payload: (
            str(payload.get("input_source", "")).upper() == "USER_CONTEXT"
            and str(payload.get("context_rewrite", "")).lower() != "force"
        ),
        normalize_narration_style=lambda style: style or "sales_saas",
        narration_profile=lambda style: {
            "cache_key": style,
            "label": style,
            "audio_cpp_goal": "Keep it smooth.",
            "audio_tts": {"voice": "en-GB-RyanNeural", "rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
        },
        resolve_voice_preset=lambda preset_id, tts_profile: {
            "effective_preset_id": preset_id,
            "fallback_used": False,
            "fallback_reason": "",
            "provider": "edge",
            "engine": "edge_tts",
            "voice": tts_profile.get("voice", "en-GB-RyanNeural"),
            "voice_identity": tts_profile.get("voice", "en-GB-RyanNeural"),
            "style_base": dict(tts_profile),
            "preset_overlay": {},
            "rate": tts_profile.get("rate", "+0%"),
            "pitch": tts_profile.get("pitch", "+0Hz"),
            "volume": tts_profile.get("volume", "+0%"),
        },
        normalize_epochs_from_mapping=lambda raw_epochs, visual_scenes: raw_epochs,
        build_local_epoch_mapping=lambda visual_scenes, vtt_text, script_text: [
            {
                "id": 1,
                "start_time": 0.0,
                "end_time": 12.34,
                "duration": 12.34,
                "text": visual_scenes[0]["text"],
                "visual_intent": visual_scenes[0]["visual_intent"],
                "subjects": [],
            }
        ],
        update_live_status=lambda fields, force=False: None,
        apply_cpp=lambda text: text,
        ffprobe_duration=lambda audio_path: 12.34,
        communicate_factory=FakeCommunicate,
        submaker_factory=FakeSubMaker,
        write_text_artifact=write_text,
        write_binary_artifact=write_binary,
        json_repair=lambda text: json.loads(text),
        get_hash=fake_hash,
        pronunciation_resolver=lambda text, backend, voice: {
            "display_script": str(text or "").strip(),
            "spoken_script": str(text or "").strip(),
            "matched_rules": [],
            "matched_rule_ids": [],
            "backend": backend,
            "voice": voice,
            "display_spoken_diff": False,
        },
        narration_style_default="sales_saas",
        voice_preset_default="style_default",
    )
    return services, captured, reports, manifest_box, fake_hash, communicate_inputs


def test_audio_engineer_module_bypasses_fireworks_in_deterministic_mode(tmp_path):
    services, captured, reports, manifest_box, _, _ = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )

    result = run_audio_engineer(_sample_input(), services)

    assert result.status == "audio_forged"
    assert result.actual_audio_duration_seconds == 12.34
    assert captured["audio_stage_report.json"]["api_bypassed"] is True
    stages = {item["stage"]: item for item in captured["audio_stage_report.json"]["stages"]}
    assert stages["neural_cpp"]["status"] == "bypassed"
    assert stages["vtt_map_refine"]["status"] == "bypassed"
    assert reports[-1][1]["source"] == "local_cpp_primary"
    assert reports[-1][1]["mapping_source"] == "local_deterministic_primary"
    assert manifest_box["audio_script_hash"].startswith("hash::")


def test_audio_engineer_module_uses_primary_api_path_when_not_deterministic(tmp_path):
    calls = []

    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        prompt_id = kwargs.get("prompt_template_id")
        calls.append(prompt_id)
        if prompt_id == "PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT":
            return _Response("Launch now.")
        if prompt_id == "PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING":
            return _Response(json.dumps([{
                "id": 1,
                "start_time": 0.0,
                "end_time": 12.34,
                "duration": 12.34,
                "text": "Launch now.",
                "visual_intent": "Polished office",
                "subjects": [],
            }]))
        raise AssertionError(f"unexpected prompt template: {prompt_id}")

    services, captured, reports, _, _, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_audio_engineer(
        _sample_input(input_source="YOUTUBE_HARVEST", context_rewrite="off"),
        services,
    )

    assert result.status == "audio_forged"
    assert calls == ["PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT", "PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING"]
    assert captured["audio_stage_report.json"]["mapping_source"] == "llm_refine_primary"
    assert reports[-1][1]["source"] == "neural_cpp"


def test_audio_engineer_module_resumes_from_cache(tmp_path):
    services, _, reports, manifest_box, fake_hash, _ = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )
    node_input = _sample_input(input_source="YOUTUBE_HARVEST", context_rewrite="off")
    voice = "en-GB-RyanNeural"
    rate = "+0%"
    pitch = "+0Hz"
    volume = "+0%"
    manifest_box["audio_script_hash"] = fake_hash(
        f"{fake_hash(node_input.script)}|{fake_hash(node_input.script)}||sales_saas|style_default|{voice}|{rate}|{pitch}|{volume}"
    )
    (tmp_path / "master_narration.mp3").write_bytes(b"ID3")
    (tmp_path / "narration.vtt").write_text("WEBVTT\n\n", encoding="utf-8")
    (tmp_path / "vtt_matrix.json").write_text(
        json.dumps([{
            "id": 1,
            "start_time": 0.0,
            "end_time": 12.34,
            "duration": 12.34,
            "text": "Launch now.",
            "visual_intent": "Polished office",
            "subjects": [],
        }]),
        encoding="utf-8",
    )

    result = run_audio_engineer(node_input, services)

    assert result.status == "audio_forged"
    assert result.audio_path.endswith("master_narration.mp3")
    assert result.vtt_path.endswith("narration.vtt")
    assert reports[-1][1]["source"] == "cache_resume"
    assert reports[-1][1]["mapping_source"] == "cache_resume"


def test_audio_engineer_module_returns_failed_status_on_synthesis_failure(tmp_path):
    services, captured, reports, _, _, _ = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
        synth_failure="tts exploded",
    )

    result = run_audio_engineer(_sample_input(), services)

    assert result.status == "failed"
    assert result.errors == ["Voice Forge Failed: tts exploded"]
    assert captured["audio_stage_report.json"]["status"] == "failed"
    assert reports[-1][1]["failure"] == "Voice Forge Failed: tts exploded"


def test_audio_engineer_uses_spoken_alias_and_writes_pronunciation_artifacts(tmp_path):
    services, captured, _, _, _, communicate_inputs = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )
    services = services.__class__(
        **{
            **services.__dict__,
            "pronunciation_resolver": lambda text, backend, voice: {
                "display_script": str(text or "").strip(),
                "spoken_script": "I create AI-powered videos with refinement, rhythm, and visual clarity.",
                "matched_rules": [
                    {
                        "id": "phrase.polish_rhythm_visual_clarity",
                        "scope": "phrase",
                        "match": "with polish, rhythm, and visual clarity",
                    }
                ],
                "matched_rule_ids": ["phrase.polish_rhythm_visual_clarity"],
                "backend": backend,
                "voice": voice,
                "display_spoken_diff": True,
            },
        }
    )

    result = run_audio_engineer(
        _sample_input(
            script="I create AI-powered videos with polish, rhythm, and visual clarity.",
            context_summary="I create AI-powered videos with polish, rhythm, and visual clarity.",
            request_prompt="I create AI-powered videos with polish, rhythm, and visual clarity.",
            visual_scenes=[{"id": 1, "text": "I create AI-powered videos with polish, rhythm, and visual clarity.", "visual_intent": "Polished office", "subjects": []}],
        ),
        services,
    )

    assert result.status == "audio_forged"
    assert communicate_inputs[-1]["args"][0] == "I create AI-powered videos with refinement, rhythm, and visual clarity."
    assert (tmp_path / "spoken_script.txt").read_text(encoding="utf-8") == communicate_inputs[-1]["args"][0]
    report = json.loads((tmp_path / "pronunciation_report.json").read_text(encoding="utf-8"))
    assert report["matched_rule_ids"] == ["phrase.polish_rhythm_visual_clarity"]
    assert report["display_spoken_diff"] is True
    assert captured["audio_stage_report.json"]["pronunciation_resolver_used"] is True
    assert captured["audio_stage_report.json"]["pronunciation_rule_count"] == 1
    assert captured["audio_stage_report.json"]["display_spoken_diff"] is True


def test_audio_engineer_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return AudioEngineerOutput(
            audio_path="audio.mp3",
            vtt_path="narration.vtt",
            actual_audio_duration_seconds=12.34,
            epochs=[{"id": 1}],
            total_epochs=1,
            images_forged=0,
            qa_attempts=0,
            status="audio_forged",
        )

    monkeypatch.setattr(core, "run_audio_engineer", fake_run)

    result = core.audio_engineer(
        {
            "script": "Launch now.",
            "context_summary": "Launch now.",
            "request_prompt": "Launch now.",
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "narration_style": "sales_saas",
            "voice_preset": "style_default",
            "visual_scenes": [{"id": 1, "text": "Launch now.", "visual_intent": "Polished office", "subjects": []}],
            "images_forged": 0,
            "qa_attempts": 0,
            "duration_mode": "manual",
            "requested_target_duration_seconds": 60,
            "estimated_duration_seconds": 60,
            "target_duration": 60,
            "actual_audio_duration_seconds": None,
        }
    )

    assert isinstance(captured["input"], AudioEngineerInput)
    assert captured["input"].voice_preset == "style_default"
    assert result["audio_path"] == "audio.mp3"
    assert result["actual_audio_duration_seconds"] == 12.34
    assert result["status"] == "audio_forged"
