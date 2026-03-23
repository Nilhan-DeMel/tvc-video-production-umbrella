import hashlib
import importlib
import json
import os
import sys
from collections import namedtuple

import pytest

from tvc_nodes.contracts import SotaForgeInput, SotaForgeOutput
from tvc_nodes.services import ArtifactStore, SotaForgeServices
from tvc_nodes.sota_forge import run_sota_forge


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
        input_source="USER_CONTEXT",
        context_rewrite="off",
        total_epochs=1,
        epochs=[{"id": 1, "text": "Launch now.", "visual_intent": "Polished office", "subjects": []}],
        sota_prompts=["LEGACY::1"],
        qa_targets=["QA::1"],
    )
    payload.update(overrides)
    return SotaForgeInput(**payload)


class _FakeOpenedImage:
    def __init__(self, size=(1920, 1080), mode="RGB"):
        self.size = size
        self.mode = mode

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def convert(self, mode):
        self.mode = mode
        return self

    def crop(self, box):
        return self

    def resize(self, size, resample):
        self.size = size
        return self

    def save(self, path, quality=95):
        with open(path, "wb") as handle:
            handle.write(b"PNG")


class _FakeImageModule:
    class Resampling:
        LANCZOS = object()

    @staticmethod
    def open(path):
        return _FakeOpenedImage()


def _capturing_services(tmp_path, smart_retry, *, env=None, qa_result=None):
    env = env or {}
    captured_json = {}
    captured_text = {}
    captured_jsonl = {}
    reports = []
    live_updates = []

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

    def append_jsonl(name, payload, mirror_legacy=None):
        captured_jsonl.setdefault(name, []).append(dict(payload))
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        return str(path)

    def ensure_epoch_image_with_fallback(target_fp, last_valid_path="", label=""):
        if os.path.exists(target_fp):
            return "generated"
        if last_valid_path and os.path.exists(last_valid_path):
            with open(last_valid_path, "rb") as src, open(target_fp, "wb") as dst:
                dst.write(src.read())
            return "copied_previous"
        with open(target_fp, "wb") as handle:
            handle.write(b"PNG")
        return "placeholder"

    services = SotaForgeServices(
        artifacts=ArtifactStore(
            path=lambda name: str(tmp_path / name),
            read_path=lambda name: str(tmp_path / name),
            write_json=write_json,
        ),
        update_scene_audio_prompt_report=lambda node, payload: reports.append((node, payload)),
        update_live_status=lambda fields, force=False: live_updates.append((dict(fields), force)),
        smart_retry=smart_retry,
        bfl_generate_image=lambda *args, **kwargs: True,
        normalize_context_rewrite=lambda value: (value or "auto").strip().lower(),
        getenv=lambda name, default=None: env.get(name, default),
        build_epoch_context_payload=lambda epochs: [{"id": e["id"], "text": e["text"], "visual_intent": e["visual_intent"]} for e in epochs],
        normalize_pre_scene_manifest_payload=lambda payload: payload if isinstance(payload, dict) and "style_dna" in payload and "meta_context" in payload and "scenes" in payload else None,
        compose_pre_scene_primary_prompt=lambda payload, epoch: f"PRE::{epoch['id']}",
        compose_image_generation_prompt=lambda base_prompt, epoch, epochs_payload: f"{base_prompt}|GEN::{epoch['id']}",
        compose_compact_epoch_fallback_prompt=lambda epoch, style_hint="": f"FALLBACK::{epoch['id']}",
        extract_main_description_for_qa=lambda current_prompt, qa_targets, idx: qa_targets[idx],
        run_visual_qa_for_image=lambda image_path, main_description, qa_model, qa_pass_threshold: (
            qa_result
            if qa_result is not None
            else {"qa_text": "SCORE: 7/10. CATEGORY:QUALITY. CRITIQUE: Fine", "score": 7.0, "has_real_score": True, "critique": "Fine", "failure_cat": "QUALITY"}
        ),
        ensure_epoch_image_with_fallback=ensure_epoch_image_with_fallback,
        append_jsonl_artifact=append_jsonl,
        write_text_artifact=write_text,
        smartcrop_factory=lambda: None,
        pil_image_module=_FakeImageModule,
        unified_negative_prompt="ABSOLUTE NEGATIVE PROMPT: No text.",
    )
    return services, captured_json, captured_text, captured_jsonl, reports, live_updates


def test_sota_forge_module_selects_pre_scene_primary_route_when_repaired_manifest_exists(tmp_path):
    def fake_retry(func, endpoint, **kwargs):
        with open(kwargs["output_path"], "wb") as handle:
            handle.write(b"PNG")
        return True

    services, captured_json, captured_text, captured_jsonl, reports, _ = _capturing_services(
        tmp_path,
        smart_retry=fake_retry,
    )
    (tmp_path / "pre_scene_manifest_repaired.json").write_text(
        json.dumps({
            "style_dna": "DNA",
            "meta_context": "CTX",
            "scenes": {1: {"id": 1, "text": "Launch now.", "visual_intent": "Polished office", "subjects": []}},
        }),
        encoding="utf-8",
    )

    result = run_sota_forge(_sample_input(), services)

    assert result.status == "sota_vision_complete"
    assert reports[0][1]["route_source"] == "pre_scene_primary"
    assert captured_text["sota_epoch_001_generation_prompt.txt"] == "PRE::1"
    assert captured_jsonl["sota_prompt_route_trace.jsonl"][-1]["route_variant"] == "pre_scene_repaired_primary"


def test_sota_forge_module_uses_legacy_route_when_pre_scene_candidate_missing(tmp_path):
    def fake_retry(func, endpoint, **kwargs):
        with open(kwargs["output_path"], "wb") as handle:
            handle.write(b"PNG")
        return True

    services, _, captured_text, captured_jsonl, reports, _ = _capturing_services(
        tmp_path,
        smart_retry=fake_retry,
    )

    result = run_sota_forge(_sample_input(), services)

    assert result.status == "sota_vision_complete"
    assert reports[0][1]["route_source"] == "legacy_primary"
    assert captured_text["sota_epoch_001_generation_prompt.txt"] == "LEGACY::1|GEN::1"
    assert captured_jsonl["sota_prompt_route_trace.jsonl"][-1]["route_source"] == "legacy_primary"


def test_sota_forge_module_suppresses_visual_qa_in_deterministic_mode(tmp_path):
    def fake_retry(func, endpoint, **kwargs):
        with open(kwargs["output_path"], "wb") as handle:
            handle.write(b"PNG")
        return True

    def qa_should_not_run(*args, **kwargs):
        pytest.fail("visual QA should not run")

    services, _, _, captured_jsonl, reports, _ = _capturing_services(
        tmp_path,
        smart_retry=fake_retry,
    )
    services = services.__class__(**{**services.__dict__, "run_visual_qa_for_image": qa_should_not_run})

    result = run_sota_forge(_sample_input(), services)

    assert result.status == "sota_vision_complete"
    assert result.qa_scores == [4.0]
    assert reports[-1][1]["images_forged"] == 1
    assert captured_jsonl["sota_prompt_route_trace.jsonl"][-1]["epoch_result"] == "qa_pass"


def test_sota_forge_module_uses_compact_fallback_on_primary_invalid_request(tmp_path):
    calls = []

    def fake_retry(func, endpoint, **kwargs):
        calls.append(kwargs["prompt_template_id"])
        if kwargs["prompt_template_id"] == "PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT":
            raise RuntimeError("400 invalid_request")
        with open(kwargs["output_path"], "wb") as handle:
            handle.write(b"PNG")
        return True

    services, _, captured_text, captured_jsonl, _, _ = _capturing_services(
        tmp_path,
        smart_retry=fake_retry,
    )

    result = run_sota_forge(_sample_input(input_source="YOUTUBE_HARVEST", context_rewrite="off"), services)

    assert result.status == "sota_vision_complete"
    assert calls == ["PROMPT_I_SOTA_FORGE_FINAL_IMAGE_PROMPT", "PROMPT_I_SOTA_FORGE_FALLBACK_COMPACT"]
    assert captured_text["sota_epoch_001_generation_prompt_fallback.txt"] == "FALLBACK::1"
    assert captured_jsonl["sota_prompt_route_trace.jsonl"][-1]["fallback_used"] is True


def test_sota_forge_module_reuses_cached_image_without_regeneration(tmp_path):
    services, _, _, captured_jsonl, _, _ = _capturing_services(
        tmp_path,
        smart_retry=lambda *args, **kwargs: pytest.fail("smart_retry should not run"),
    )
    seeded_prompt = "LEGACY::1|GEN::1"
    prompt_hash = hashlib.sha256(seeded_prompt.encode("utf-8")).hexdigest()[:8]
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / f"epoch_001_{prompt_hash}.png").write_bytes(b"PNG")

    result = run_sota_forge(_sample_input(), services)

    assert result.status == "sota_vision_complete"
    assert result.images_forged == 1
    assert captured_jsonl["sota_prompt_route_trace.jsonl"][-1]["cache_used"] is True


def test_sota_forge_core_wrapper_delegates_to_node_module(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    def fake_run(node_input, services):
        captured["input"] = node_input
        captured["services"] = services
        return SotaForgeOutput(
            status="sota_vision_complete",
            qa_scores=[7.0],
            images_forged=1,
            epochs=[{"id": 1, "image_source": "generated"}],
        )

    monkeypatch.setattr(core, "run_sota_forge", fake_run)

    result = core.sota_vision_forge(
        {
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "total_epochs": 1,
            "epochs": [{"id": 1, "text": "Launch now.", "visual_intent": "Polished office", "subjects": []}],
            "sota_prompts": ["LEGACY::1"],
            "qa_targets": ["QA::1"],
        }
    )

    assert isinstance(captured["input"], SotaForgeInput)
    assert captured["input"].total_epochs == 1
    assert result["status"] == "sota_vision_complete"
    assert result["qa_scores"] == [7.0]
    assert result["images_forged"] == 1
