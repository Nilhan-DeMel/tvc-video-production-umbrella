import importlib
import os
import sys
from collections import namedtuple

from tvc_duration import resolve_duration_plan


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


def test_resolve_duration_plan_auto_mode_does_not_mark_requested_duration():
    plan = resolve_duration_plan(
        input_source="USER_CONTEXT",
        context_rewrite="off",
        narration_style="documentary",
        context_text="One two three four five six seven eight nine ten.",
        requested_target_duration=60,
    )

    assert plan["duration_mode"] == "auto"
    assert plan["requested_target_duration_seconds"] is None
    assert plan["target_duration"] is None
    assert int(plan["estimated_duration_seconds"]) > 0
    assert int(plan["effective_planning_duration_seconds"]) > 0


def test_duration_meta_from_state_keeps_auto_mode_requested_duration_null(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    meta = core._duration_meta_from_state(
        {
            "input_source": "USER_CONTEXT",
            "context_rewrite": "off",
            "narration_style": "documentary",
            "context_summary": "One two three four five six seven eight nine ten.",
            "duration_mode": "auto",
            "target_duration": 41,
            "requested_target_duration_seconds": None,
            "estimated_duration_seconds": 41,
        }
    )

    assert meta["duration_mode"] == "auto"
    assert meta["requested_target_duration_seconds"] is None
    assert meta["estimated_duration_seconds"] == 41
    assert meta["effective_planning_duration_seconds"] == 41


def test_cpp_alignment_metrics_make_expansion_obvious(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    base = "alpha beta gamma delta"
    candidate = "alpha beta gamma delta " + " ".join(f"extra{i}" for i in range(20))

    metrics = core._summarize_cpp_alignment(base, candidate)

    assert metrics["base_token_recall"] == 1.0
    assert metrics["candidate_growth_ratio"] > 1.0
    assert metrics["symmetric_token_overlap"] < 1.0


def test_update_run_manifest_duration_fields_refreshes_actual_audio_duration(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(
        '{"run_id":"r1","duration_mode":"auto","target_duration":null,'
        '"requested_target_duration_seconds":null,"estimated_duration_seconds":41,'
        '"effective_planning_duration_seconds":41,"actual_audio_duration_seconds":null}',
        encoding="utf-8",
    )

    monkeypatch.setattr(core, "_CURRENT_PIPELINE_RUN_DIR", str(run_dir))
    core._update_run_manifest_duration_fields(
        {
            "duration_mode": "auto",
            "requested_target_duration_seconds": None,
            "estimated_duration_seconds": 41,
            "effective_planning_duration_seconds": 41,
            "actual_audio_duration_seconds": 41.64,
        }
    )

    payload = manifest_path.read_text(encoding="utf-8")
    assert '"actual_audio_duration_seconds": 41.64' in payload


def test_init_live_status_mirrors_to_root_live_status(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    root_dir = tmp_path / "db"
    run_dir = root_dir / "runs" / "run_1"
    run_dir.mkdir(parents=True)

    monkeypatch.setattr(core, "ROOT_INTEL_DIR", str(root_dir))
    monkeypatch.setattr(core, "_CURRENT_PIPELINE_RUN_DIR", str(run_dir))

    core._init_live_status("run_1", {"actual_audio_duration_seconds": None})

    assert (run_dir / "live_status.json").exists()
    assert (root_dir / "live_status.json").exists()
    payload = (root_dir / "live_status.json").read_text(encoding="utf-8")
    assert '"run_id": "run_1"' in payload


def test_progress_from_live_status_uses_node_subprogress_when_present(monkeypatch):
    core = _load_langgraph_core(monkeypatch)

    no_subprogress = core._progress_from_live_status(
        {
            "nodes_completed": ["Harvester", "Writer", "DurationGate", "TopicExtractor", "SceneDirector", "Audio", "PromptArchitect"],
            "current_node": "SotaForge",
        }
    )
    with_subprogress = core._progress_from_live_status(
        {
            "nodes_completed": ["Harvester", "Writer", "DurationGate", "TopicExtractor", "SceneDirector", "Audio", "PromptArchitect"],
            "current_node": "SotaForge",
            "current_node_progress_ratio": 0.5,
            "current_node_units_completed": 6,
            "current_node_units_total": 12,
            "current_node_units_label": "epochs",
            "current_node_detail": "Epoch 7/12 · generating",
        }
    )

    assert no_subprogress["progress_pct"] == 73.5
    assert with_subprogress["progress_pct"] > no_subprogress["progress_pct"]
    assert with_subprogress["progress_pct"] < 80.0


def test_progress_from_live_status_never_reaches_100_before_completion(monkeypatch):
    core = _load_langgraph_core(monkeypatch)

    progress = core._progress_from_live_status(
        {
            "nodes_completed": ["Harvester", "Writer", "DurationGate", "TopicExtractor", "SceneDirector", "Audio", "PromptArchitect"],
            "current_node": "SotaForge",
            "current_node_progress_ratio": 1.0,
        }
    )

    assert progress["progress_pct"] < 100.0


def test_scene_audio_prompt_report_is_seeded_run_local_not_previous_run(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    root_dir = tmp_path / "db"
    old_run_dir = root_dir / "runs" / "old_run"
    new_run_dir = root_dir / "runs" / "new_run"
    old_run_dir.mkdir(parents=True)
    new_run_dir.mkdir(parents=True)

    (old_run_dir / "scene_audio_prompt_report.json").write_text(
        '{"timestamp":"old","run_id":"old_run","nodes":{"Audio":{"audio_stage_report":"old"}}}',
        encoding="utf-8",
    )
    (root_dir / "latest_run_pointer.json").write_text(
        '{"run_id":"old_run","run_dir":"' + str(old_run_dir).replace("\\", "\\\\") + '"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(core, "ROOT_INTEL_DIR", str(root_dir))
    monkeypatch.setattr(core, "_CURRENT_PIPELINE_RUN_ID", "new_run")
    monkeypatch.setattr(core, "_CURRENT_PIPELINE_RUN_DIR", str(new_run_dir))

    core._write_json_artifact(
        "scene_audio_prompt_report.json",
        {"timestamp": "now", "run_id": "new_run", "nodes": {}},
        mirror_legacy=False,
    )
    core._update_scene_audio_prompt_report("SceneDirector", {"status": "ok", "scene_count": 3})

    payload = (new_run_dir / "scene_audio_prompt_report.json").read_text(encoding="utf-8")
    assert '"run_id": "new_run"' in payload
    assert '"SceneDirector"' in payload
    assert "old_run" not in payload


def test_sotaforge_node_end_preserves_subprogress_fields_during_handoff(monkeypatch, tmp_path):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    monkeypatch.setattr(core, "_write_json_artifact", lambda name, payload, mirror_legacy=None: captured.setdefault(name, []).append(dict(payload)))
    monkeypatch.setattr(core, "_write_text_artifact", lambda name, text, mirror_legacy=None: None)

    core._init_live_status("run-subprogress", {})
    core._update_live_status(
        {
            "nodes_completed": [
                "Harvester",
                "Writer",
                "DurationGate",
                "TopicExtractor",
                "SceneDirector",
                "Audio",
                "PromptArchitect",
            ],
            "current_node": "SotaForge",
            "current_node_event": "start",
            "current_node_progress_ratio": 0.5,
            "current_node_units_completed": 6,
            "current_node_units_total": 12,
            "current_node_units_label": "epochs",
            "current_node_detail": "Epoch 7/12 · generating",
        },
        force=True,
    )

    core.trace_node_timing("SotaForge", "end", monotonic_s=10.0, duration_s=4.0, status="ok")

    last_payload = captured["live_status.json"][-1]
    assert last_payload["current_node"] == "SotaForge"
    assert last_payload["current_node_event"] == "end"
    assert last_payload["current_node_progress_ratio"] == 0.5
    assert last_payload["current_node_units_completed"] == 6
    assert last_payload["current_node_units_total"] == 12
    assert last_payload["current_node_units_label"] == "epochs"
    assert last_payload["current_node_detail"] == "Epoch 7/12 · generating"
    assert last_payload["progress_pct"] == 80.0


def test_next_node_start_clears_prior_sotaforge_subprogress(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    monkeypatch.setattr(core, "_write_json_artifact", lambda name, payload, mirror_legacy=None: captured.setdefault(name, []).append(dict(payload)))
    monkeypatch.setattr(core, "_write_text_artifact", lambda name, text, mirror_legacy=None: None)

    core._init_live_status("run-subprogress", {})
    core._update_live_status(
        {
            "current_node": "SotaForge",
            "current_node_event": "end",
            "current_node_progress_ratio": 1.0,
            "current_node_units_completed": 12,
            "current_node_units_total": 12,
            "current_node_units_label": "epochs",
            "current_node_detail": "Epoch 12/12 · generating",
        },
        force=True,
    )

    core.trace_node_timing("Editor", "start", monotonic_s=11.0, status="running")

    last_payload = captured["live_status.json"][-1]
    assert last_payload["current_node"] == "Editor"
    assert last_payload["current_node_event"] == "start"
    assert last_payload["current_node_progress_ratio"] is None
    assert last_payload["current_node_units_completed"] is None
    assert last_payload["current_node_units_total"] is None
    assert last_payload["current_node_units_label"] == ""
    assert last_payload["current_node_detail"] == ""


def test_finalize_live_status_clears_transient_subprogress(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    captured = {}

    monkeypatch.setattr(core, "_write_json_artifact", lambda name, payload, mirror_legacy=None: captured.setdefault(name, []).append(dict(payload)))
    monkeypatch.setattr(core, "_write_text_artifact", lambda name, text, mirror_legacy=None: None)

    core._init_live_status("run-finalize", {})
    core._update_live_status(
        {
            "current_node": "Verifier",
            "current_node_event": "end",
            "current_node_progress_ratio": 1.0,
            "current_node_units_completed": 12,
            "current_node_units_total": 12,
            "current_node_units_label": "epochs",
            "current_node_detail": "Epoch 12/12 · generating",
        },
        force=True,
    )

    core._finalize_live_status("success", final_video="D:\\final.mp4")

    last_payload = captured["live_status.json"][-1]
    assert last_payload["pipeline_status"] == "success"
    assert last_payload["current_node_progress_ratio"] is None
    assert last_payload["current_node_units_completed"] is None
    assert last_payload["current_node_units_total"] is None
    assert last_payload["current_node_units_label"] == ""
    assert last_payload["current_node_detail"] == ""


def test_watermark_font_size_constant_is_14(monkeypatch):
    core = _load_langgraph_core(monkeypatch)
    assert core.WATERMARK_FONT_SIZE == 14
