from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QDoubleSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from tvc_postproduction import (
    TEXT_STYLE_PRESETS,
    create_post_project,
    list_completed_runs,
    list_text_layers,
    load_project,
    render_post_project,
    reorder_text_layers,
    replace_epoch_image,
    run_ralph_loop,
    update_text_layer,
)
from tvc_duration import DURATION_MODE_AUTO, resolve_duration_plan
from tvc_launch_contract import prepare_narrate_launch, write_context_file, persist_launch_payload
from tvc_voice_registry import DEFAULT_VOICE_PRESET_ID, voice_preset_choices

from .command_palette import CommandPaletteDialog
from .components import AccentButton, ElidedLabel, GlassCard, MetricTile, RunCard, StatusPill, Toast, WrapRow
from .paths import APP_ROOT, COMMANDER_PATH, EXPECTED_ROOT_NAME, RUNS_ROOT
from .services import (
    attach_payload_to_run,
    list_run_cards,
    list_run_ids,
    mark_run_terminal,
    read_live_metrics,
    resolve_current_run_id,
    resolve_latest_run_id,
)
from .state import UIState, load_ui_state, save_ui_state
from .tokens import MOTION_TOKENS, THEMES, app_font, build_stylesheet, headline_font, load_premium_fonts, mono_font

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget

    HAS_MULTIMEDIA = True
except Exception:  # pragma: no cover
    HAS_MULTIMEDIA = False

OFFSCREEN_MODE = str(os.environ.get("QT_QPA_PLATFORM", "") or "").strip().lower() == "offscreen"
if OFFSCREEN_MODE:
    HAS_MULTIMEDIA = False


PAGE_COPY = {
    "NARRATE": (
        "CONTROL ROOM / EXACT SCRIPT",
        "Arm, inspect, and launch deterministic narration from a premium production command deck.",
    ),
    "POST-PRODUCTION": (
        "FINISHING SUITE",
        "Swap visuals, shape layers, and render polished revisions without re-running production.",
    ),
    "RUNS": (
        "MISSION ARCHIVE",
        "Review outputs, health signatures, and fallback pressure across the studio archive.",
    ),
    "SETTINGS": (
        "STUDIO DIRECTIVES",
        "Tune the shell, motion, diagnostics, and workspace comfort without changing launch behavior.",
    ),
}


class VideoPreviewCard(GlassCard):
    def __init__(self, title: str = "Video Preview", variant: str = "subtle", parent=None):
        super().__init__(
            title=title,
            subtitle="In-app review surface for latest output or post-render media.",
            variant=variant,
            parent=parent,
        )
        self.current_path = ""
        state_row = QHBoxLayout()
        self.state_pill = StatusPill("STANDBY", "muted")
        self.state_detail = QLabel("No render attached yet.")
        self.state_detail.setProperty("role", "muted")
        self.state_detail.setWordWrap(True)
        state_row.addWidget(self.state_pill)
        state_row.addWidget(self.state_detail, 1)
        self.layout_root.addLayout(state_row)
        self.info = ElidedLabel("No video loaded")
        self.info.setProperty("role", "muted")
        self.layout_root.addWidget(self.info)

        self.controls_host = WrapRow()
        self.btn_load = QPushButton("Load File")
        self.btn_open = QPushButton("Open External")
        self.controls_host.addWidget(self.btn_load)
        self.controls_host.addWidget(self.btn_open)
        self.layout_root.addWidget(self.controls_host)
        self.playback_controls = None

        self.preview_surface = QFrame()
        self.preview_surface.setObjectName("HeroFacetWell")
        preview_layout = QVBoxLayout(self.preview_surface)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        if HAS_MULTIMEDIA:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(220)
            self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            preview_layout.addWidget(self.video_widget, 1)
            self.audio_out = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_out)
            self.player.setVideoOutput(self.video_widget)
            playback_controls = WrapRow()
            self.btn_play = QPushButton("Play")
            self.btn_pause = QPushButton("Pause")
            self.btn_stop = QPushButton("Stop")
            playback_controls.addWidget(self.btn_play)
            playback_controls.addWidget(self.btn_pause)
            playback_controls.addWidget(self.btn_stop)
            self.playback_controls = playback_controls
            self.layout_root.addWidget(playback_controls)
            self.btn_play.clicked.connect(self.player.play)
            self.btn_pause.clicked.connect(self.player.pause)
            self.btn_stop.clicked.connect(self.player.stop)
        else:
            self.player = None
            note = QLabel("QtMultimedia not available; external open only.")
            note.setProperty("role", "muted")
            note.setWordWrap(True)
            preview_layout.addWidget(note, 1)
        self.preview_surface.setMinimumHeight(220)
        self.layout_root.addWidget(self.preview_surface, 1)

    def set_video(self, path: str):
        path = str(path or "").strip()
        if not path or not os.path.exists(path):
            return
        self.current_path = path
        self.info.set_full_text(path)
        if self.player is not None:
            self.player.setSource(QUrl.fromLocalFile(path))

    def set_state(self, text: str, tone: str = "muted", detail: str = ""):
        self.state_pill.setText(str(text or "STANDBY"))
        self.state_pill.set_tone(tone)
        self.state_detail.setText(str(detail or ""))


class TVCStudioAgentWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.session_id = uuid.uuid4().hex[:12]
        self.ui_state: UIState = load_ui_state()
        self.process = None
        self.active_payload_path = ""
        self.active_known_runs: set = set()
        self.toast_widgets: List[Toast] = []

        self._init_window()
        self._init_process()
        self._build_shell()
        self._apply_ui_state()
        self._bind_shortcuts()
        self._refresh_live_metrics()
        self._refresh_run_gallery()
        self._refresh_post_runs()
        self._rebuild_preview()
        self._show_toast("TVC Studio Agent ready", "success")

    def _init_window(self):
        load_premium_fonts()
        self.setWindowTitle("TVC Studio Agent | SOTA Studio v2")
        self.setMinimumSize(1480, 900)
        self.setObjectName("StudioWindow")
        self.setFont(app_font(self.ui_state.density))
        self._apply_theme_stylesheet()

    def _init_process(self):
        from PyQt6.QtCore import QProcess

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        self.live_timer = QTimer(self)
        self.live_timer.setInterval(2000)
        self.live_timer.timeout.connect(self._refresh_live_metrics)

    def _apply_theme_stylesheet(self):
        self.setStyleSheet(build_stylesheet(self.ui_state.theme_id, self.ui_state.density))

    def _build_shell(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        outer.addWidget(self._build_top_bar())

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.body_splitter, 1)

        self.left_nav = QListWidget()
        self.left_nav.setObjectName("LeftRail")
        self.left_nav.setMinimumWidth(188)
        nav_specs = [
            ("NARRATE", QStyle.StandardPixmap.SP_MediaPlay),
            ("POST-PRODUCTION", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("RUNS", QStyle.StandardPixmap.SP_DirOpenIcon),
            ("SETTINGS", QStyle.StandardPixmap.SP_ComputerIcon),
        ]
        for name, icon_id in nav_specs:
            icon = self.style().standardIcon(icon_id)
            self.left_nav.addItem(QListWidgetItem(icon, name))
        self.left_nav.currentRowChanged.connect(self._on_nav_changed)

        self.left_rail_frame = GlassCard(
            title="Studio Modes",
            subtitle="One command room, four premium workspaces. Launch, finish, audit, and direct the shell from here.",
            eyebrow="NAVIGATION",
            variant="nav",
        )
        self.left_rail_frame.setObjectName("LeftRailFrame")
        self.left_rail_frame.setMinimumWidth(214)
        self.left_rail_frame.setMaximumWidth(236)
        rail_badges = QVBoxLayout()
        rail_badges.setSpacing(6)
        top_badge_row = QHBoxLayout()
        top_badge_row.addWidget(StatusPill("CONTROL ROOM", "live"))
        top_badge_row.addStretch(1)
        bottom_badge_row = QHBoxLayout()
        bottom_badge_row.addWidget(StatusPill("OPS-FIRST", "info"))
        bottom_badge_row.addStretch(1)
        rail_badges.addLayout(top_badge_row)
        rail_badges.addLayout(bottom_badge_row)
        self.left_rail_frame.layout_root.addLayout(rail_badges)
        self.left_rail_frame.layout_root.addWidget(self.left_nav, 1)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        self.page_kicker = QLabel("DETERMINISTIC USER CONTEXT")
        self.page_kicker.setProperty("role", "eyebrow")
        center_layout.addWidget(self.page_kicker)

        self.page_title = QLabel("NARRATE")
        self.page_title.setProperty("role", "pageTitle")
        center_layout.addWidget(self.page_title)

        self.page_subtitle = QLabel(PAGE_COPY["NARRATE"][1])
        self.page_subtitle.setProperty("role", "pageSubtitle")
        self.page_subtitle.setWordWrap(True)
        center_layout.addWidget(self.page_subtitle)

        self.page_stack = QStackedWidget()
        center_layout.addWidget(self.page_stack, 1)

        self.inspector = self._build_inspector()

        self.body_splitter.addWidget(self.left_rail_frame)
        self.body_splitter.addWidget(center)
        self.body_splitter.addWidget(self.inspector)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setStretchFactor(2, 0)
        self.body_splitter.setSizes([220, 1180, 316])

        self.page_stack.addWidget(self._build_page_narrate())
        self.page_stack.addWidget(self._build_page_post())
        self.page_stack.addWidget(self._build_page_runs())
        self.page_stack.addWidget(self._build_page_settings())
        self.left_nav.setCurrentRow(0)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ShellTopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)
        title = QLabel("TVC STUDIO AGENT")
        title.setProperty("role", "shellTitle")
        subtitle = QLabel("Cinematic control room for deterministic launch, live telemetry, and premium finishing.")
        subtitle.setProperty("role", "shellSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        lay.addLayout(title_box)

        self.badge_root = StatusPill("ROOT GUARD", "muted")
        lay.addWidget(self.badge_root)
        self.shell_mode_badge = StatusPill("COMMAND DECK", "live")
        lay.addWidget(self.shell_mode_badge)

        quick_label = QLabel("Mission Log")
        quick_label.setProperty("role", "muted")
        lay.addWidget(quick_label)
        self.quick_runs_combo = QComboBox()
        self.quick_runs_combo.setMinimumWidth(280)
        self.quick_runs_combo.setToolTip("Quick run switch")
        self.quick_runs_combo.currentTextChanged.connect(self._quick_run_selected)
        lay.addWidget(self.quick_runs_combo)

        lay.addStretch(1)

        look_label = QLabel("Theme")
        look_label.setProperty("role", "muted")
        lay.addWidget(look_label)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["aurora_graphite", "obsidian_contrast"])
        self.theme_combo.setCurrentText(self.ui_state.theme_id)
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        lay.addWidget(self.theme_combo)

        density_label = QLabel("Density")
        density_label.setProperty("role", "muted")
        lay.addWidget(density_label)
        self.density_combo = QComboBox()
        self.density_combo.addItems(["cozy", "compact"])
        self.density_combo.setCurrentText(self.ui_state.density)
        self.density_combo.currentTextChanged.connect(self._change_density)
        lay.addWidget(self.density_combo)

        btn_palette = AccentButton("Command Palette (Ctrl+K)", accent_kind="ghost")
        btn_palette.clicked.connect(self._open_command_palette)
        lay.addWidget(btn_palette)
        return bar

    def _build_hud_stat(self, label: str, value: str = "--") -> Tuple[QWidget, QLabel]:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lbl = QLabel(label)
        lbl.setProperty("role", "hudLabel")
        val = QLabel(value)
        val.setProperty("role", "hudValue")
        val.setWordWrap(True)
        lay.addWidget(lbl)
        lay.addWidget(val)
        return host, val

    def _build_inspector(self) -> QWidget:
        panel = GlassCard(
            title="Ops Spine",
            subtitle="Compact live signal for the current or latest run.",
            eyebrow="INSPECTOR",
            variant="subtle",
        )
        panel.setObjectName("InspectorPanel")
        panel.setMinimumWidth(286)
        panel.setMaximumWidth(332)

        self.tile_node = MetricTile("Node", tone="live")
        self.tile_retry = MetricTile("Retries")
        self.tile_fail = MetricTile("API Failures")
        self.tile_eta = MetricTile("ETA")
        self.tile_progress = MetricTile("Progress", tone="live")
        self.tile_run = MetricTile("Run ID")
        grid = QGridLayout()
        grid.addWidget(self.tile_node, 0, 0)
        grid.addWidget(self.tile_retry, 0, 1)
        grid.addWidget(self.tile_fail, 1, 0)
        grid.addWidget(self.tile_eta, 1, 1)
        grid.addWidget(self.tile_progress, 2, 0)
        grid.addWidget(self.tile_run, 2, 1)
        panel.layout_root.addLayout(grid)

        self.lbl_node_detail = QLabel("")
        self.lbl_node_detail.setProperty("role", "muted")
        self.lbl_node_detail.setWordWrap(True)
        panel.layout_root.addWidget(self.lbl_node_detail)

        self.root_status = StatusPill("UNKNOWN", "muted")
        self.process_status = StatusPill("Idle", "info")
        row = QHBoxLayout()
        row.addWidget(self.root_status)
        row.addWidget(self.process_status)
        row.addStretch(1)
        panel.layout_root.addLayout(row)

        output_label = QLabel("Latest Output")
        output_label.setProperty("role", "muted")
        panel.layout_root.addWidget(output_label)
        self.lbl_output = ElidedLabel("--")
        self.lbl_output.setProperty("role", "muted")
        self.lbl_output.setMinimumHeight(26)
        panel.layout_root.addWidget(self.lbl_output)

        btns = QHBoxLayout()
        btn_open_run = QPushButton("Open Run Folder")
        btn_open_run.clicked.connect(self._open_latest_run_folder)
        btn_open_video = AccentButton("Open Video", accent_kind="ghost")
        btn_open_video.clicked.connect(self._open_latest_video)
        btns.addWidget(btn_open_run)
        btns.addWidget(btn_open_video)
        panel.layout_root.addLayout(btns)
        panel.layout_root.addStretch(1)
        return panel

    def _build_page_narrate(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self.narrate_scroll = QScrollArea()
        self.narrate_scroll.setWidgetResizable(True)
        self.narrate_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.narrate_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.narrate_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_layout.addWidget(self.narrate_scroll)

        self.narrate_content = QWidget()
        self.narrate_scroll.setWidget(self.narrate_content)

        root = QVBoxLayout(self.narrate_content)
        root.setContentsMargins(0, 4, 0, 12)
        root.setSpacing(12)
        self.narrate_root_layout = root

        self.command_deck_card = GlassCard(
            title="Launch Deck",
            subtitle="Arm deterministic narration, monitor confidence, and let the live run take over the surface when execution starts.",
            eyebrow="MISSION CONTROL",
            variant="hero",
        )
        self.command_deck_main_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.command_deck_main_layout.setContentsMargins(0, 2, 0, 0)
        self.command_deck_main_layout.setSpacing(18)

        self.command_primary_pill = StatusPill("DETERMINISTIC USER CONTEXT", "live")
        self.command_contract_pill = StatusPill("CONTRACT LOCKED", "success")
        self.command_duration_pill = StatusPill("AUTO DURATION", "info")
        self.command_ready_pill = StatusPill("WARM", "info")
        self.command_status_wrap = WrapRow(h_spacing=8, v_spacing=8)
        self.command_status_wrap.addWidget(self.command_primary_pill)
        self.command_status_wrap.addWidget(self.command_contract_pill)
        self.command_status_wrap.addWidget(self.command_duration_pill)
        self.command_status_wrap.addWidget(self.command_ready_pill)
        self.command_status_row = self.command_status_wrap.layout()

        self.hero_left_host = QFrame()
        self.hero_left_host.setObjectName("HeroNarrativeWell")
        hero_left = QVBoxLayout(self.hero_left_host)
        self.hero_left_layout = hero_left
        hero_left.setContentsMargins(18, 18, 18, 18)
        hero_left.setSpacing(8)
        hero_left.addWidget(self.command_status_wrap)

        self.command_state_label = QLabel("MISSION STATE")
        self.command_state_label.setProperty("role", "heroStateLabel")
        self.command_state_title = QLabel("Awaiting script")
        self.command_state_title.setProperty("role", "heroStateTitle")
        self.command_state_body = QLabel(
            "Provide an exact script to arm the launch contract, payload trace, and deterministic narration path."
        )
        self.command_state_body.setProperty("role", "heroStateBody")
        self.command_state_body.setWordWrap(True)
        self.command_request_title = QLabel("Mission title will appear here when the deck is armed.")
        self.command_request_title.setProperty("role", "heroMeta")
        self.command_request_title.setWordWrap(True)
        hero_left.addWidget(self.command_state_label)
        hero_left.addWidget(self.command_state_title)
        hero_left.addWidget(self.command_state_body)
        hero_left.addWidget(self.command_request_title)

        self.hero_signal_wrap = WrapRow(h_spacing=8, v_spacing=8)
        self.command_root_pill = StatusPill("ROOT PASS", "success")
        self.command_confidence_pill = StatusPill("PAYLOAD VISIBLE", "info")
        self.hero_signal_wrap.addWidget(self.command_root_pill)
        self.hero_signal_wrap.addWidget(self.command_confidence_pill)
        hero_left.addWidget(self.hero_signal_wrap)

        self.command_summary = QLabel("Exact-script launch path with visible payload tokens, auto duration, and progressive telemetry.")
        self.command_summary.setProperty("role", "cardSubtitle")
        self.command_summary.setWordWrap(True)
        hero_left.addWidget(self.command_summary)

        self.btn_launch = AccentButton("Launch NARRATE", accent_kind="success")
        self.btn_abort = QPushButton("Abort")
        self.btn_abort.setEnabled(False)
        self.btn_open_latest_video = AccentButton("Open Latest Video", accent_kind="ghost")
        self.btn_launch.clicked.connect(self._launch_narrate)
        self.btn_abort.clicked.connect(self._abort_run)
        self.btn_open_latest_video.clicked.connect(self._open_latest_video)
        self.command_action_wrap = WrapRow(h_spacing=10, v_spacing=10)
        self.command_action_wrap.addWidget(self.btn_launch)
        self.command_action_wrap.addWidget(self.btn_abort)
        self.command_action_wrap.addWidget(self.btn_open_latest_video)
        hero_left.addWidget(self.command_action_wrap)

        self.hero_right_host = QFrame()
        self.hero_right_host.setObjectName("HeroFacetWell")
        hero_right = QGridLayout(self.hero_right_host)
        self.hero_right_layout = hero_right
        hero_right.setContentsMargins(14, 14, 14, 14)
        hero_right.setHorizontalSpacing(10)
        hero_right.setVerticalSpacing(10)

        self.deck_launch_tile = MetricTile("Launch State", "WARM", tone="live")
        self.deck_contract_tile = MetricTile("Contract", "USER_CONTEXT")
        self.deck_voice_tile = MetricTile("Voice", "--")
        self.deck_style_tile = MetricTile("Style", "DOCUMENTARY")
        self.deck_duration_tile = MetricTile("Duration", "AUTO")
        self.deck_progress_tile = MetricTile("Progress", "0.0%")
        self.deck_output_tile = MetricTile("Output", "WAITING")
        hero_right.addWidget(self.deck_launch_tile, 0, 0)
        hero_right.addWidget(self.deck_contract_tile, 0, 1)
        hero_right.addWidget(self.deck_voice_tile, 1, 0)
        hero_right.addWidget(self.deck_style_tile, 1, 1)
        hero_right.addWidget(self.deck_duration_tile, 2, 0)
        hero_right.addWidget(self.deck_progress_tile, 2, 1)
        hero_right.addWidget(self.deck_output_tile, 3, 0, 1, 2)

        self.command_deck_main_layout.addWidget(self.hero_left_host, 3)
        self.command_deck_main_layout.addWidget(self.hero_right_host, 2)
        self.command_deck_card.layout_root.addLayout(self.command_deck_main_layout)

        card_script = GlassCard(
            title="Script Studio",
            subtitle="Author the exact script that powers the deterministic launch contract. No hidden prompt assembly sits behind this surface.",
            eyebrow="SOURCE",
            variant="subtle",
        )
        self.card_script = card_script
        self.script_badge_wrap = WrapRow(h_spacing=8, v_spacing=8)
        self.script_source = StatusPill("USER_CONTEXT", "info")
        self.script_stats = QLabel("0 words | 0 lines")
        self.script_stats.setProperty("role", "muted")
        self.script_hint = StatusPill("AUTHORING LOCK", "muted")
        self.script_badge_wrap.addWidget(self.script_source)
        self.script_badge_wrap.addWidget(self.script_stats)
        self.script_badge_wrap.addWidget(self.script_hint)
        card_script.layout_root.addWidget(self.script_badge_wrap)
        self.script_guidance = QLabel("Paste a script to arm the deck and unlock launch readiness.")
        self.script_guidance.setProperty("role", "cardSubtitle")
        self.script_guidance.setWordWrap(True)
        card_script.layout_root.addWidget(self.script_guidance)
        self.mission_title_host = QWidget()
        req_row = QHBoxLayout(self.mission_title_host)
        req_row.setContentsMargins(0, 0, 0, 0)
        req_row.setSpacing(10)
        req_label = QLabel("Mission Title")
        req_label.setProperty("role", "sectionLabel")
        req_row.addWidget(req_label)
        self.request_title = QLineEdit("Create narrated video from provided script")
        self.request_title.textChanged.connect(self._rebuild_preview)
        req_row.addWidget(self.request_title, 1)
        card_script.layout_root.addWidget(self.mission_title_host)
        self.script_text = QPlainTextEdit()
        self.script_text.setProperty("role", "editor")
        self.script_text.setPlaceholderText("Paste your USER_CONTEXT script here...")
        self.script_text.textChanged.connect(self._rebuild_preview)
        self.script_text.setMinimumHeight(280)
        card_script.layout_root.addWidget(self.script_text, 1)

        self.preview_player = VideoPreviewCard("Output Monitor", variant="archive")
        self.preview_player.set_state("STANDBY", "muted", "Latest output will land here. During a run, this surface leans into monitoring.")
        self.preview_player.btn_load.clicked.connect(self._pick_preview_video)
        self.preview_player.btn_open.clicked.connect(self._open_preview_external)

        self.narrate_focus_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.narrate_focus_splitter.addWidget(card_script)
        self.narrate_focus_splitter.addWidget(self.preview_player)
        self.narrate_focus_splitter.setChildrenCollapsible(False)
        self.narrate_focus_splitter.setStretchFactor(0, 3)
        self.narrate_focus_splitter.setStretchFactor(1, 2)

        card_runtime = GlassCard(
            title="Launch Controls",
            subtitle="Tune the narration contract, voice direction, and runtime policy without losing the deterministic launch path.",
            eyebrow="CONTROL",
            variant="subtle",
        )
        self.card_runtime = card_runtime
        rt = QGridLayout()
        rt.setHorizontalSpacing(12)
        rt.setVerticalSpacing(8)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(10, 600)
        self.duration_spin.setValue(60)
        self.duration_spin.valueChanged.connect(self._rebuild_preview)
        self.duration_mode_value = QLabel("Auto from script")
        self.duration_mode_value.setProperty("role", "title")
        self.duration_estimate_value = QLabel("Waiting for script...")
        self.duration_estimate_value.setProperty("role", "muted")
        auto_duration_widget = QWidget()
        auto_duration_layout = QVBoxLayout(auto_duration_widget)
        auto_duration_layout.setContentsMargins(0, 0, 0, 0)
        auto_duration_layout.setSpacing(2)
        auto_duration_layout.addWidget(self.duration_mode_value)
        auto_duration_layout.addWidget(self.duration_estimate_value)
        manual_duration_widget = QWidget()
        manual_duration_layout = QVBoxLayout(manual_duration_widget)
        manual_duration_layout.setContentsMargins(0, 0, 0, 0)
        manual_duration_layout.setSpacing(2)
        manual_duration_layout.addWidget(self.duration_spin)
        self.duration_stack = QStackedWidget()
        self.duration_stack.addWidget(auto_duration_widget)
        self.duration_stack.addWidget(manual_duration_widget)
        self.style_combo = QComboBox()
        self.style_combo.addItems(["documentary", "sales_saas", "human_story"])
        self.style_combo.currentTextChanged.connect(self._rebuild_preview)
        self.rewrite_combo = QComboBox()
        self.rewrite_combo.addItems(["off", "force"])
        self.rewrite_combo.currentTextChanged.connect(self._rebuild_preview)
        self.watermark_combo = QComboBox()
        self.watermark_combo.addItems(["on", "off"])
        self.watermark_combo.currentTextChanged.connect(self._rebuild_preview)
        self.voice_combo = QComboBox()
        for choice in voice_preset_choices():
            vid = str(choice.get("id", "") or "").strip()
            label = str(choice.get("label", vid) or vid).strip()
            if not vid:
                continue
            self.voice_combo.addItem(f"{label} ({vid})", userData=vid)
        self._set_default_voice()
        self.voice_combo.currentIndexChanged.connect(self._rebuild_preview)
        self.key_probe_combo = QComboBox()
        self.key_probe_combo.addItems(["off", "on"])
        self.key_probe_combo.currentTextChanged.connect(self._rebuild_preview)

        rt.addWidget(self._section_label("Narration Contract"), 0, 0, 1, 2)
        rt.addWidget(self._field_label("Duration"), 1, 0)
        rt.addWidget(self.duration_stack, 1, 1)
        rt.addWidget(self._field_label("Context Rewrite"), 2, 0)
        rt.addWidget(self.rewrite_combo, 2, 1)
        rt.addWidget(self._section_label("Voice Direction"), 3, 0, 1, 2)
        rt.addWidget(self._field_label("Style"), 4, 0)
        rt.addWidget(self.style_combo, 4, 1)
        rt.addWidget(self._field_label("Voice Preset"), 5, 0)
        rt.addWidget(self.voice_combo, 5, 1)
        rt.addWidget(self._section_label("Runtime Policy"), 6, 0, 1, 2)
        rt.addWidget(self._field_label("Watermark"), 7, 0)
        rt.addWidget(self.watermark_combo, 7, 1)
        rt.addWidget(self._field_label("Key Probe"), 8, 0)
        rt.addWidget(self.key_probe_combo, 8, 1)
        card_runtime.layout_root.addLayout(rt)

        self.chk_show_preview = QCheckBox("Show payload trace")
        self.chk_show_preview.setChecked(self.ui_state.panel_visibility.get("command_preview", True))
        self.chk_show_preview.toggled.connect(self._toggle_preview_panel)
        card_runtime.layout_root.addWidget(self.chk_show_preview)

        self.utility_card = GlassCard(
            title="Operational Trace",
            subtitle="Progressive reveal for payload trace and execution feed. The surface auto-promotes monitoring while a run is active.",
            eyebrow="UTILITY BAND",
            variant="archive",
        )
        self.preview_text = QPlainTextEdit()
        self.preview_text.setProperty("role", "console")
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(mono_font(9))
        self.preview_text.setMinimumHeight(220)

        self.log_console = QTextBrowser()
        self.log_console.setProperty("role", "console")
        self.log_console.setFont(mono_font(9))
        self.log_console.setMinimumHeight(220)

        self.utility_switch_host = QWidget()
        switch_row = QHBoxLayout(self.utility_switch_host)
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.setSpacing(8)
        self.utility_trace_button = QPushButton("Payload Trace")
        self.utility_trace_button.setProperty("segment", True)
        self.utility_feed_button = QPushButton("Execution Feed")
        self.utility_feed_button.setProperty("segment", True)
        self.utility_trace_button.clicked.connect(lambda: self._set_narrate_utility_mode("trace"))
        self.utility_feed_button.clicked.connect(lambda: self._set_narrate_utility_mode("feed"))
        switch_row.addWidget(self.utility_trace_button)
        switch_row.addWidget(self.utility_feed_button)
        switch_row.addStretch(1)
        self.utility_card.layout_root.addWidget(self.utility_switch_host)

        self.trace_console_page = QWidget()
        trace_layout = QVBoxLayout(self.trace_console_page)
        trace_layout.setContentsMargins(0, 0, 0, 0)
        trace_layout.setSpacing(6)
        trace_hint = QLabel("Resolved CLI-equivalent launch contract assembled by the shell before commander launch.")
        trace_hint.setProperty("role", "muted")
        trace_hint.setWordWrap(True)
        trace_layout.addWidget(trace_hint)
        trace_layout.addWidget(self.preview_text, 1)

        self.feed_console_page = QWidget()
        feed_layout = QVBoxLayout(self.feed_console_page)
        feed_layout.setContentsMargins(0, 0, 0, 0)
        feed_layout.setSpacing(6)
        feed_hint = QLabel("Commander output, node progress, and intervention-ready context while a run is active.")
        feed_hint.setProperty("role", "muted")
        feed_hint.setWordWrap(True)
        feed_layout.addWidget(feed_hint)
        feed_layout.addWidget(self.log_console, 1)

        self.narrate_utility_stack = QStackedWidget()
        self.narrate_utility_stack.addWidget(self.trace_console_page)
        self.narrate_utility_stack.addWidget(self.feed_console_page)
        self.utility_card.layout_root.addWidget(self.narrate_utility_stack, 1)

        self.narrate_utility_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.narrate_utility_splitter.addWidget(card_runtime)
        self.narrate_utility_splitter.addWidget(self.utility_card)
        self.narrate_utility_splitter.setChildrenCollapsible(False)
        self.narrate_utility_splitter.setStretchFactor(0, 2)
        self.narrate_utility_splitter.setStretchFactor(1, 3)

        root.addWidget(self.command_deck_card, 0)
        root.addWidget(self.narrate_focus_splitter, 5)
        root.addWidget(self.narrate_utility_splitter, 3)
        self.card_preview = self.utility_card
        self._set_narrate_utility_mode("trace")
        self._refresh_narrate_utility_visibility()
        self.narrate_stage_mode = "empty"
        self.narrate_layout_mode = "wide"
        self._sync_narrate_responsive_layout()
        return page

    def _build_page_post(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(12)

        self.post_suite_card = GlassCard(
            title="Finishing Command Suite",
            subtitle="Attach a run to an editable layer project, review project readiness, and keep all render work non-destructive.",
            eyebrow="PROJECT COMMAND",
            variant="command",
        )
        row = QGridLayout()
        self.post_runs_combo = QComboBox()
        self.post_refresh_btn = QPushButton("Refresh")
        self.post_create_btn = AccentButton("Create Project", accent_kind="success")
        self.post_project_path = QLineEdit()
        self.post_project_path.setReadOnly(True)
        row.addWidget(QLabel("Run"), 0, 0)
        row.addWidget(self.post_runs_combo, 0, 1)
        row.addWidget(self.post_refresh_btn, 0, 2)
        row.addWidget(self.post_create_btn, 1, 0, 1, 3)
        row.addWidget(QLabel("Project Path"), 2, 0)
        row.addWidget(self.post_project_path, 2, 1, 1, 2)
        self.post_project_metric = MetricTile("Project", "UNBOUND", tone="live")
        self.post_layer_metric = MetricTile("Layers", "0")
        self.post_render_metric = MetricTile("Render", "READY")
        self.post_loop_metric = MetricTile("Ralph", "4 max")
        suite_metrics = QGridLayout()
        suite_metrics.addWidget(self.post_project_metric, 0, 0)
        suite_metrics.addWidget(self.post_layer_metric, 0, 1)
        suite_metrics.addWidget(self.post_render_metric, 1, 0)
        suite_metrics.addWidget(self.post_loop_metric, 1, 1)
        suite_host = QWidget()
        suite_host.setLayout(suite_metrics)
        suite_shell = QGridLayout()
        suite_shell.addLayout(row, 0, 0)
        suite_shell.addWidget(suite_host, 0, 1)
        suite_shell.setColumnStretch(0, 3)
        suite_shell.setColumnStretch(1, 2)
        self.post_suite_card.layout_root.addLayout(suite_shell)
        self.post_refresh_btn.clicked.connect(self._refresh_post_runs)
        self.post_create_btn.clicked.connect(self._create_post_project)

        card_media = GlassCard(
            title="Media Surgery",
            subtitle="Replace epoch visuals surgically without regenerating the pipeline.",
            eyebrow="MEDIA",
            variant="archive",
        )
        media_grid = QGridLayout()
        self.replace_epoch_spin = QSpinBox()
        self.replace_epoch_spin.setRange(1, 9999)
        self.replace_path = QLineEdit()
        btn_pick = QPushButton("Browse")
        btn_apply = QPushButton("Apply")
        btn_pick.clicked.connect(self._browse_replace_image)
        btn_apply.clicked.connect(self._apply_replace_image)
        media_grid.addWidget(QLabel("Epoch"), 0, 0)
        media_grid.addWidget(self.replace_epoch_spin, 0, 1)
        media_grid.addWidget(QLabel("Image"), 1, 0)
        media_grid.addWidget(self.replace_path, 1, 1)
        media_grid.addWidget(btn_pick, 1, 2)
        media_grid.addWidget(btn_apply, 2, 0, 1, 3)
        card_media.layout_root.addLayout(media_grid)

        card_layers = GlassCard(
            title="Timeline / Layers",
            subtitle="Edit text styles, motion curves, and ordering inside the finishing timeline.",
            eyebrow="LAYERS",
            variant="subtle",
        )
        layers_grid = QGridLayout()
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.layer_list.currentItemChanged.connect(self._on_layer_selected)
        self.layer_style = QComboBox()
        self.layer_style.addItems(list(TEXT_STYLE_PRESETS.keys()))
        self.layer_style.currentTextChanged.connect(self._update_style_preview)
        self.layer_text = QLineEdit()
        self.layer_start = QDoubleSpinBox()
        self.layer_end = QDoubleSpinBox()
        self.layer_start.setRange(0.0, 9999.0)
        self.layer_end.setRange(0.0, 9999.0)
        self.layer_start.setDecimals(2)
        self.layer_end.setDecimals(2)

        self.motion_in_curve = QComboBox()
        self.motion_in_curve.addItems(["linear", "cubic", "expo"])
        self.motion_out_curve = QComboBox()
        self.motion_out_curve.addItems(["linear", "cubic", "expo"])
        self.motion_in_ms = QSpinBox()
        self.motion_in_ms.setRange(0, 3000)
        self.motion_in_ms.setValue(180)
        self.motion_out_ms = QSpinBox()
        self.motion_out_ms.setRange(0, 3000)
        self.motion_out_ms.setValue(180)
        self.motion_opacity = QSpinBox()
        self.motion_opacity.setRange(0, 100)
        self.motion_opacity.setValue(100)
        self.motion_blur = QDoubleSpinBox()
        self.motion_blur.setRange(0.0, 10.0)
        self.motion_blur.setSingleStep(0.1)
        self.motion_blur.setValue(0.6)
        self.motion_offset_x = QSpinBox()
        self.motion_offset_x.setRange(-2000, 2000)
        self.motion_offset_y = QSpinBox()
        self.motion_offset_y.setRange(-2000, 2000)

        self.style_preview = QLabel("Style Preview")
        self.style_preview.setProperty("role", "muted")
        self.style_catalog = QTextBrowser()
        self.style_catalog.setProperty("role", "console")
        self.style_catalog.setMaximumHeight(130)
        self.style_catalog.setFont(mono_font(8))
        catalog_lines = []
        for name, cfg in TEXT_STYLE_PRESETS.items():
            catalog_lines.append(f"- {name}  |  {cfg.get('anchor')} / {cfg.get('effect')}")
        self.style_catalog.setPlainText("\n".join(catalog_lines))

        btn_update_layer = QPushButton("Update Layer")
        btn_save_order = QPushButton("Save Layer Order")
        btn_reload_layers = QPushButton("Reload Layers")
        btn_update_layer.clicked.connect(self._apply_layer_edit)
        btn_save_order.clicked.connect(self._save_layer_order)
        btn_reload_layers.clicked.connect(self._load_project_layers)

        layers_grid.addWidget(self.layer_list, 0, 0, 8, 1)
        layers_grid.addWidget(QLabel("Style"), 0, 1)
        layers_grid.addWidget(self.layer_style, 0, 2)
        layers_grid.addWidget(self.style_preview, 1, 1, 1, 2)
        layers_grid.addWidget(QLabel("Text"), 2, 1)
        layers_grid.addWidget(self.layer_text, 2, 2)
        layers_grid.addWidget(QLabel("Start"), 3, 1)
        layers_grid.addWidget(self.layer_start, 3, 2)
        layers_grid.addWidget(QLabel("End"), 4, 1)
        layers_grid.addWidget(self.layer_end, 4, 2)
        layers_grid.addWidget(QLabel("In / Out Curve"), 5, 1)
        curve_row = QHBoxLayout()
        curve_row.addWidget(self.motion_in_curve)
        curve_row.addWidget(self.motion_out_curve)
        curve_w = QWidget()
        curve_w.setLayout(curve_row)
        layers_grid.addWidget(curve_w, 5, 2)
        layers_grid.addWidget(QLabel("In / Out ms"), 6, 1)
        ms_row = QHBoxLayout()
        ms_row.addWidget(self.motion_in_ms)
        ms_row.addWidget(self.motion_out_ms)
        ms_w = QWidget()
        ms_w.setLayout(ms_row)
        layers_grid.addWidget(ms_w, 6, 2)
        layers_grid.addWidget(QLabel("Opacity / Blur"), 7, 1)
        ob_row = QHBoxLayout()
        ob_row.addWidget(self.motion_opacity)
        ob_row.addWidget(self.motion_blur)
        ob_w = QWidget()
        ob_w.setLayout(ob_row)
        layers_grid.addWidget(ob_w, 7, 2)
        layers_grid.addWidget(QLabel("Offset X / Y"), 8, 1)
        off_row = QHBoxLayout()
        off_row.addWidget(self.motion_offset_x)
        off_row.addWidget(self.motion_offset_y)
        off_w = QWidget()
        off_w.setLayout(off_row)
        layers_grid.addWidget(off_w, 8, 2)
        layers_grid.addWidget(self.style_catalog, 9, 1, 1, 2)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_update_layer)
        btn_row.addWidget(btn_save_order)
        btn_row.addWidget(btn_reload_layers)
        btn_row.addStretch(1)
        brw = QWidget()
        brw.setLayout(btn_row)
        layers_grid.addWidget(brw, 10, 0, 1, 3)
        card_layers.layout_root.addLayout(layers_grid)

        card_render = GlassCard(
            title="Render Control",
            subtitle="Rebuild the edited output and run bounded Ralph correction loops from the same command surface.",
            eyebrow="QUALITY LOOP",
            variant="command",
        )
        ren = QGridLayout()
        self.btn_render_post = AccentButton("Render Post Project", accent_kind="success")
        self.btn_ralph = QPushButton("Run Ralph Loop")
        self.spin_ralph = QSpinBox()
        self.spin_ralph.setRange(1, 8)
        self.spin_ralph.setValue(4)
        self.post_log = QTextBrowser()
        self.post_log.setProperty("role", "console")
        self.post_log.setFont(mono_font(9))
        self.post_log.setMinimumHeight(160)
        self.btn_render_post.clicked.connect(self._render_post_project)
        self.btn_ralph.clicked.connect(self._run_ralph)
        ren.addWidget(self.btn_render_post, 0, 0)
        ren.addWidget(QLabel("Max loops"), 0, 1)
        ren.addWidget(self.spin_ralph, 0, 2)
        ren.addWidget(self.btn_ralph, 0, 3)
        ren.addWidget(self.post_log, 1, 0, 1, 4)
        card_render.layout_root.addLayout(ren)

        self.post_preview = VideoPreviewCard("Post-Render Preview", variant="archive")
        self.post_preview.btn_load.clicked.connect(self._pick_preview_video)
        self.post_preview.btn_open.clicked.connect(self._open_preview_external)

        grid.addWidget(self.post_suite_card, 0, 0, 1, 3)
        grid.addWidget(card_media, 1, 0, 1, 1)
        grid.addWidget(card_render, 1, 1, 1, 2)
        grid.addWidget(card_layers, 2, 0, 1, 2)
        grid.addWidget(self.post_preview, 2, 2, 1, 1)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(2, 1)
        return page

    def _build_page_runs(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        overview = GlassCard(
            title="Mission Archive",
            subtitle="Snapshot of recent outputs, verifier state, and fallback pressure across the studio archive.",
            eyebrow="ARCHIVE",
            variant="command",
        )
        overview_grid = QGridLayout()
        self.run_tile_total = MetricTile("Runs", tone="live")
        self.run_tile_verified = MetricTile("Verified", tone="success")
        self.run_tile_fallbacks = MetricTile("Fallbacks")
        overview_grid.addWidget(self.run_tile_total, 0, 0)
        overview_grid.addWidget(self.run_tile_verified, 0, 1)
        overview_grid.addWidget(self.run_tile_fallbacks, 0, 2)
        overview.layout_root.addLayout(overview_grid)
        lay.addWidget(overview)

        controls = QHBoxLayout()
        self.run_search = QLineEdit()
        self.run_search.setPlaceholderText("Search runs...")
        self.run_search.textChanged.connect(self._refresh_run_gallery)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_run_gallery)
        controls.addWidget(self.run_search, 1)
        controls.addWidget(btn_refresh)
        lay.addLayout(controls)

        self.run_scroll = QScrollArea()
        self.run_scroll.setWidgetResizable(True)
        self.run_grid_host = QWidget()
        self.run_grid = QGridLayout(self.run_grid_host)
        self.run_grid.setSpacing(10)
        self.run_scroll.setWidget(self.run_grid_host)
        lay.addWidget(self.run_scroll, 1)
        return page

    def _build_page_settings(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        card_studio = GlassCard(
            title="Studio Directives",
            subtitle="Theme, motion profile, and control-room layout directives for this shell only.",
            eyebrow="STUDIO",
            variant="command",
        )
        studio_grid = QGridLayout()
        studio_grid.addWidget(QLabel("Theme"), 0, 0)
        self.settings_theme_combo = QComboBox()
        self.settings_theme_combo.addItems(["aurora_graphite", "obsidian_contrast"])
        self.settings_theme_combo.setCurrentText(self.ui_state.theme_id)
        self.settings_theme_combo.currentTextChanged.connect(self._change_theme)
        studio_grid.addWidget(self.settings_theme_combo, 0, 1)
        studio_grid.addWidget(QLabel("Density"), 1, 0)
        self.settings_density_combo = QComboBox()
        self.settings_density_combo.addItems(["cozy", "compact"])
        self.settings_density_combo.setCurrentText(self.ui_state.density)
        self.settings_density_combo.currentTextChanged.connect(self._change_density)
        studio_grid.addWidget(self.settings_density_combo, 1, 1)
        studio_grid.addWidget(QLabel("Performance Mode"), 2, 0)
        self.performance_combo = QComboBox()
        self.performance_combo.addItems(["balanced", "smooth", "battery"])
        self.performance_combo.setCurrentText(self.ui_state.performance_mode)
        self.performance_combo.currentTextChanged.connect(self._change_performance_mode)
        studio_grid.addWidget(self.performance_combo, 2, 1)
        studio_grid.addWidget(QLabel("Motion Profile"), 3, 0)
        self.settings_motion_combo = QComboBox()
        self.settings_motion_combo.addItems(["cinematic", "focused", "calm"])
        self.settings_motion_combo.setCurrentText(self.ui_state.motion_profile)
        self.settings_motion_combo.currentTextChanged.connect(self._change_motion_profile)
        studio_grid.addWidget(self.settings_motion_combo, 3, 1)
        studio_grid.addWidget(QLabel("Layout Mode"), 4, 0)
        self.settings_layout_combo = QComboBox()
        self.settings_layout_combo.addItems(["command_deck", "balanced_shell"])
        self.settings_layout_combo.setCurrentText(self.ui_state.layout_mode)
        self.settings_layout_combo.currentTextChanged.connect(self._change_layout_mode)
        studio_grid.addWidget(self.settings_layout_combo, 4, 1)
        studio_grid.addWidget(QLabel("Inspector Density"), 5, 0)
        self.inspector_density_combo = QComboBox()
        self.inspector_density_combo.addItems(["comfortable", "compact"])
        self.inspector_density_combo.setCurrentText(self.ui_state.inspector_density)
        self.inspector_density_combo.currentTextChanged.connect(self._change_inspector_density)
        studio_grid.addWidget(self.inspector_density_combo, 5, 1)
        self.chk_reduced_motion = QCheckBox("Reduce motion and shell animation")
        self.chk_reduced_motion.setChecked(self.ui_state.reduced_motion)
        self.chk_reduced_motion.toggled.connect(self._change_reduced_motion)
        studio_grid.addWidget(self.chk_reduced_motion, 6, 0, 1, 2)
        card_studio.layout_root.addLayout(studio_grid)

        card_layout = GlassCard(
            title="Workspace Surfaces",
            subtitle="Show or hide persistent chrome panels without changing the underlying launch contract.",
            eyebrow="LAYOUT",
            variant="subtle",
        )
        layout_grid = QGridLayout()
        self.chk_left_nav = QCheckBox("Show left rail")
        self.chk_left_nav.setChecked(self.ui_state.panel_visibility.get("left_nav", True))
        self.chk_right = QCheckBox("Show right inspector")
        self.chk_right.setChecked(self.ui_state.panel_visibility.get("right_inspector", True))
        self.chk_preview = QCheckBox("Show command preview panel")
        self.chk_preview.setChecked(self.ui_state.panel_visibility.get("command_preview", True))
        self.chk_video_preview = QCheckBox("Show video preview panel")
        self.chk_video_preview.setChecked(self.ui_state.panel_visibility.get("video_preview", True))
        self.chk_live_console = QCheckBox("Show live console")
        self.chk_live_console.setChecked(self.ui_state.panel_visibility.get("live_console", True))

        self.chk_left_nav.toggled.connect(lambda v: self._toggle_panel("left_nav", v))
        self.chk_right.toggled.connect(lambda v: self._toggle_panel("right_inspector", v))
        self.chk_preview.toggled.connect(lambda v: self._toggle_panel("command_preview", v))
        self.chk_video_preview.toggled.connect(lambda v: self._toggle_panel("video_preview", v))
        self.chk_live_console.toggled.connect(lambda v: self._toggle_panel("live_console", v))

        layout_grid.addWidget(self.chk_left_nav, 0, 0)
        layout_grid.addWidget(self.chk_right, 0, 1)
        layout_grid.addWidget(self.chk_preview, 1, 0)
        layout_grid.addWidget(self.chk_video_preview, 1, 1)
        layout_grid.addWidget(self.chk_live_console, 2, 0)
        card_layout.layout_root.addLayout(layout_grid)

        card_diag = GlassCard(
            title="Diagnostics",
            subtitle="Agent-root assertion and launcher path visibility for rapid sanity checks.",
            eyebrow="DIAGNOSTICS",
            variant="subtle",
        )
        diag = QTextBrowser()
        diag.setProperty("role", "console")
        diag.setFont(mono_font(9))
        diag.setMinimumHeight(150)
        diag.setPlainText(
            "\n".join(
                [
                    f"APP_ROOT: {APP_ROOT}",
                    f"COMMANDER: {COMMANDER_PATH}",
                    f"ROOT_GUARD: {'PASS' if self._agent_root_guard() else 'FAIL'}",
                    "Legacy UI untouched by design.",
                ]
            )
        )
        card_diag.layout_root.addWidget(diag)

        card_desktop = GlassCard(
            title="Desktop Integration",
            subtitle="Generate the agent-only shortcut and keep launch entry points explicit.",
            eyebrow="INTEGRATION",
            variant="subtle",
        )
        btn_shortcut = AccentButton("Create Desktop Shortcut")
        btn_shortcut.clicked.connect(self._create_shortcut)
        desktop_note = QLabel("Shortcut target remains pinned to Video_production_agent only.")
        desktop_note.setProperty("role", "muted")
        card_desktop.layout_root.addWidget(btn_shortcut)
        card_desktop.layout_root.addWidget(desktop_note)

        grid.addWidget(card_studio, 0, 0, 1, 2)
        grid.addWidget(card_layout, 1, 0, 1, 1)
        grid.addWidget(card_desktop, 1, 1, 1, 1)
        grid.addWidget(card_diag, 2, 0, 1, 2)
        grid.setRowStretch(2, 1)
        return page

    # ---------- Interaction ----------
    def _bind_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._open_command_palette)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._refresh_run_gallery)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._launch_narrate)

        act_open = QAction("Open Latest Video", self)
        act_open.triggered.connect(self._open_latest_video)
        self.addAction(act_open)

    def _open_command_palette(self):
        commands: List[Tuple[str, callable]] = [
            ("Launch NARRATE", self._launch_narrate),
            ("Abort Active Run", self._abort_run),
            ("Refresh Run Gallery", self._refresh_run_gallery),
            ("Open Latest Run Folder", self._open_latest_run_folder),
            ("Create Post Project", self._create_post_project),
            ("Render Post Project", self._render_post_project),
            ("Run Ralph Loop", self._run_ralph),
            ("Switch Theme", self._cycle_theme),
            ("Toggle Inspector", lambda: self._toggle_panel("right_inspector", not self.inspector.isVisible())),
        ]
        dlg = CommandPaletteDialog(commands, self)
        dlg.exec()

    def _cycle_theme(self):
        keys = list(THEMES.keys())
        cur = self.ui_state.theme_id
        idx = keys.index(cur) if cur in keys else 0
        self.theme_combo.setCurrentText(keys[(idx + 1) % len(keys)])

    def _page_copy(self, name: str) -> Tuple[str, str]:
        return PAGE_COPY.get(name, ("STUDIO", "Agent-only TVC shell."))

    def _motion_duration(self, token: str) -> int:
        base = int(MOTION_TOKENS.get(token, 0))
        if self.ui_state.reduced_motion or self.ui_state.performance_mode == "battery":
            return 0
        profile_scale = {
            "cinematic": 1.0,
            "focused": 0.82,
            "calm": 1.12,
        }.get(str(self.ui_state.motion_profile or "cinematic"), 1.0)
        base = int(base * profile_scale)
        if self.ui_state.performance_mode == "smooth":
            return int(base * 1.2)
        return base

    def _set_process_pill(self, text: str, tone: str):
        self.process_status.setText(text)
        self.process_status.set_tone(tone)
        if hasattr(self, "command_ready_pill"):
            self.command_ready_pill.setText(str(text).upper())
            self.command_ready_pill.set_tone("live" if tone == "info" else tone)

    def _on_nav_changed(self, index: int):
        index = max(0, min(self.page_stack.count() - 1, index))
        self.page_stack.setCurrentIndex(index)
        name = self.left_nav.item(index).text() if self.left_nav.item(index) else "TVC"
        eyebrow, subtitle = self._page_copy(name)
        self.page_kicker.setText(eyebrow)
        self.page_title.setText(name)
        self.page_subtitle.setText(subtitle)
        if hasattr(self, "shell_mode_badge"):
            self.shell_mode_badge.setText("COMMAND DECK" if name == "NARRATE" else name.replace("-", " "))
        self._animate_page(self.page_stack.currentWidget())

    def _animate_page(self, widget: QWidget):
        duration = self._motion_duration("panel_ms")
        if duration <= 0:
            widget.setGraphicsEffect(None)
            return
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.15)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        widget._page_anim = anim

    def _change_theme(self, theme_id: str):
        self.ui_state.theme_id = str(theme_id or "aurora_graphite")
        for combo in [self.theme_combo, getattr(self, "settings_theme_combo", None)]:
            if combo is not None and combo.currentText() != self.ui_state.theme_id:
                combo.blockSignals(True)
                combo.setCurrentText(self.ui_state.theme_id)
                combo.blockSignals(False)
        self._apply_theme_stylesheet()
        if hasattr(self, "command_state_title"):
            self._stabilize_narrate_layout()
        self._show_toast(f"Theme set: {self.ui_state.theme_id}", "info")

    def _change_density(self, density: str):
        self.ui_state.density = str(density or "cozy")
        for combo in [self.density_combo, getattr(self, "settings_density_combo", None)]:
            if combo is not None and combo.currentText() != self.ui_state.density:
                combo.blockSignals(True)
                combo.setCurrentText(self.ui_state.density)
                combo.blockSignals(False)
        self.setFont(app_font(self.ui_state.density))
        self._apply_theme_stylesheet()
        if hasattr(self, "command_state_title"):
            self._stabilize_narrate_layout()

    def _change_performance_mode(self, mode: str):
        self.ui_state.performance_mode = str(mode or "balanced")
        self._show_toast(f"Performance mode: {self.ui_state.performance_mode}", "info")

    def _change_motion_profile(self, profile: str):
        self.ui_state.motion_profile = str(profile or "cinematic")
        self._show_toast(f"Motion profile: {self.ui_state.motion_profile}", "info")

    def _change_layout_mode(self, mode: str):
        self.ui_state.layout_mode = str(mode or "command_deck")
        self._show_toast(f"Layout mode: {self.ui_state.layout_mode}", "info")
        if hasattr(self, "command_state_title"):
            self._stabilize_narrate_layout()

    def _change_reduced_motion(self, enabled: bool):
        self.ui_state.reduced_motion = bool(enabled)
        self._show_toast("Reduced motion enabled" if enabled else "Reduced motion disabled", "info")

    def _change_inspector_density(self, density: str):
        self.ui_state.inspector_density = str(density or "comfortable")
        compact = self.ui_state.inspector_density == "compact"
        for tile in (self.tile_node, self.tile_retry, self.tile_fail, self.tile_eta, self.tile_progress, self.tile_run):
            tile.set_density(compact, compact)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(str(text or ""))
        label.setProperty("role", "sectionLabel")
        return label

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(str(text or ""))
        label.setProperty("role", "hudLabel")
        return label

    def _current_narrate_balance_mode(self) -> str:
        return "monitoring" if str(getattr(self, "narrate_stage_mode", "empty")) in {"running", "verified", "failed", "attention", "aborted"} else "authoring"

    def _narrate_viewport_budget(self) -> Tuple[int, int]:
        if hasattr(self, "narrate_scroll") and self.narrate_scroll.viewport() is not None:
            rect = self.narrate_scroll.viewport().contentsRect()
            return max(0, rect.width()), max(0, rect.height())
        if hasattr(self, "page_stack"):
            rect = self.page_stack.contentsRect()
            return max(0, rect.width()), max(0, rect.height())
        return max(0, self.width()), max(0, self.height())

    def _resolve_narrate_layout_mode(self, width: int, height: int, compact: bool) -> str:
        wide_width = 1280 if compact else 1360
        wide_height = 700 if compact else 760
        stacked_width = 1040 if compact else 1120
        stacked_height = 580 if compact else 640
        if width >= wide_width and height >= wide_height:
            return "wide"
        if width >= stacked_width and height >= stacked_height:
            return "stacked-wide"
        return "stacked-tight"

    def _apply_splitter_ratio(self, splitter: QSplitter, weights: Tuple[int, int]):
        if splitter.count() < 2:
            return
        total = max(1, sum(int(weight) for weight in weights))
        span = splitter.size().width() if splitter.orientation() == Qt.Orientation.Horizontal else splitter.size().height()
        if span <= 0:
            splitter.setSizes([int(weight) for weight in weights])
            return
        sizes = [max(1, int(span * weight / total)) for weight in weights]
        remainder = max(0, span - sum(sizes))
        if remainder:
            sizes[-1] += remainder
        splitter.setSizes(sizes)

    def _refresh_narrate_geometry_surfaces(self):
        wrap_rows = [
            self.command_status_wrap,
            self.hero_signal_wrap,
            self.command_action_wrap,
            self.script_badge_wrap,
            self.preview_player.controls_host,
        ]
        if getattr(self.preview_player, "playback_controls", None) is not None:
            wrap_rows.append(self.preview_player.playback_controls)
        for row in wrap_rows:
            row.refresh_layout()
        for label in (self.preview_player.info, self.lbl_output):
            label.refresh_elide()
        for widget in (
            self.command_deck_card,
            self.hero_left_host,
            self.hero_right_host,
            self.card_script,
            self.preview_player,
            self.card_runtime,
            self.utility_card,
            self.narrate_content,
        ):
            widget.updateGeometry()
        if hasattr(self, "narrate_root_layout"):
            self.narrate_root_layout.activate()

    def _stabilize_narrate_layout(self):
        if not hasattr(self, "command_deck_main_layout"):
            return
        self._sync_narrate_responsive_layout(force=True)
        QTimer.singleShot(0, lambda: self._sync_narrate_responsive_layout(force=True))

    def _sync_narrate_responsive_layout(self, force: bool = False):
        if not hasattr(self, "command_deck_main_layout"):
            return
        available_width, available_height = self._narrate_viewport_budget()
        compact = self.ui_state.density == "compact"
        layout_mode = self._resolve_narrate_layout_mode(available_width, available_height, compact)
        narrow = layout_mode != "wide"
        stack_hero = layout_mode != "wide"
        stack_focus = layout_mode == "stacked-tight"
        stack_utility = layout_mode != "wide"
        balance_mode = self._current_narrate_balance_mode()
        mode_changed = layout_mode != getattr(self, "narrate_layout_mode", None)
        balance_changed = balance_mode != getattr(self, "_narrate_balance_mode", None)

        self.command_deck_main_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if stack_hero else QBoxLayout.Direction.LeftToRight
        )
        focus_orientation = Qt.Orientation.Vertical if stack_focus else Qt.Orientation.Horizontal
        utility_orientation = Qt.Orientation.Vertical if stack_utility else Qt.Orientation.Horizontal
        orientation_changed = False
        if self.narrate_focus_splitter.orientation() != focus_orientation:
            self.narrate_focus_splitter.setOrientation(focus_orientation)
            orientation_changed = True
        if self.narrate_utility_splitter.orientation() != utility_orientation:
            self.narrate_utility_splitter.setOrientation(utility_orientation)
            orientation_changed = True

        if layout_mode == "wide":
            self.hero_left_layout.setContentsMargins(18, 18, 18, 18)
            self.hero_left_layout.setSpacing(8)
            self.hero_right_layout.setContentsMargins(14, 14, 14, 14)
            self.hero_right_layout.setHorizontalSpacing(10)
            self.hero_right_layout.setVerticalSpacing(10)
            self.command_deck_card.setMinimumHeight(292 if compact else 320)
            self.narrate_focus_splitter.setMinimumHeight(350 if compact else 400)
            self.narrate_utility_splitter.setMinimumHeight(250 if compact else 300)
            self.script_text.setMinimumHeight(240 if compact else 280)
            self.preview_player.preview_surface.setMinimumHeight(190 if compact else 220)
            self.preview_text.setMinimumHeight(180 if compact else 220)
            self.log_console.setMinimumHeight(180 if compact else 220)
            self.narrate_root_layout.setStretch(1, 5)
            self.narrate_root_layout.setStretch(2, 3)
        elif layout_mode == "stacked-wide":
            self.hero_left_layout.setContentsMargins(16, 16, 16, 16)
            self.hero_left_layout.setSpacing(7)
            self.hero_right_layout.setContentsMargins(12, 12, 12, 12)
            self.hero_right_layout.setHorizontalSpacing(8)
            self.hero_right_layout.setVerticalSpacing(8)
            self.command_deck_card.setMinimumHeight(320 if compact else 348)
            self.narrate_focus_splitter.setMinimumHeight(380 if compact else 430)
            self.narrate_utility_splitter.setMinimumHeight(240 if compact else 280)
            self.script_text.setMinimumHeight(220 if compact else 250)
            self.preview_player.preview_surface.setMinimumHeight(170 if compact else 200)
            self.preview_text.setMinimumHeight(150 if compact else 180)
            self.log_console.setMinimumHeight(150 if compact else 180)
            self.narrate_root_layout.setStretch(1, 5)
            self.narrate_root_layout.setStretch(2, 2)
        else:
            self.hero_left_layout.setContentsMargins(14, 14, 14, 14)
            self.hero_left_layout.setSpacing(6)
            self.hero_right_layout.setContentsMargins(10, 10, 10, 10)
            self.hero_right_layout.setHorizontalSpacing(8)
            self.hero_right_layout.setVerticalSpacing(8)
            self.command_deck_card.setMinimumHeight(330 if compact else 360)
            self.narrate_focus_splitter.setMinimumHeight(520 if compact else 580)
            self.narrate_utility_splitter.setMinimumHeight(320 if compact else 360)
            self.script_text.setMinimumHeight(200 if compact else 230)
            self.preview_player.preview_surface.setMinimumHeight(150 if compact else 170)
            self.preview_text.setMinimumHeight(140 if compact else 160)
            self.log_console.setMinimumHeight(140 if compact else 160)
            self.narrate_root_layout.setStretch(1, 6)
            self.narrate_root_layout.setStretch(2, 2)

        scale = "tight" if stack_hero or narrow else "wide"
        self.command_state_title.setProperty("scale", scale)
        self.command_state_body.setProperty("scale", scale)
        for label in (self.command_state_title, self.command_state_body):
            label.style().unpolish(label)
            label.style().polish(label)
            label.updateGeometry()

        all_pills = [
            self.command_primary_pill,
            self.command_contract_pill,
            self.command_duration_pill,
            self.command_ready_pill,
            self.command_root_pill,
            self.command_confidence_pill,
            self.script_source,
            self.script_hint,
            self.root_status,
            self.process_status,
            self.preview_player.state_pill,
        ]
        for pill in all_pills:
            pill.set_density(compact or narrow)

        metric_tiles = [
            self.tile_node,
            self.tile_retry,
            self.tile_fail,
            self.tile_eta,
            self.tile_progress,
            self.tile_run,
            self.deck_launch_tile,
            self.deck_contract_tile,
            self.deck_voice_tile,
            self.deck_style_tile,
            self.deck_duration_tile,
            self.deck_progress_tile,
            self.deck_output_tile,
        ]
        for tile in metric_tiles:
            tile.set_density(compact, narrow)

        self.narrate_layout_mode = layout_mode
        self._narrate_balance_mode = balance_mode
        self._refresh_narrate_geometry_surfaces()

        if force or mode_changed or balance_changed or orientation_changed:
            if self.narrate_focus_splitter.orientation() == Qt.Orientation.Horizontal:
                focus_weights = (9, 7) if balance_mode == "authoring" else (7, 9)
            else:
                focus_weights = (6, 5) if balance_mode == "authoring" else (5, 6)
            if self.narrate_utility_splitter.orientation() == Qt.Orientation.Horizontal:
                utility_weights = (6, 7) if balance_mode == "authoring" else (5, 8)
            else:
                utility_weights = (5, 4) if balance_mode == "authoring" else (4, 5)
            self._apply_splitter_ratio(self.narrate_focus_splitter, focus_weights)
            self._apply_splitter_ratio(self.narrate_utility_splitter, utility_weights)

    def _set_narrate_utility_mode(self, mode: str):
        mode = "feed" if str(mode or "").strip().lower() == "feed" else "trace"
        self.narrate_utility_mode = mode
        trace_visible = bool(self.ui_state.panel_visibility.get("command_preview", True))
        feed_visible = bool(self.ui_state.panel_visibility.get("live_console", True))
        if mode == "trace" and trace_visible:
            self.narrate_utility_stack.setCurrentWidget(self.trace_console_page)
        elif feed_visible:
            self.narrate_utility_stack.setCurrentWidget(self.feed_console_page)
            self.narrate_utility_mode = "feed"
        elif trace_visible:
            self.narrate_utility_stack.setCurrentWidget(self.trace_console_page)
            self.narrate_utility_mode = "trace"
        for button, active in (
            (self.utility_trace_button, self.narrate_utility_mode == "trace"),
            (self.utility_feed_button, self.narrate_utility_mode == "feed"),
        ):
            button.setProperty("active", "true" if active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_narrate_utility_visibility()

    def _refresh_narrate_utility_visibility(self):
        trace_visible = bool(self.ui_state.panel_visibility.get("command_preview", True))
        feed_visible = bool(self.ui_state.panel_visibility.get("live_console", True))
        self.utility_trace_button.setVisible(trace_visible)
        self.utility_feed_button.setVisible(feed_visible)
        if not trace_visible and self.narrate_utility_mode == "trace" and feed_visible:
            self.narrate_utility_stack.setCurrentWidget(self.feed_console_page)
            self.narrate_utility_mode = "feed"
        elif not feed_visible and self.narrate_utility_mode == "feed" and trace_visible:
            self.narrate_utility_stack.setCurrentWidget(self.trace_console_page)
            self.narrate_utility_mode = "trace"
        elif trace_visible and self.narrate_utility_mode == "trace":
            self.narrate_utility_stack.setCurrentWidget(self.trace_console_page)
        elif feed_visible and self.narrate_utility_mode == "feed":
            self.narrate_utility_stack.setCurrentWidget(self.feed_console_page)
        show_utility = trace_visible or feed_visible
        self.utility_card.setVisible(show_utility)
        for button, active in (
            (self.utility_trace_button, self.narrate_utility_mode == "trace"),
            (self.utility_feed_button, self.narrate_utility_mode == "feed"),
        ):
            button.setProperty("active", "true" if active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self.chk_show_preview.blockSignals(True)
        self.chk_show_preview.setChecked(trace_visible)
        self.chk_show_preview.blockSignals(False)
        self._sync_narrate_responsive_layout()

    def _set_narrate_stage(self, stage: str, detail: str = "", progress_pct: Optional[float] = None):
        stage = str(stage or "idle").strip().lower()
        self.narrate_stage_mode = stage
        progress_text = "--" if progress_pct is None else f"{float(progress_pct):.1f}%"
        if stage == "running":
            self.command_state_label.setText("LIVE EXECUTION")
            self.command_state_title.setText("Run active")
            body = f"{detail}. Progress {progress_text}." if detail else f"The command deck is monitoring the active run at {progress_text}."
            self.command_state_body.setText(body)
            self.command_confidence_pill.setText("LIVE MONITORING")
            self.command_confidence_pill.set_tone("live")
            self.preview_player.set_state("RUN ACTIVE", "live", detail or "Monitoring current node and output readiness.")
            self.deck_launch_tile.set_value("RUNNING")
            self.deck_launch_tile.set_tone("live")
            self.deck_progress_tile.set_value(progress_text)
            self.deck_progress_tile.set_tone("live")
            self.deck_output_tile.set_value("ACTIVE")
            self.deck_output_tile.set_tone("live")
            self.btn_open_latest_video.set_accent_kind("ghost")
            self._set_narrate_utility_mode("feed")
            self._sync_narrate_responsive_layout()
            return
        if stage == "verified":
            self.command_state_label.setText("MISSION COMPLETE")
            self.command_state_title.setText("Verified output")
            self.command_state_body.setText(detail or "Render complete. Verification cleared the latest output and the deck is ready for review.")
            self.command_confidence_pill.setText("VERIFIED")
            self.command_confidence_pill.set_tone("success")
            self.preview_player.set_state("VERIFIED", "success", detail or "Latest output is ready for external review.")
            self.deck_launch_tile.set_value("VERIFIED")
            self.deck_launch_tile.set_tone("success")
            self.deck_progress_tile.set_value("100.0%")
            self.deck_progress_tile.set_tone("success")
            self.deck_output_tile.set_value("READY")
            self.deck_output_tile.set_tone("success")
            self.btn_open_latest_video.set_accent_kind("success")
            self._set_narrate_utility_mode("feed")
            self._sync_narrate_responsive_layout()
            return
        if stage in {"failed", "attention", "aborted"}:
            self.command_state_label.setText("ATTENTION")
            self.command_state_title.setText("Run needs review")
            self.command_state_body.setText(detail or "The last run stopped before verification. Review the operational trace and latest output.")
            self.command_confidence_pill.setText("ATTENTION")
            self.command_confidence_pill.set_tone("warning")
            self.preview_player.set_state("REVIEW", "warning", detail or "Inspect the output and execution feed.")
            self.deck_launch_tile.set_value("REVIEW")
            self.deck_launch_tile.set_tone("warning")
            self.deck_output_tile.set_value("REVIEW")
            self.deck_output_tile.set_tone("warning")
            self.btn_open_latest_video.set_accent_kind("ghost")
            self._set_narrate_utility_mode("feed")
            self._sync_narrate_responsive_layout()
            return
        if stage == "armed":
            self.command_state_label.setText("LAUNCH READY")
            self.command_state_title.setText("Launch armed")
            self.command_state_body.setText(
                "The script, contract, voice, and duration plan are aligned. The deck is ready to launch deterministic narration."
            )
            self.command_confidence_pill.setText("PAYLOAD VISIBLE")
            self.command_confidence_pill.set_tone("info")
            self.preview_player.set_state("STANDBY", "info", "Output monitor is armed. Trace stays forward until the run starts.")
            self.deck_launch_tile.set_value("ARMED")
            self.deck_launch_tile.set_tone("success")
            self.deck_output_tile.set_value("READY")
            self.deck_output_tile.set_tone("default")
            self.deck_progress_tile.set_value("0.0%")
            self.deck_progress_tile.set_tone("default")
            self.btn_open_latest_video.set_accent_kind("ghost")
            self._set_narrate_utility_mode("trace")
            self._sync_narrate_responsive_layout()
            return
        self.command_state_label.setText("MISSION STATE")
        self.command_state_title.setText("Awaiting script")
        self.command_state_body.setText(
            "Provide an exact script to arm the launch contract, payload trace, and deterministic narration path."
        )
        self.command_confidence_pill.setText("UNARMED")
        self.command_confidence_pill.set_tone("muted")
        self.preview_player.set_state("STANDBY", "muted", "Latest output will land here. During a run, this surface leans into monitoring.")
        self.deck_launch_tile.set_value("WARM")
        self.deck_launch_tile.set_tone("live")
        self.deck_output_tile.set_value("WAITING")
        self.deck_output_tile.set_tone("default")
        self.deck_progress_tile.set_value("0.0%")
        self.deck_progress_tile.set_tone("default")
        self.btn_open_latest_video.set_accent_kind("ghost")
        self._set_narrate_utility_mode("trace")
        self._sync_narrate_responsive_layout()

    def _agent_root_guard(self) -> bool:
        return os.path.basename(os.path.normpath(APP_ROOT)).lower() == EXPECTED_ROOT_NAME

    def _set_default_voice(self):
        idx = 0
        for i in range(self.voice_combo.count()):
            if self.voice_combo.itemData(i) == DEFAULT_VOICE_PRESET_ID:
                idx = i
                break
        self.voice_combo.setCurrentIndex(idx)

    def _toggle_preview_panel(self, visible: bool):
        self.ui_state.panel_visibility["command_preview"] = bool(visible)
        self._refresh_narrate_utility_visibility()

    def _toggle_panel(self, key: str, visible: bool):
        visible = bool(visible)
        self.ui_state.panel_visibility[key] = visible
        if key == "left_nav":
            self.left_rail_frame.setVisible(visible)
            self.chk_left_nav.setChecked(visible)
        elif key == "right_inspector":
            self.inspector.setVisible(visible)
            self.chk_right.setChecked(visible)
        elif key == "command_preview":
            self.chk_preview.setChecked(visible)
            self.chk_show_preview.setChecked(visible)
            self._refresh_narrate_utility_visibility()
        elif key == "video_preview":
            self.preview_player.setVisible(visible)
            self.post_preview.setVisible(visible)
            self.chk_video_preview.setChecked(visible)
        elif key == "live_console":
            self.chk_live_console.setChecked(visible)
            self._refresh_narrate_utility_visibility()

    # ---------- NARRATE ----------
    def _current_duration_plan(self, script_text: Optional[str] = None) -> Dict[str, object]:
        requested_target_duration = None
        if self.rewrite_combo.currentText().strip().lower() == "force":
            requested_target_duration = int(self.duration_spin.value())
        return resolve_duration_plan(
            input_source="USER_CONTEXT",
            context_rewrite=self.rewrite_combo.currentText().strip(),
            narration_style=self.style_combo.currentText().strip(),
            context_text=self.script_text.toPlainText() if script_text is None else str(script_text or ""),
            requested_target_duration=requested_target_duration,
        )

    def _build_narrate_tokens(self, context_file: str) -> List[str]:
        duration_plan = self._current_duration_plan()
        prepared = prepare_narrate_launch(
            script=self.script_text.toPlainText().strip(),
            stamp="preview",
            request_prompt=self.request_title.text().strip() or "Create narrated video from provided script.",
            duration_plan=duration_plan,
            narration_style=self.style_combo.currentText().strip(),
            context_rewrite=self.rewrite_combo.currentText().strip(),
            watermark_mode=self.watermark_combo.currentText().strip(),
            voice_preset=str(self.voice_combo.currentData() or DEFAULT_VOICE_PRESET_ID),
            key_probe=self.key_probe_combo.currentText().strip(),
            python_executable=sys.executable,
            commander_path=COMMANDER_PATH,
            app_root=APP_ROOT,
            expected_root_name=EXPECTED_ROOT_NAME,
            ui_profile=f"{self.ui_state.theme_id}:{self.ui_state.density}",
            session_id=self.session_id,
            launch_source="studio_agent_ui_v2",
        )
        if prepared.context_file != context_file:
            preview_tokens = list(prepared.cli_tokens)
            idx = preview_tokens.index("--context-file")
            preview_tokens[idx + 1] = context_file
            return [COMMANDER_PATH, *preview_tokens]
        return list(prepared.arguments)

    def _rebuild_preview(self):
        script = self.script_text.toPlainText().strip()
        words = len([x for x in script.split() if x.strip()])
        lines = len([x for x in script.splitlines() if x.strip()])
        duration_plan = self._current_duration_plan(script)
        request_title = self.request_title.text().strip() or "Create narrated video from provided script"
        self.script_stats.setText(f"{words} words | {lines} lines")
        self.script_source.setText(
            "USER_CONTEXT / deterministic" if self.rewrite_combo.currentText().strip() == "off" else "USER_CONTEXT / rewrite"
        )
        self.script_source.set_tone("info" if self.rewrite_combo.currentText().strip() == "off" else "warning")
        self.script_hint.setText("ROOT LOCKED" if self._agent_root_guard() else "ROOT ALERT")
        self.script_hint.set_tone("success" if self._agent_root_guard() else "danger")
        self.command_request_title.setText(
            f"Mission title: {request_title}" if script else "Mission title will appear here when the deck is armed."
        )
        self.script_guidance.setText(
            (
                f"{words} words across {lines} lines. The script studio is armed and the launch deck can now verify payload confidence."
            )
            if script
            else "Paste a script to arm the deck and unlock launch readiness."
        )
        if duration_plan.get("duration_mode") == DURATION_MODE_AUTO:
            self.duration_stack.setCurrentIndex(0)
            self.duration_mode_value.setText("Auto from script")
            est = duration_plan.get("estimated_duration_seconds")
            self.duration_estimate_value.setText(f"~{est}s estimated" if est else "Waiting for script...")
        else:
            self.duration_stack.setCurrentIndex(1)
            self.duration_mode_value.setText("Manual target duration")
            est = duration_plan.get("estimated_duration_seconds")
            self.duration_estimate_value.setText(f"~{est}s current script estimate" if est else "No estimate available")
        preview_ctx = write_context_file(script, "preview") if script else "<missing_script>"
        pretty = [sys.executable] + self._build_narrate_tokens(preview_ctx if script else preview_ctx)
        self.preview_text.setPlainText(
            "\n".join([f"[{i:02d}] {x if len(x) < 500 else x[:500] + ' ...'}" for i, x in enumerate(pretty)])
        )
        voice_label = self.voice_combo.currentText().split(" (", 1)[0].strip() or "UNSET"
        self.command_summary.setText(
            (
                f"{words} words across {lines} lines. "
                f"Style {self.style_combo.currentText().strip()} with "
                f"{'locked deterministic authoring' if self.rewrite_combo.currentText().strip() == 'off' else 'rewrite-enabled narrative shaping'}."
            )
            if script
            else "Provide a script to arm the launch contract, payload trace, and deterministic run state."
        )
        contract_text = "LOCKED" if self.rewrite_combo.currentText().strip() == "off" else "REWRITE"
        self.command_contract_pill.setText(f"CONTRACT {contract_text}")
        self.command_contract_pill.set_tone("success" if contract_text == "LOCKED" else "warning")
        self.command_duration_pill.setText(
            "AUTO DURATION" if duration_plan.get("duration_mode") == DURATION_MODE_AUTO else "MANUAL TARGET"
        )
        self.command_duration_pill.set_tone("info" if duration_plan.get("duration_mode") == DURATION_MODE_AUTO else "warning")
        self.deck_contract_tile.set_value(contract_text)
        self.deck_voice_tile.set_value(voice_label.upper())
        self.deck_style_tile.set_value(self.style_combo.currentText().strip().upper())
        est = duration_plan.get("estimated_duration_seconds")
        self.deck_duration_tile.set_value(f"AUTO ~{est}s" if duration_plan.get("duration_mode") == DURATION_MODE_AUTO and est else "MANUAL")
        self.command_root_pill.setText("ROOT PASS" if self._agent_root_guard() else "ROOT ALERT")
        self.command_root_pill.set_tone("success" if self._agent_root_guard() else "warning")
        if self.process.state() == self.process.ProcessState.NotRunning:
            if script:
                self._set_process_pill("Armed", "success")
                self._set_narrate_stage("armed")
            else:
                self._set_process_pill("Warm", "info")
                self._set_narrate_stage("empty")

    def _launch_narrate(self):
        if not self._agent_root_guard():
            QMessageBox.critical(self, "Root Guard", f"Launch blocked. Root is not agent repo:\n{APP_ROOT}")
            return
        if self.process.state() != self.process.ProcessState.NotRunning:
            self._show_toast("A run is already active", "warning")
            return

        script = self.script_text.toPlainText().strip()
        if not script:
            QMessageBox.warning(self, "Missing Script", "Provide script text first.")
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        duration_plan = self._current_duration_plan(script)
        prepared = prepare_narrate_launch(
            script=script,
            stamp=stamp,
            request_prompt=self.request_title.text().strip() or "Create narrated video from provided script.",
            duration_plan=duration_plan,
            narration_style=self.style_combo.currentText().strip(),
            context_rewrite=self.rewrite_combo.currentText().strip(),
            watermark_mode=self.watermark_combo.currentText().strip(),
            voice_preset=str(self.voice_combo.currentData() or DEFAULT_VOICE_PRESET_ID),
            key_probe=self.key_probe_combo.currentText().strip(),
            python_executable=sys.executable,
            commander_path=COMMANDER_PATH,
            app_root=APP_ROOT,
            expected_root_name=EXPECTED_ROOT_NAME,
            ui_profile=f"{self.ui_state.theme_id}:{self.ui_state.density}",
            session_id=self.session_id,
            launch_source="studio_agent_ui_v2",
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.active_payload_path = persist_launch_payload(prepared.payload, stamp)
        self.active_known_runs = set(list_run_ids())

        self.process.setWorkingDirectory(APP_ROOT)
        self.process.start(sys.executable, prepared.arguments)
        if not self.process.waitForStarted(5000):
            QMessageBox.critical(self, "Launch Failed", "Commander process did not start.")
            return
        self.btn_launch.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self._set_process_pill("Running", "info")
        self._set_narrate_stage("running", detail="Commander launch handshake in progress.", progress_pct=0.0)
        self.live_timer.start()
        self._append_log("NARRATE launch started with ui_launch_payload.v2")
        self._show_toast("NARRATE started", "success")

    def _abort_run(self):
        if self.process.state() != self.process.ProcessState.NotRunning:
            run_id = resolve_current_run_id()
            self.process.kill()
            self.process.waitForFinished(3000)
            if run_id:
                mark_run_terminal(run_id, "aborted", "aborted_by_ui")
        self.btn_launch.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self._set_process_pill("Aborted", "warning")
        self._set_narrate_stage("aborted", detail="The active run was stopped from the control room.")
        self._show_toast("Run aborted", "warning")

    def _on_stdout(self):
        txt = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        if txt.strip():
            self._append_log(txt.rstrip())

    def _on_stderr(self):
        txt = bytes(self.process.readAllStandardError()).decode("utf-8", errors="ignore")
        if txt.strip():
            self._append_log(f"[stderr] {txt.rstrip()}")

    def _on_process_error(self, _err):
        self._append_log("[error] Commander process error.")

    def _on_finished(self, code: int, _status):
        self.live_timer.stop()
        self.btn_launch.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self._set_process_pill("Completed" if code == 0 else "Failed", "success" if code == 0 else "danger")
        self._set_narrate_stage("verified" if code == 0 else "failed", detail="Verification clean." if code == 0 else "Commander exited with a failure status.")
        self._append_log(f"Process finished with exit code {code}")

        all_runs = set(list_run_ids())
        new_runs = sorted([r for r in all_runs if r not in self.active_known_runs])
        run_id = new_runs[-1] if new_runs else (resolve_current_run_id() or resolve_latest_run_id())
        if run_id:
            attach_payload_to_run(
                self.active_payload_path,
                run_id,
                int(code),
                asdict(self.ui_state),
            )
            if run_id not in self.ui_state.recent_runs:
                self.ui_state.recent_runs.insert(0, run_id)
                self.ui_state.recent_runs = self.ui_state.recent_runs[:20]
            self._append_log(f"Attached UI payload + run snapshot for {run_id}")
        self._refresh_live_metrics()
        self._refresh_run_gallery()
        self._refresh_post_runs()
        self._show_toast("Run complete" if code == 0 else "Run failed", "success" if code == 0 else "error")

    def _append_log(self, text: str):
        self.log_console.append(text)
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    # ---------- Live / Inspector ----------
    def _refresh_live_metrics(self):
        m = read_live_metrics()
        self.tile_node.set_value(m.get("node", "idle"))
        self.tile_retry.set_value(str(m.get("retries", 0)))
        self.tile_fail.set_value(str(m.get("api_failures", 0)))
        self.tile_eta.set_value(m.get("eta", "--"))
        progress_pct = m.get("progress_pct")
        if progress_pct is None:
            self.tile_progress.set_value("--")
        else:
            self.tile_progress.set_value(f"{float(progress_pct):.1f}%")
        self.tile_run.set_value(m.get("run_id", "--"))
        detail = str(m.get("node_detail", "") or "").strip()
        if not detail:
            units_completed = m.get("node_units_completed")
            units_total = m.get("node_units_total")
            if units_completed is not None and units_total:
                detail = f"{units_completed}/{units_total}"
        self.lbl_node_detail.setText(detail)
        self.lbl_output.set_full_text(str(m.get("output_video", "") or "--"))
        node_name = str(m.get("node", "idle") or "idle")
        retries = int(m.get("retries", 0) or 0)
        failures = int(m.get("api_failures", 0) or 0)
        progress_pct = float(m.get("progress_pct", 0.0) or 0.0)
        self.tile_node.set_tone("live" if node_name.lower() not in {"idle", "--"} else "default")
        self.tile_progress.set_tone("success" if progress_pct >= 100.0 else "live")
        self.tile_fail.set_tone("warning" if failures else "default")
        self.tile_retry.set_tone("warning" if retries else "default")
        self.deck_progress_tile.set_value(f"{progress_pct:.1f}%")
        self.deck_progress_tile.set_tone("success" if progress_pct >= 100.0 else "live" if progress_pct > 0.0 else "default")
        self.quick_runs_combo.blockSignals(True)
        self.quick_runs_combo.clear()
        self.quick_runs_combo.addItems(list_run_ids()[:50])
        self.quick_runs_combo.blockSignals(False)

        guard_ok = self._agent_root_guard()
        self.root_status.setText("ROOT PASS" if guard_ok else "ROOT FAIL")
        self.root_status.set_tone("success" if guard_ok else "danger")
        self.command_root_pill.setText("ROOT PASS" if guard_ok else "ROOT ALERT")
        self.command_root_pill.set_tone("success" if guard_ok else "warning")
        out = str(m.get("output_video", "") or "")
        if out and os.path.exists(out):
            self.preview_player.set_video(out)
            self.deck_output_tile.set_value("OUTPUT READY")
            self.preview_player.set_state("OUTPUT READY", "success", "Latest render is attached and ready for review.")
        if node_name.lower() not in {"idle", "--"}:
            self.command_ready_pill.setText(node_name.upper())
            self.command_ready_pill.set_tone("live")
            self._set_narrate_stage("running", detail=detail or node_name, progress_pct=progress_pct)
        elif progress_pct >= 100.0 and out:
            self._set_narrate_stage("verified", detail="Verification clean. Latest output is attached.")

    def _quick_run_selected(self, run_id: str):
        run_id = str(run_id or "").strip()
        if not run_id:
            return
        if run_id not in self.ui_state.recent_runs:
            self.ui_state.recent_runs.insert(0, run_id)
            self.ui_state.recent_runs = self.ui_state.recent_runs[:20]

    # ---------- Runs gallery ----------
    def _clear_grid(self, layout: QGridLayout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _populate_run_skeletons(self, n: int = 8):
        self._clear_grid(self.run_grid)
        for i in range(n):
            sk = QFrame()
            sk.setObjectName("GlassCard")
            lay = QVBoxLayout(sk)
            lay.addWidget(QLabel("Loading run card..."))
            lay.addWidget(QLabel("Please wait"))
            self.run_grid.addWidget(sk, i // 3, i % 3)

    def _refresh_run_gallery(self):
        self._populate_run_skeletons()
        QTimer.singleShot(140, self._populate_run_cards_real)

    def _populate_run_cards_real(self):
        self._clear_grid(self.run_grid)
        search = self.run_search.text().strip().lower()
        rows = list_run_cards(limit=60)
        if search:
            rows = [r for r in rows if search in r["run_id"].lower() or search in str(r.get("timestamp", "")).lower()]
        verified_count = 0
        fallback_total = 0
        for i, row in enumerate(rows):
            card = RunCard(row["run_id"], row["run_dir"], title=row["run_id"])
            card.set_thumbnail(row.get("thumbnail", ""))
            if row.get("verified"):
                ver = "PASS"
                tone = "success"
                verified_count += 1
            elif row.get("telemetry_pass"):
                ver = "TELEMETRY"
                tone = "info"
            else:
                ver = "CHECK"
                tone = "warning"
            fallback_total += int(row.get("fallback_count", 0) or 0)
            card.set_status(ver, tone)
            summary = (
                f"{'Verifier clean' if row.get('verified') else 'Needs review'}  |  "
                f"duration {row.get('duration','--')}s  |  "
                f"fallback {row.get('fallback_count',0)}"
            )
            card.set_summary(summary)
            meta = (
                f"timestamp={row.get('timestamp','')}\n"
                f"duration={row.get('duration','--')}  verifier={ver}\n"
                f"api_fail={row.get('api_failures',0)} fallback={row.get('fallback_count',0)}"
            )
            card.set_meta(meta)
            b = QHBoxLayout()
            btn_folder = QPushButton("Open Run")
            btn_video = AccentButton("Open Video", accent_kind="ghost")
            btn_folder.clicked.connect(lambda _=False, p=row["run_dir"]: self._open_path(p))
            btn_video.clicked.connect(lambda _=False, p=row.get("output_video", ""): self._open_video_path(p))
            b.addWidget(btn_folder)
            b.addWidget(btn_video)
            b.addStretch(1)
            card.layout_root.addLayout(b)
            self.run_grid.addWidget(card, i // 3, i % 3)
        if not rows:
            self.run_grid.addWidget(QLabel("No runs found"), 0, 0)
        self.run_tile_total.set_value(str(len(rows)))
        self.run_tile_verified.set_value(str(verified_count))
        self.run_tile_fallbacks.set_value(str(fallback_total))

    # ---------- Post-production ----------
    def _refresh_post_runs(self):
        cur = self.post_runs_combo.currentText().strip()
        self.post_runs_combo.clear()
        rows = list_completed_runs(APP_ROOT, limit=80, only_with_output=True)
        ids = [r["run_id"] for r in rows]
        self.post_runs_combo.addItems(ids)
        if cur and cur in ids:
            self.post_runs_combo.setCurrentText(cur)

    def _create_post_project(self):
        run_id = self.post_runs_combo.currentText().strip()
        if not run_id:
            QMessageBox.warning(self, "Run required", "Select a run first.")
            return
        try:
            path = create_post_project(APP_ROOT, run_id)
            self.post_project_path.setText(path)
            self.post_project_metric.set_value(run_id)
            self.post_project_metric.set_tone("live")
            self.post_render_metric.set_value("PROJECT READY")
            self._show_toast(f"Post project created: {run_id}", "success")
            self._log_post(path)
            self._load_project_layers()
        except Exception as exc:
            self._log_post(f"[error] {exc}")
            self._show_toast("Post project creation failed", "error")

    def _browse_replace_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select replacement image",
            APP_ROOT,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.replace_path.setText(path)

    def _ensure_post_project(self) -> str:
        p = self.post_project_path.text().strip()
        if not p or not os.path.exists(p):
            raise FileNotFoundError("Create/select post project first.")
        return p

    def _apply_replace_image(self):
        try:
            p = self._ensure_post_project()
            out = replace_epoch_image(p, int(self.replace_epoch_spin.value()), self.replace_path.text().strip())
            self._log_post(str(out))
            self._show_toast("Epoch image replaced", "success")
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _load_project_layers(self):
        self.layer_list.clear()
        try:
            p = self._ensure_post_project()
            rows = list_text_layers(p)
            for row in rows:
                item = QListWidgetItem(
                    f"[{row['track']}] {row['id']}  {row['start']:.2f}-{row['end']:.2f}  {row['text'][:56]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.layer_list.addItem(item)
            self.post_layer_metric.set_value(str(len(rows)))
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _on_layer_selected(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]):
        if not current:
            return
        layer_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
        if not layer_id:
            return
        try:
            p = self._ensure_post_project()
            project = load_project(p)
            layer = next((x for x in project.get("text_layers", []) if str(x.get("id", "")) == layer_id), None)
            if not layer:
                return
            self.layer_text.setText(str(layer.get("text", "")))
            self.layer_style.setCurrentText(str(layer.get("style", "Fade Caption")))
            self.layer_start.setValue(float(layer.get("start", 0.0) or 0.0))
            self.layer_end.setValue(float(layer.get("end", 0.0) or 0.0))
            params = dict(layer.get("params", {}))
            self.motion_in_ms.setValue(int(params.get("entry_ms", 180)))
            self.motion_out_ms.setValue(int(params.get("exit_ms", 180)))
            self.motion_opacity.setValue(int(params.get("opacity", 100)))
            self.motion_blur.setValue(float(params.get("blur", 0.6)))
            self.motion_offset_x.setValue(int(params.get("offset_x", 0)))
            self.motion_offset_y.setValue(int(params.get("offset_y", 0)))
            self.motion_in_curve.setCurrentText(str(params.get("in_curve", "cubic")))
            self.motion_out_curve.setCurrentText(str(params.get("out_curve", "cubic")))
            self._update_style_preview(self.layer_style.currentText())
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _update_style_preview(self, style: str):
        cfg = TEXT_STYLE_PRESETS.get(style, {})
        self.style_preview.setText(
            f"{style}  |  anchor={cfg.get('anchor', '-')}  |  effect={cfg.get('effect', '-')}"
        )

    def _apply_layer_edit(self):
        try:
            p = self._ensure_post_project()
            item = self.layer_list.currentItem()
            if not item:
                raise ValueError("Select a layer first.")
            layer_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            params = {
                "entry_ms": int(self.motion_in_ms.value()),
                "exit_ms": int(self.motion_out_ms.value()),
                "opacity": int(self.motion_opacity.value()),
                "blur": float(self.motion_blur.value()),
                "offset_x": int(self.motion_offset_x.value()),
                "offset_y": int(self.motion_offset_y.value()),
                "in_curve": self.motion_in_curve.currentText(),
                "out_curve": self.motion_out_curve.currentText(),
            }
            out = update_text_layer(
                p,
                layer_id=layer_id,
                text=self.layer_text.text().strip(),
                style=self.layer_style.currentText().strip(),
                start=float(self.layer_start.value()),
                end=float(self.layer_end.value()),
                params=params,
            )
            self._log_post(str(out))
            self._show_toast("Layer updated", "success")
            self._load_project_layers()
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _save_layer_order(self):
        try:
            p = self._ensure_post_project()
            order = []
            for i in range(self.layer_list.count()):
                item = self.layer_list.item(i)
                order.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
            out = reorder_text_layers(p, order)
            self._log_post(str(out))
            self._show_toast("Layer order saved", "success")
            self._load_project_layers()
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _render_post_project(self):
        try:
            p = self._ensure_post_project()
            self.post_render_metric.set_value("RENDERING")
            self.post_render_metric.set_tone("live")
            out = render_post_project(p)
            self._log_post(str(out))
            self._show_toast("Post project rendered", "success")
            self.post_render_metric.set_value("RENDERED")
            self.post_render_metric.set_tone("success")
            video = str(out.get("output_video", ""))
            if video:
                self.post_preview.set_video(video)
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _run_ralph(self):
        try:
            p = self._ensure_post_project()
            self.post_loop_metric.set_value(f"{int(self.spin_ralph.value())} loops")
            self.post_loop_metric.set_tone("live")
            out = run_ralph_loop(p, max_loops=int(self.spin_ralph.value()))
            self._log_post(str(out))
            self._show_toast(f"Ralph loop status: {out.get('status')}", "info")
            self.post_loop_metric.set_value(str(out.get("status", "done")).upper())
            self.post_loop_metric.set_tone("success" if str(out.get("status", "")).lower() == "passed" else "warning")
            video = str(out.get("output_video", ""))
            if video:
                self.post_preview.set_video(video)
        except Exception as exc:
            self._log_post(f"[error] {exc}")

    def _log_post(self, text: str):
        self.post_log.append(str(text))
        self.post_log.verticalScrollBar().setValue(self.post_log.verticalScrollBar().maximum())

    # ---------- Preview / file actions ----------
    def _pick_preview_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select video", APP_ROOT, "Videos (*.mp4 *.mov *.mkv *.webm)")
        if path:
            self.preview_player.set_video(path)
            self.post_preview.set_video(path)

    def _open_preview_external(self):
        p = self.preview_player.current_path or self.post_preview.current_path
        self._open_video_path(p)

    def _open_path(self, path: str):
        path = str(path or "").strip()
        if path and os.path.exists(path):
            os.startfile(path)

    def _open_video_path(self, path: str):
        path = str(path or "").strip()
        if path and os.path.exists(path):
            os.startfile(path)
        elif path:
            self._show_toast("Video path missing", "warning")

    def _open_latest_run_folder(self):
        run_id = resolve_current_run_id() or resolve_latest_run_id()
        if not run_id:
            return
        self._open_path(os.path.join(RUNS_ROOT, run_id))

    def _open_latest_video(self):
        m = read_live_metrics()
        out = str(m.get("output_video", "") or "")
        if out and os.path.exists(out):
            self._open_video_path(out)
            self.preview_player.set_video(out)
            return
        run_id = resolve_current_run_id() or resolve_latest_run_id()
        if not run_id:
            return
        run_dir = os.path.join(RUNS_ROOT, run_id)
        mp4s = sorted([x for x in os.listdir(run_dir) if x.lower().endswith(".mp4")]) if os.path.isdir(run_dir) else []
        if mp4s:
            path = os.path.join(run_dir, mp4s[-1])
            self._open_video_path(path)
            self.preview_player.set_video(path)

    # ---------- Top-level helpers ----------
    def _create_shortcut(self):
        script = os.path.join(APP_ROOT, "make_agent_ui_shortcut.py")
        if not os.path.exists(script):
            QMessageBox.warning(self, "Missing script", script)
            return
        try:
            out = subprocess.check_output([sys.executable, script], cwd=APP_ROOT, text=True)
            self._show_toast((out or "Shortcut created").strip(), "success")
        except Exception as exc:
            QMessageBox.critical(self, "Shortcut failed", str(exc))

    def _show_toast(self, text: str, tone: str = "info"):
        if str(os.environ.get("TVC_UI_CAPTURE", "") or "").strip() == "1":
            return
        toast = Toast(str(text), tone=tone, parent=self.centralWidget())
        toast.adjustSize()
        margin = 18
        y = self.centralWidget().height() - toast.height() - margin
        for old in self.toast_widgets:
            y -= old.height() + 8
        x = self.centralWidget().width() - toast.width() - margin
        toast.move(max(8, x), max(8, y))
        toast.show()
        toast.fade_in()
        self.toast_widgets.append(toast)

        def _cleanup():
            toast.fade_out()
            QTimer.singleShot(180, lambda: self._remove_toast(toast))

        QTimer.singleShot(max(self._motion_duration("toast_ms"), 900), _cleanup)

    def _remove_toast(self, toast: Toast):
        if toast in self.toast_widgets:
            self.toast_widgets.remove(toast)
        toast.deleteLater()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_narrate_responsive_layout(force=True)
        QTimer.singleShot(0, self._stabilize_narrate_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_narrate_responsive_layout()

    def _apply_ui_state(self):
        if not self.ui_state.panel_visibility.get("left_nav", True):
            self.left_rail_frame.hide()
        if not self.ui_state.panel_visibility.get("right_inspector", True):
            self.inspector.hide()
        self.preview_player.setVisible(self.ui_state.panel_visibility.get("video_preview", True))
        self.post_preview.setVisible(self.ui_state.panel_visibility.get("video_preview", True))
        self._refresh_narrate_utility_visibility()

        if self.ui_state.splitter_state:
            try:
                raw = bytes.fromhex(self.ui_state.splitter_state)
                from PyQt6.QtCore import QByteArray

                self.body_splitter.restoreState(QByteArray(raw))
            except Exception:
                pass

        self.theme_combo.setCurrentText(self.ui_state.theme_id)
        self.density_combo.setCurrentText(self.ui_state.density)
        if hasattr(self, "settings_theme_combo"):
            self.settings_theme_combo.setCurrentText(self.ui_state.theme_id)
        if hasattr(self, "settings_density_combo"):
            self.settings_density_combo.setCurrentText(self.ui_state.density)
        if hasattr(self, "performance_combo"):
            self.performance_combo.setCurrentText(self.ui_state.performance_mode)
        if hasattr(self, "settings_motion_combo"):
            self.settings_motion_combo.setCurrentText(self.ui_state.motion_profile)
        if hasattr(self, "settings_layout_combo"):
            self.settings_layout_combo.setCurrentText(self.ui_state.layout_mode)
        if hasattr(self, "chk_reduced_motion"):
            self.chk_reduced_motion.setChecked(self.ui_state.reduced_motion)
        if hasattr(self, "inspector_density_combo"):
            self.inspector_density_combo.setCurrentText(self.ui_state.inspector_density)
        self._change_inspector_density(self.ui_state.inspector_density)
        self._stabilize_narrate_layout()

    def closeEvent(self, event):
        self.ui_state.theme_id = self.theme_combo.currentText().strip() or self.ui_state.theme_id
        self.ui_state.density = self.density_combo.currentText().strip() or self.ui_state.density
        self.ui_state.performance_mode = self.performance_combo.currentText().strip() or self.ui_state.performance_mode
        self.ui_state.motion_profile = self.settings_motion_combo.currentText().strip() or self.ui_state.motion_profile
        self.ui_state.layout_mode = self.settings_layout_combo.currentText().strip() or self.ui_state.layout_mode
        self.ui_state.reduced_motion = bool(self.chk_reduced_motion.isChecked())
        self.ui_state.inspector_density = (
            self.inspector_density_combo.currentText().strip() or self.ui_state.inspector_density
        )
        self.ui_state.splitter_state = bytes(self.body_splitter.saveState()).hex()
        save_ui_state(self.ui_state)
        super().closeEvent(event)
