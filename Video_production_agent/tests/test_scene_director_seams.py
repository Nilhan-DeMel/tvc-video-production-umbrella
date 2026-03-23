import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import SceneDirectorInput, SceneDirectorOutput
from tvc_nodes.scene_director import run_scene_director
from tvc_nodes.services import ArtifactStore, ManifestStore, SceneDirectorServices


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

    return tvc_langgraph_core


def _capturing_services(tmp_path, smart_retry):
    captured = {}
    reports = []
    manifest_box = {}

    def write_json(name, payload, mirror_legacy=None):
        captured[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    services = SceneDirectorServices(
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
        normalize_scene_payload=lambda payload, script_text, narration_style=None: payload,
        enforce_scene_mode_style=lambda payload, narration_style: payload,
        deterministic_scene_builder=lambda script_text, narration_style=None: {
            "style_dna": "DNA",
            "meta_context": "CTX",
            "character_manifest": {},
            "scenes": [
                {"id": 1, "text": "One.", "visual_intent": "Shot one.", "subjects": []},
                {"id": 2, "text": "Two.", "visual_intent": "Shot two.", "subjects": []},
            ],
        },
        sentence_scene_recovery=lambda script_text: ["One.", "Two."],
        narration_profile=lambda style: {
            "cache_key": style,
            "label": style,
            "scene_direction_hint": "Keep it grounded.",
            "scene_style_dna_default": "DNA",
            "scene_meta_context_default": "CTX",
            "scene_visual_prefix": "Shot showing:",
        },
        normalize_narration_style=lambda style: style or "sales_saas",
        is_deterministic_user_context_mode=lambda state: (
            str(state.get("input_source", "")).upper() == "USER_CONTEXT"
            and str(state.get("context_rewrite", "")).lower() != "force"
        ),
        minimum_scene_count_for_script=lambda script_text: 2,
        get_hash=lambda text: f"hash::{text}",
        json_repair=lambda text: json.loads(text),
        unified_negative_prompt="ABSOLUTE NEGATIVE PROMPT: no text.",
        narration_style_default="sales_saas",
    )
    return services, captured, reports, manifest_box


def test_scene_director_module_bypasses_api_in_deterministic_mode(tmp_path):
    services, captured, reports, manifest_box = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )
    result = run_scene_director(
        SceneDirectorInput(
            request_prompt="",
            script="One. Two.",
            input_source="USER_CONTEXT",
            context_rewrite="off",
            narration_style="sales_saas",
        ),
        services,
    )

    assert result.status == "scenes_directed"
    assert len(result.visual_scenes) == 2
    assert captured["pre_scene_manifest_prompt.json"]["api_bypassed"] is True
    assert captured["scene_director_diagnostics.json"]["api_calls_made"] == 0
    assert captured["scene_director_diagnostics.json"]["final_repaired_source"] == "deterministic_primary"
    assert captured["scene_manifest.json"]["scenes"][0]["text"] == "One."
    assert manifest_box["scene_script_hash"].startswith("hash::")
    assert reports[-1][1]["source"] == "deterministic_primary"


def test_scene_director_module_uses_primary_api_path_when_not_deterministic(tmp_path):
    calls = []

    class _Response:
        text = json.dumps(
            {
                "style_dna": "DNA",
                "meta_context": "CTX",
                "character_manifest": {},
                "scenes": [
                    {"id": 1, "text": "One.", "visual_intent": "Shot one.", "subjects": []},
                    {"id": 2, "text": "Two.", "visual_intent": "Shot two.", "subjects": []},
                ],
            }
        )

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs.get("prompt_template_id"))
        return _Response()

    services, captured, reports, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_scene_director(
        SceneDirectorInput(
            request_prompt="Need office scenes",
            script="One. Two.",
            input_source="YOUTUBE_HARVEST",
            context_rewrite="off",
            narration_style="sales_saas",
        ),
        services,
    )

    assert result.status == "scenes_directed"
    assert "PROMPT_F_SCENE_DIRECTOR_SEGMENTATION" in calls
    assert captured["pre_scene_manifest.json"]["style_dna"] == "DNA"
    assert captured["scene_director_diagnostics.json"]["final_repaired_source"] == "first_response_local_repair"
    assert reports[-1][1]["source"] == "primary"


def test_scene_director_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return SceneDirectorOutput(
            visual_scenes=[{"id": 1, "text": "One.", "visual_intent": "Shot one.", "subjects": []}],
            style_dna="DNA",
            meta_context="CTX",
            character_manifest={},
            status="scenes_directed",
        )

    monkeypatch.setattr(core, "run_scene_director", fake_run)

    result = core.scene_director(
        {
            "request_prompt": "Need office scenes",
            "script": "One.",
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "narration_style": "sales_saas",
        }
    )

    assert isinstance(captured["input"], SceneDirectorInput)
    assert captured["input"].script == "One."
    assert result["style_dna"] == "DNA"
    assert result["status"] == "scenes_directed"
