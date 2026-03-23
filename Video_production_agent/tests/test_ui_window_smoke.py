import os
import json
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QApplication

from ui.main_window import TVCStudioAgentWindow
from ui.state import UIState
from tvc_voice_registry import DEFAULT_VOICE_PRESET_ID, voice_preset_choices


def _rect_in(window, widget):
    top_left = widget.mapTo(window, QPoint(0, 0))
    return QRect(top_left, widget.size())


def test_ui_window_smoke(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    assert win.page_stack.count() == 4
    assert win.left_nav.count() == 4
    assert win.voice_combo.count() == len(voice_preset_choices())
    assert win.voice_combo.currentData() == DEFAULT_VOICE_PRESET_ID
    assert all(win.voice_combo.itemData(i) != "id" for i in range(win.voice_combo.count()))
    assert win.ui_state.layout_mode == "command_deck"
    assert win.ui_state.motion_profile == "cinematic"
    assert win.command_deck_card.property("variant") == "hero"
    assert win.command_status_row.count() >= 3
    assert win.command_state_title.text() == "Awaiting script"
    assert win.narrate_focus_splitter.count() == 2
    assert win.narrate_utility_stack.count() == 2
    assert win.post_suite_card.property("variant") == "command"
    assert win.settings_motion_combo.currentText() == "cinematic"
    win.theme_combo.setCurrentText("obsidian_contrast")
    assert win.settings_theme_combo.currentText() == "obsidian_contrast"
    win.settings_density_combo.setCurrentText("compact")
    assert win.density_combo.currentText() == "compact"
    win.close()


def test_exact_script_mode_uses_auto_duration_and_omits_duration_flag(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win.script_text.setPlainText("This is a deterministic user context script for duration estimation.")
    win.rewrite_combo.setCurrentText("off")
    win.style_combo.setCurrentText("documentary")
    tokens = win._build_narrate_tokens(r"D:\ctx.txt")
    duration_plan = win._current_duration_plan()
    assert "--duration" not in tokens
    assert duration_plan["duration_mode"] == "auto"
    assert duration_plan["requested_target_duration_seconds"] is None
    assert int(duration_plan["estimated_duration_seconds"]) > 0
    assert "Auto from script" in win.duration_mode_value.text()
    assert "~" in win.duration_estimate_value.text()
    win.close()


def test_rewrite_mode_keeps_manual_duration_flag(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win.script_text.setPlainText("Rewrite mode should keep a target duration.")
    win.rewrite_combo.setCurrentText("force")
    win.duration_spin.setValue(75)
    tokens = win._build_narrate_tokens(r"D:\ctx.txt")
    assert "--duration" in tokens
    idx = tokens.index("--duration")
    assert tokens[idx + 1] == "75"
    assert "Manual target" in win.duration_mode_value.text()
    win.close()


def test_launch_narrate_uses_shared_launch_contract(monkeypatch, tmp_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    captured = {}

    def fake_prepare(**kwargs):
        captured["prepare"] = kwargs
        return SimpleNamespace(
            context_file=str(tmp_path / "ctx.txt"),
            cli_tokens=["--mode", "MODE_NARRATE", "--context-file", str(tmp_path / "ctx.txt"), "Create narrated video"],
            arguments=["D:/app/supreme_commander.py", "--mode", "MODE_NARRATE", "--context-file", str(tmp_path / "ctx.txt"), "Create narrated video"],
            payload=SimpleNamespace(schema_version="ui_launch_payload.v2"),
        )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    monkeypatch.setattr("ui.main_window.prepare_narrate_launch", fake_prepare)
    monkeypatch.setattr("ui.main_window.persist_launch_payload", lambda payload, stamp: str(tmp_path / "payload.json"))
    monkeypatch.setattr(win.process, "start", lambda program, args: captured.setdefault("started", (program, list(args))))
    monkeypatch.setattr(win.process, "waitForStarted", lambda timeout: True)
    monkeypatch.setattr(win, "_agent_root_guard", lambda: True)

    win.script_text.setPlainText("A deterministic studio script.")
    win._launch_narrate()

    assert captured["prepare"]["script"] == "A deterministic studio script."
    assert captured["started"][0] == os.sys.executable
    assert captured["started"][1][0] == "D:/app/supreme_commander.py"
    assert captured["started"][1][-1] == "Create narrated video"
    assert win.active_payload_path == str(tmp_path / "payload.json")
    assert win.command_state_title.text() == "Launch in progress"
    win.close()


def test_refresh_live_metrics_attaches_and_pins_active_run(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: ["20260322_000219", "20260321_213328"])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.resolve_active_run_binding",
        lambda **kwargs: {"run_id": "20260322_000219", "source": "fresh_after_launch"},
    )
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda preferred_run_id="": {
            "run_id": preferred_run_id or "20260322_000219",
            "node": "Audio",
            "retries": 0,
            "eta": "00:08",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 14.0,
            "node_detail": "Run attached · waiting for live node telemetry.",
            "node_units_completed": None,
            "node_units_total": None,
            "run_binding_source": "bound",
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    monkeypatch.setattr(
        win.process,
        "state",
        lambda: win.process.ProcessState.Running,
    )
    win.active_known_runs = {"20260321_213328"}
    win.active_launch_stamp = "20260322_000218"
    win._refresh_live_metrics()

    assert win.active_run_id == "20260322_000219"
    assert win.quick_runs_combo.currentText() == "20260322_000219"
    assert win.tile_run.val.text() == "20260322_000219"
    assert win.command_state_title.text() == "Run active"
    win.close()


def test_on_finished_attaches_payload_to_bound_run_before_fallback(monkeypatch, tmp_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: ["20260321_213328"])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda preferred_run_id="": {
            "run_id": preferred_run_id or "20260322_000219",
            "node": "Verifier",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 100.0,
            "node_detail": "Verification clean.",
            "node_units_completed": None,
            "node_units_total": None,
            "run_binding_source": "bound",
        },
    )

    attached = {}
    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    monkeypatch.setattr("ui.main_window.attach_payload_to_run", lambda payload_path, run_id, process_exit_code, ui_state: attached.setdefault("run_id", run_id))
    monkeypatch.setattr(win.live_timer, "stop", lambda: None)
    monkeypatch.setattr(win, "_refresh_run_gallery", lambda: None)
    monkeypatch.setattr(win, "_refresh_post_runs", lambda: None)
    monkeypatch.setattr(win, "_show_toast", lambda *args, **kwargs: None)

    win.active_payload_path = str(tmp_path / "payload.json")
    win.active_run_id = "20260322_000219"
    win._on_finished(0, None)

    assert attached["run_id"] == "20260322_000219"
    win.close()


def test_launch_seed_prefills_narrate_surface(monkeypatch, tmp_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    seed_path = tmp_path / "launch-seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "request_title": "Seeded mission title",
                "script_text": "Seeded exact script for deterministic narration.",
                "narration_style": "sales_saas",
                "context_rewrite": "off",
                "watermark_mode": "on",
                "key_probe": "off",
                "voice_preset": DEFAULT_VOICE_PRESET_ID,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TVC_STUDIO_LAUNCH_SEED_FILE", str(seed_path))

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()

    assert win.request_title.text() == "Seeded mission title"
    assert win.script_text.toPlainText() == "Seeded exact script for deterministic narration."
    assert win.style_combo.currentText() == "sales_saas"
    assert win.rewrite_combo.currentText() == "off"
    assert win.watermark_combo.currentText() == "on"
    assert win.key_probe_combo.currentText() == "off"
    assert win.voice_combo.currentData() == DEFAULT_VOICE_PRESET_ID
    assert win.command_state_title.text() == "Launch armed"
    win.close()


def test_open_latest_run_folder_uses_current_observable_run(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "20260314_151751",
            "node": "Audio",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )
    monkeypatch.setattr("ui.main_window.resolve_current_run_id", lambda: "20260314_151751")

    opened = {}
    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    monkeypatch.setattr(win, "_open_path", lambda path: opened.setdefault("path", path))

    win._open_latest_run_folder()

    assert opened["path"].endswith("20260314_151751")
    win.close()


def test_refresh_live_metrics_populates_progress_and_detail(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "20260314_154954",
            "node": "SotaForge",
            "retries": 1,
            "eta": "00:43",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 78.1,
            "node_detail": "Epoch 8/12 · generating",
            "node_units_completed": 7,
            "node_units_total": 12,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win._refresh_live_metrics()

    assert win.tile_progress.val.text() == "78.1%"
    assert win.lbl_node_detail.text() == "Epoch 8/12 · generating"
    win.close()


def test_refresh_live_metrics_promotes_stage_signal_and_richer_sotaforge_detail(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "20260321_102200",
            "node": "SotaForge",
            "retries": 0,
            "eta": "00:43",
            "api_failures": 1,
            "output_video": "",
            "progress_pct": 78.1,
            "node_detail": "Epoch 8/12 · generating images · ETA 00:43",
            "node_units_completed": 7,
            "node_units_total": 12,
            "node_signal_text": "LIVE COMPUTE",
            "node_signal_tone": "live",
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win._refresh_live_metrics()

    assert win.command_confidence_pill.text() == "LIVE COMPUTE"
    assert "Epoch 8/12" in win.command_state_body.text()
    assert "00:43" in win.command_state_body.text()
    assert win.lbl_node_detail.text() == "Epoch 8/12 · generating images · ETA 00:43"
    win.close()


def test_narrate_stage_choreography_promotes_monitoring(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState())
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win.script_text.setPlainText("A premium deterministic script that should arm the launch deck.")
    win._rebuild_preview()

    assert win.command_state_title.text() == "Launch armed"
    assert win.narrate_utility_stack.currentIndex() == 0

    win._set_narrate_stage("running", detail="SotaForge · Epoch 3/12", progress_pct=41.7)

    assert win.command_state_title.text() == "Run active"
    assert "41.7%" in win.command_state_body.text()
    assert win.narrate_utility_stack.currentIndex() == 1
    assert win.preview_player.state_pill.text() == "RUN ACTIVE"

    win._set_narrate_stage("verified", detail="Verifier clean")

    assert win.command_state_title.text() == "Verified output"
    assert win.preview_player.state_pill.text() == "VERIFIED"
    win.close()


def test_utility_card_visibility_tracks_trace_and_feed_toggles(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()

    assert not win.utility_card.isHidden()
    win._toggle_panel("command_preview", False)
    assert not win.utility_card.isHidden()
    assert win.narrate_utility_stack.currentWidget() is win.feed_console_page
    win._toggle_panel("live_console", False)
    assert win.utility_card.isHidden()
    win._toggle_panel("command_preview", True)
    assert not win.utility_card.isHidden()
    assert win.narrate_utility_stack.currentWidget() is win.trace_console_page
    win.close()


def test_narrate_responsive_layout_stacks_when_narrow(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: [])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState(theme_id="obsidian_contrast", density="cozy"))
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "--",
            "node": "idle",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": "",
            "progress_pct": 0.0,
            "node_detail": "",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win.resize(1366, 768)
    app.processEvents()
    win._sync_narrate_responsive_layout()

    assert win.narrate_layout_mode == "stacked-tight"
    assert win.command_deck_main_layout.direction() == win.command_deck_main_layout.Direction.TopToBottom
    assert win.narrate_focus_splitter.orientation() == Qt.Orientation.Vertical
    assert win.narrate_utility_splitter.orientation() == Qt.Orientation.Vertical
    win.close()


@pytest.mark.parametrize("theme_id", ["obsidian_contrast", "aurora_graphite"])
@pytest.mark.parametrize("density", ["cozy", "compact"])
@pytest.mark.parametrize("size", [(1366, 768), (1600, 900), (1920, 1080), (2560, 1440)])
def test_narrate_overlap_guard_in_stress_layout(monkeypatch, theme_id, density, size):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("ui.main_window.list_run_cards", lambda limit=60: [])
    monkeypatch.setattr("ui.main_window.list_run_ids", lambda: ["verify_nondet_scene_1773229530"])
    monkeypatch.setattr("ui.main_window.list_completed_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr("ui.main_window.load_ui_state", lambda: UIState(theme_id=theme_id, density=density))
    monkeypatch.setattr(
        "ui.main_window.read_live_metrics",
        lambda: {
            "run_id": "20260314_162414_WITH_A_VERY_LONG_IDENTIFIER",
            "node": "Verifier",
            "retries": 0,
            "eta": "--",
            "api_failures": 0,
            "output_video": r"D:\AI-Apps-In-Drive\App_Station\Video_production_agent\emperor_output_1773485653.mp4",
            "progress_pct": 100.0,
            "node_detail": "Verifier clean and latest output ready",
            "node_units_completed": None,
            "node_units_total": None,
        },
    )

    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()
    win.show()
    win.quick_runs_combo.addItem("verify_nondet_scene_1773229530")
    win.quick_runs_combo.setCurrentText("verify_nondet_scene_1773229530")
    win.script_text.setPlainText("A deterministic exact script that arms the deck and fills enough text to produce a meaningful launch summary.")
    win.request_title.setText("Create narrated video from provided script")
    win.resize(*size)
    app.processEvents()
    win._refresh_live_metrics()
    win._rebuild_preview()
    win._sync_narrate_responsive_layout()
    app.processEvents()

    assert not _rect_in(win, win.command_status_wrap).intersects(_rect_in(win, win.command_state_title))
    assert not _rect_in(win, win.command_state_title).intersects(_rect_in(win, win.command_state_body))
    assert not _rect_in(win, win.script_badge_wrap).intersects(_rect_in(win, win.script_guidance))
    assert _rect_in(win, win.mission_title_host).bottom() < _rect_in(win, win.script_text).top()
    assert _rect_in(win, win.preview_player.info).bottom() < _rect_in(win, win.preview_player.preview_surface).top()
    assert _rect_in(win, win.preview_player.controls_host).bottom() < _rect_in(win, win.preview_player.preview_surface).top()
    assert _rect_in(win, win.utility_switch_host).bottom() < _rect_in(win, win.narrate_utility_stack).top()
    assert ".mp4" in win.preview_player.info.text()
    assert win.preview_player.info.full_text().endswith(".mp4")
    win.close()
