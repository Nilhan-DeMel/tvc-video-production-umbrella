import importlib
import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import PromptArchitectInput, PromptArchitectOutput
from tvc_nodes.services import ArtifactStore, ManifestStore, PromptArchitectServices
from tvc_nodes.prompt_architect import run_prompt_architect


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
        script="A founder enters the office. The team starts moving. A client meeting begins.",
        epochs=[
            {"id": 1, "text": "A founder enters the office.", "visual_intent": "Founder entering a bright office.", "subjects": ["founder"]},
            {"id": 2, "text": "The team starts moving.", "visual_intent": "A busy team starting work together.", "subjects": ["team"]},
        ],
        total_epochs=2,
        input_source="USER_CONTEXT",
        context_rewrite="off",
        narration_style="sales_saas",
        style_dna="Premium SaaS campaign look",
        meta_context="Business growth story",
        character_manifest={"founder": "confident founder in navy blazer"},
    )
    payload.update(overrides)
    return PromptArchitectInput(**payload)


def _capturing_services(tmp_path, smart_retry, env_value="0"):
    captured = {}
    reports = []
    manifest_box = {}

    def write_json(name, payload, mirror_legacy=None):
        captured[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    services = PromptArchitectServices(
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
        json_repair=lambda text: json.loads(text),
        normalize_narration_style=lambda style: style or "sales_saas",
        normalize_context_rewrite=lambda value: (value or "auto").strip().lower(),
        narration_profile=lambda style: {
            "cache_key": style,
            "label": style,
            "prompt_tone_hint": "Clean premium corporate imagery.",
            "scene_style_dna_default": "Fallback style DNA",
            "scene_meta_context_default": "Fallback meta context",
            "prompt_fallback_scene_label": "Narration scene",
        },
        get_hash=lambda text: f"hash::{text}",
        getenv=lambda name, default=None: env_value if name == "TVC_SUPPRESS_PROMPT_ARCHITECT_API" else default,
    )
    return services, captured, reports, manifest_box


def test_prompt_architect_module_bypasses_api_in_deterministic_mode(tmp_path):
    services, captured, reports, manifest_box = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )

    result = run_prompt_architect(_sample_input(), services)

    assert result.status == "prompts_architected"
    assert len(result.sota_prompts) == 2
    assert result.qa_targets[0] == "Photorealistic 16:9 cinematic shot: Founder entering a bright office."
    assert "Premium SaaS campaign look. Business growth story." in result.sota_prompts[0]
    assert captured["master_prompts.json"]["prompts"] == result.sota_prompts
    assert reports[-1][1]["source"] == "deterministic_user_context_fallback"
    assert manifest_box["prompts_script_hash"].startswith("hash::")


def test_prompt_architect_module_uses_primary_api_path_when_not_deterministic(tmp_path):
    calls = []

    class _Response:
        text = '[{"id": 1, "sota_prompt": "Prompt one. ABSOLUTE NEGATIVE PROMPT: No text."}, {"id": 2, "sota_prompt": "Prompt two. ABSOLUTE NEGATIVE PROMPT: No text."}]'

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs.get("prompt_template_id"))
        return _Response()

    services, captured, reports, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_prompt_architect(
        _sample_input(input_source="YOUTUBE_HARVEST", context_rewrite="off"),
        services,
    )

    assert result.status == "prompts_architected"
    assert calls == ["PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS"]
    assert result.qa_targets == ["Prompt one.", "Prompt two."]
    assert captured["master_prompts.json"]["qa_targets"] == ["Prompt one.", "Prompt two."]
    assert reports[-1][1]["source"] == "primary"


def test_prompt_architect_module_runs_repair_retry_after_primary_parse_failure(tmp_path):
    calls = []

    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        prompt_id = kwargs.get("prompt_template_id")
        calls.append(prompt_id)
        if prompt_id == "PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS":
            return _Response("not json")
        if prompt_id == "PROMPT_H_PROMPT_ARCHITECT_REPAIR":
            return _Response('[{"id": 1, "sota_prompt": "Prompt one. ABSOLUTE NEGATIVE PROMPT: No text."}, {"id": 2, "sota_prompt": "Prompt two. ABSOLUTE NEGATIVE PROMPT: No text."}]')
        raise AssertionError(f"unexpected prompt template: {prompt_id}")

    services, _, reports, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_prompt_architect(
        _sample_input(input_source="YOUTUBE_HARVEST", context_rewrite="off"),
        services,
    )

    assert result.status == "prompts_architected"
    assert calls == ["PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS", "PROMPT_H_PROMPT_ARCHITECT_REPAIR"]
    assert reports[-1][1]["source"] == "repair_retry"


def test_prompt_architect_module_uses_literal_fallback_after_dual_api_failure(tmp_path):
    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        return _Response("not json")

    services, _, reports, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_prompt_architect(
        _sample_input(input_source="YOUTUBE_HARVEST", context_rewrite="off"),
        services,
    )

    assert result.status == "prompts_architected"
    assert reports[-1][1]["source"] == "literal_fallback"
    assert result.qa_targets[1] == "Photorealistic 16:9 cinematic shot: A busy team starting work together."


def test_prompt_architect_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return PromptArchitectOutput(
            sota_prompts=["Prompt one", "Prompt two"],
            qa_targets=["QA one", "QA two"],
            status="prompts_architected",
        )

    monkeypatch.setattr(core, "run_prompt_architect", fake_run)

    result = core.prompt_architect(
        {
            "script": "A founder enters the office. The team starts moving.",
            "epochs": [
                {"id": 1, "text": "A founder enters the office.", "visual_intent": "Founder entering a bright office.", "subjects": ["founder"]},
                {"id": 2, "text": "The team starts moving.", "visual_intent": "A busy team starting work together.", "subjects": ["team"]},
            ],
            "total_epochs": 2,
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "narration_style": "sales_saas",
            "style_dna": "Premium SaaS campaign look",
            "meta_context": "Business growth story",
            "character_manifest": {"founder": "confident founder in navy blazer"},
        }
    )

    assert isinstance(captured["input"], PromptArchitectInput)
    assert captured["input"].total_epochs == 2
    assert result["sota_prompts"] == ["Prompt one", "Prompt two"]
    assert result["qa_targets"] == ["QA one", "QA two"]
    assert result["status"] == "prompts_architected"
