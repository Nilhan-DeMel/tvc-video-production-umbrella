import json
import os

from ui.services import (
    attach_payload_to_run,
    mark_run_terminal,
    read_live_metrics,
    resolve_active_run_binding,
    resolve_current_run_id,
    write_json,
)
from ui.state import UIState, load_ui_state, save_ui_state


def test_ui_state_roundtrip(monkeypatch, tmp_path):
    state_file = tmp_path / "ui_state.json"
    monkeypatch.setattr("ui.state.UI_STATE_PATH", str(state_file))
    src = UIState(
        theme_id="obsidian_contrast",
        density="compact",
        performance_mode="smooth",
        motion_profile="focused",
        layout_mode="command_deck",
        reduced_motion=True,
        inspector_density="compact",
        panel_visibility={"left_nav": False, "right_inspector": True},
        splitter_state="a1b2",
        recent_runs=["20260301_010101"],
    )
    save_ui_state(src)
    out = load_ui_state()
    assert out.theme_id == "obsidian_contrast"
    assert out.density == "compact"
    assert out.performance_mode == "smooth"
    assert out.motion_profile == "focused"
    assert out.layout_mode == "command_deck"
    assert out.reduced_motion is True
    assert out.inspector_density == "compact"
    assert out.panel_visibility["left_nav"] is False
    assert out.recent_runs[0] == "20260301_010101"


def test_attach_payload_writes_snapshot(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    run_id = "20260313_123456"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)

    payload_path = tmp_path / "payload.json"
    write_json(
        str(payload_path),
        {
            "mode": "MODE_NARRATE",
            "target_duration": None,
            "duration_mode": "auto",
            "estimated_duration_seconds": 47,
            "voice_preset": "style_default",
        },
    )

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    attach_payload_to_run(
        str(payload_path),
        run_id=run_id,
        process_exit_code=0,
        ui_state={
            "theme_id": "aurora_graphite",
            "density": "cozy",
            "layout_mode": "command_deck",
            "motion_profile": "cinematic",
            "panel_visibility": {"left_nav": True},
        },
    )

    launch_payload = run_dir / "ui_launch_payload.json"
    snapshot = run_dir / "run_ui_snapshot.json"
    assert launch_payload.exists()
    assert snapshot.exists()
    launch = json.loads(launch_payload.read_text(encoding="utf-8"))
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    assert launch["duration_mode"] == "auto"
    assert launch["target_duration"] is None
    assert launch["estimated_duration_seconds"] == 47
    assert snap["launch_source"] == "studio_agent_ui_v2"
    assert snap["run_id"] == run_id
    assert snap["layout_mode"] == "command_deck"
    assert snap["motion_profile"] == "cinematic"


def test_resolve_current_run_id_prefers_live_then_active_then_latest(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    for run_id in ["20260314_100000", "20260314_100001", "20260314_100002"]:
        (runs_root / run_id).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(str(db_root / "latest_run_pointer.json"), {"run_id": "20260314_100000"})
    write_json(str(db_root / "active_run_pointer.json"), {"run_id": "20260314_100001"})
    write_json(str(db_root / "live_status.json"), {"run_id": "20260314_100002"})

    assert resolve_current_run_id() == "20260314_100002"

    os.remove(db_root / "live_status.json")
    assert resolve_current_run_id() == "20260314_100001"

    os.remove(db_root / "active_run_pointer.json")
    assert resolve_current_run_id() == "20260314_100000"


def test_read_live_metrics_uses_current_observable_run(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    run_id = "20260314_200000"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(
        str(db_root / "live_status.json"),
        {
            "run_id": run_id,
            "current_node": "Audio",
            "retries_total": 2,
            "eta_human": "00:15",
            "actual_audio_duration_seconds": 42.1,
            "progress_pct": 64.5,
            "current_node_detail": "Epoch 4/12 · generating",
            "current_node_units_completed": 3,
            "current_node_units_total": 12,
        },
    )
    write_json(
        str(run_dir / "provider_resilience_report.json"),
        {"failure_count": 3},
    )

    metrics = read_live_metrics()
    assert metrics["run_id"] == run_id
    assert metrics["node"] == "Audio"
    assert metrics["api_failures"] == 3
    assert metrics["actual_audio_duration_seconds"] == 42.1
    assert metrics["progress_pct"] == 64.5
    assert metrics["node_detail"] == "Epoch 4/12 · generating"
    assert metrics["node_units_completed"] == 3
    assert metrics["node_units_total"] == 12


def test_read_live_metrics_sums_provider_failure_counts_from_counts_dict(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    run_id = "20260321_101500"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(
        str(db_root / "live_status.json"),
        {
            "run_id": run_id,
            "current_node": "SotaForge",
            "current_node_detail": "Epoch 2/5 · generating",
            "progress_pct": 40.0,
            "eta_human": "00:44",
        },
    )
    write_json(
        str(run_dir / "provider_resilience_report.json"),
        {
            "counts": {
                "retryable": 1,
                "precondition_412": 2,
                "invalid_request_400": 0,
                "circuit_open_failfast": 1,
                "sanitized_retry": 0,
                "permanent_failures": 3,
                "successful_calls": 9,
            }
        },
    )

    metrics = read_live_metrics()
    assert metrics["api_failures"] == 7


def test_read_live_metrics_enriches_deterministic_scene_director_signal(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    run_id = "20260321_101700"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(
        str(db_root / "live_status.json"),
        {
            "run_id": run_id,
            "current_node": "SceneDirector",
            "progress_pct": 20.0,
        },
    )
    write_json(
        str(run_dir / "scene_audio_prompt_report.json"),
        {
            "nodes": {
                "SceneDirector": {
                    "source": "deterministic_primary",
                    "api_bypassed": True,
                }
            }
        },
    )

    metrics = read_live_metrics()
    assert metrics["node_signal_text"] == "API BYPASSED"
    assert metrics["node_signal_tone"] == "info"
    assert metrics["node_detail"] == "Deterministic primary · API bypassed"


def test_resolve_active_run_binding_prefers_new_run_after_launch(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    for run_id in ["20260321_213328", "20260322_000219"]:
        (runs_root / run_id).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(str(db_root / "latest_run_pointer.json"), {"run_id": "20260321_213328"})

    binding = resolve_active_run_binding(
        bound_run_id="",
        launch_stamp="20260322_000218",
        prelaunch_run_ids={"20260321_213328"},
    )

    assert binding["run_id"] == "20260322_000219"
    assert binding["source"] == "fresh_after_launch"


def test_read_live_metrics_prefers_explicit_bound_run_for_artifacts(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    db_root = tmp_path / "db"
    stale_run_id = "20260321_213328"
    active_run_id = "20260322_000219"
    for run_id in [stale_run_id, active_run_id]:
        (runs_root / run_id).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("ui.services.RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(
        str(db_root / "live_status.json"),
        {
            "run_id": stale_run_id,
            "current_node": "idle",
            "progress_pct": 0.0,
        },
    )
    write_json(
        str(runs_root / active_run_id / "provider_resilience_report.json"),
        {
            "counts": {
                "retryable": 1,
                "precondition_412": 0,
                "invalid_request_400": 0,
                "circuit_open_failfast": 0,
                "sanitized_retry": 0,
                "permanent_failures": 0,
            }
        },
    )

    metrics = read_live_metrics(preferred_run_id=active_run_id)

    assert metrics["run_id"] == active_run_id
    assert metrics["api_failures"] == 1
    assert metrics["run_binding_source"] == "bound"


def test_mark_run_terminal_updates_active_pointer_and_root_live(monkeypatch, tmp_path):
    db_root = tmp_path / "db"
    monkeypatch.setattr("ui.services.DB_ROOT", str(db_root))

    write_json(
        str(db_root / "active_run_pointer.json"),
        {"run_id": "20260314_300000", "run_dir": "x", "timestamp": "old", "status": "running"},
    )
    write_json(
        str(db_root / "live_status.json"),
        {
            "run_id": "20260314_300000",
            "pipeline_status": "running",
            "last_error": "",
            "current_node_progress_ratio": 1.0,
            "current_node_units_completed": 12,
            "current_node_units_total": 12,
            "current_node_units_label": "epochs",
            "current_node_detail": "Epoch 12/12 · generating",
        },
    )

    mark_run_terminal("20260314_300000", "aborted", "aborted_by_ui")

    active = json.loads((db_root / "active_run_pointer.json").read_text(encoding="utf-8"))
    live = json.loads((db_root / "live_status.json").read_text(encoding="utf-8"))
    assert active["status"] == "aborted"
    assert live["pipeline_status"] == "aborted"
    assert live["last_error"] == "aborted_by_ui"
    assert live["current_node_progress_ratio"] is None
    assert live["current_node_units_completed"] is None
    assert live["current_node_units_total"] is None
    assert live["current_node_units_label"] == ""
    assert live["current_node_detail"] == ""
