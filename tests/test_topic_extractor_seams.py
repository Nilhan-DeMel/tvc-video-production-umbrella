import importlib
import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import TopicExtractorInput, TopicExtractorOutput
from tvc_nodes.services import ArtifactStore, ManifestStore, TopicExtractorServices
from tvc_nodes.topic_extractor import run_topic_extractor


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


def _capturing_services(tmp_path, smart_retry):
    captured = {}
    manifest_box = {}

    def write_json(name, payload, mirror_legacy=None):
        captured[name] = payload
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    services = TopicExtractorServices(
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
        is_deterministic_user_context_mode=lambda state: (
            str(state.get("input_source", "")).upper() == "USER_CONTEXT"
            and str(state.get("context_rewrite", "")).lower() != "force"
        ),
        get_hash=lambda text: f"hash::{text}",
        json_repair=lambda text: json.loads(text),
    )
    return services, captured, manifest_box


def test_topic_extractor_module_bypasses_fireworks_in_deterministic_mode(tmp_path):
    services, captured, manifest_box = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )

    result = run_topic_extractor(
        TopicExtractorInput(
            script="Morning light fills the office. A founder walks in with purpose. The team starts moving fast.",
            input_source="USER_CONTEXT",
            context_rewrite="off",
        ),
        services,
    )

    assert result.status == "topics_extracted"
    assert result.topic_callouts
    assert captured["topic_extractor_diagnostics.json"]["api_bypassed"] is True
    assert captured["topic_extractor_diagnostics.json"]["primary_repair_reason"] == "deterministic_local_primary"
    assert captured["topic_callout_quality_report.json"]["source"] == "deterministic_primary"
    assert manifest_box["topic_script_hash"].startswith("hash::")


def test_topic_extractor_module_uses_primary_api_path_when_not_deterministic(tmp_path):
    calls = []

    class _Response:
        text = '[{"topic":"OFFICE","after_sentence":1}]'

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs.get("prompt_template_id"))
        return _Response()

    services, captured, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_topic_extractor(
        TopicExtractorInput(
            script="Morning light fills the office. A founder walks in with purpose.",
            input_source="YOUTUBE_HARVEST",
            context_rewrite="off",
        ),
        services,
    )

    assert result.status == "topics_extracted"
    assert "PROMPT_TOPIC_EXTRACTOR_CALLOUTS" in calls
    assert captured["topic_callout_quality_report.json"]["source"] == "primary"


def test_topic_extractor_module_runs_repair_retry_after_primary_parse_failure(tmp_path):
    calls = []

    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        prompt_id = kwargs.get("prompt_template_id")
        calls.append(prompt_id)
        if prompt_id == "PROMPT_TOPIC_EXTRACTOR_CALLOUTS":
            return _Response("not json")
        if prompt_id == "PROMPT_TOPIC_EXTRACTOR_REPAIR":
            return _Response('[{"topic":"OFFICE","after_sentence":1}]')
        raise AssertionError(f"unexpected prompt template: {prompt_id}")

    services, captured, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_topic_extractor(
        TopicExtractorInput(
            script="Morning light fills the office. A founder walks in with purpose.",
            input_source="YOUTUBE_HARVEST",
            context_rewrite="off",
        ),
        services,
    )

    assert result.status == "topics_extracted"
    assert calls == ["PROMPT_TOPIC_EXTRACTOR_CALLOUTS", "PROMPT_TOPIC_EXTRACTOR_REPAIR"]
    assert captured["topic_extractor_diagnostics.json"]["repair_retry_success"] is True
    assert captured["topic_extractor_diagnostics.json"]["final_selected_source"] == "repair_retry"


def test_topic_extractor_module_uses_deterministic_fallback_after_dual_api_failure(tmp_path):
    class _Response:
        def __init__(self, text):
            self.text = text

    def fake_retry(func, endpoint, **kwargs):
        return _Response("not json")

    services, captured, _ = _capturing_services(tmp_path, smart_retry=fake_retry)
    result = run_topic_extractor(
        TopicExtractorInput(
            script="Morning light fills the office. A founder walks in with purpose.",
            input_source="YOUTUBE_HARVEST",
            context_rewrite="off",
        ),
        services,
    )

    assert result.status == "topics_extracted"
    assert captured["topic_extractor_diagnostics.json"]["repair_retry_success"] is False
    assert captured["topic_extractor_diagnostics.json"]["final_selected_source"] == "deterministic_fallback"
    assert captured["topic_callout_quality_report.json"]["source"] == "deterministic_fallback"


def test_topic_extractor_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return TopicExtractorOutput(
            topic_callouts=[{"topic": "OFFICE", "after_sentence": 1}],
            status="topics_extracted",
        )

    monkeypatch.setattr(core, "run_topic_extractor", fake_run)

    result = core.topic_extractor(
        {
            "script": "Morning light fills the office.",
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
        }
    )

    assert isinstance(captured["input"], TopicExtractorInput)
    assert captured["input"].script == "Morning light fills the office."
    assert result["topic_callouts"] == [{"topic": "OFFICE", "after_sentence": 1}]
    assert result["status"] == "topics_extracted"
