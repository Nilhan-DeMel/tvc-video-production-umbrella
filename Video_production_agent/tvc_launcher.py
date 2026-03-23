import sys
import os
import re
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPlainTextEdit, QComboBox, 
                             QPushButton, QProgressBar, QTextBrowser, QGroupBox,
                             QMessageBox)
from PyQt6.QtCore import Qt, QProcess, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QColor, QPalette

import tvc_config
from tvc_duration import resolve_duration_plan
from tvc_launch_contract import get_dead_end_metadata, persist_launch_payload, prepare_narrate_launch, strip_mode_label
from tvc_voice_registry import DEFAULT_VOICE_PRESET_ID
# --- Configuration Paths ---
INTEL_DIR = os.path.dirname(tvc_config.PATHS["secrets"]) # D:\AI\API
APP_STATION_DIR = tvc_config.PATHS["root"]
COMMANDER_SCRIPT = os.path.join(APP_STATION_DIR, "supreme_commander.py")


# --- QSS Styling (SOTA Dark Glassmorphism) ---
SOTA_STYLESHEET = """
QMainWindow {
    background-color: #0d0d0d;
}

QWidget {
    color: #e0e0e0;
    font-size: 13px;
    font-family: 'Segoe UI', Inter, sans-serif;
}

QGroupBox {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    margin-top: 1.5ex;
    background-color: rgba(30, 30, 36, 0.4);
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #888888;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QPlainTextEdit {
    background-color: #1a1a1a;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 12px;
    font-size: 14px;
    selection-background-color: #007acc;
}
QPlainTextEdit:focus {
    border: 1px solid #007acc;
    background-color: #1e1e1e;
}

QTextBrowser {
    background-color: #000000;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 6px;
    padding: 10px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
}

QComboBox {
    background-color: #1a1a1a;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    padding: 6px 12px;
    min-width: 150px;
}
QComboBox:hover {
    border: 1px solid rgba(255, 255, 255, 0.2);
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: none;
}

QPushButton {
    background-color: #1a1a1a;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    color: #ffffff;
}
QPushButton:hover {
    background-color: #2a2a2a;
    border: 1px solid rgba(255, 255, 255, 0.2);
}
QPushButton:pressed {
    background-color: #333333;
}
QPushButton#launchBtn {
    background-color: #0070f3;
    border: none;
    font-weight: bold;
}
QPushButton#launchBtn:hover {
    background-color: #3291ff;
}
QPushButton#launchBtn:disabled {
    background-color: #111111;
    color: #444444;
}
QPushButton#abortBtn {
    background-color: transparent;
    border: 1px solid #ff4d4f;
    color: #ff4d4f;
}
QPushButton#abortBtn:hover {
    background-color: rgba(255, 77, 79, 0.1);
}

QProgressBar {
    background-color: #1a1a1a;
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 24px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0070f3, stop:1 #00c6ff);
    border-radius: 5px;
}
"""

class TVCLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⬛ TVC EMPEROR — Video Production Command Centre")
        self.setMinimumSize(950, 750)
        self.setStyleSheet(SOTA_STYLESHEET)
        
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)

        self.epoch_total = 13  # Default expectation, updated dynamically
        self.current_epoch = 0

        self.init_ui()
        self.load_api_vault()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # --- 1. Mission Brief ---
        brief_group = QGroupBox("Mission Brief")
        brief_layout = QVBoxLayout()
        self.description_input = QPlainTextEdit()
        self.description_input.setPlaceholderText("Enter the cinematic narrative or video description here...")
        brief_layout.addWidget(self.description_input)
        brief_group.setLayout(brief_layout)
        main_layout.addWidget(brief_group, stretch=2)

        # --- 2. Middle Row (Settings & Engines) ---
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(20)
        
        # Ordinance Configuration
        ord_group = QGroupBox("Ordinance Configuration")
        ord_layout = QVBoxLayout()
        
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "MODE_NARRATE [LEGACY COMPATIBILITY PATH]",
            "MODE_GENERATIVE [DEAD-END / unsupported in Fireworks-only mode]",
            "MODE_VOICE [LEGACY DEAD-END / use Modern Studio UI or CLI]",
        ])
        mode_layout.addWidget(self.mode_combo)
        ord_layout.addLayout(mode_layout)

        dur_layout = QHBoxLayout()
        dur_layout.addWidget(QLabel("Duration:"))
        self.dur_combo = QComboBox()
        self.dur_combo.addItems(["60s", "30s", "90s", "120s"])
        dur_layout.addWidget(self.dur_combo)
        ord_layout.addLayout(dur_layout)
        
        ar_layout = QHBoxLayout()
        ar_layout.addWidget(QLabel("Aspect Ratio:"))
        self.ar_combo = QComboBox()
        self.ar_combo.addItems(["16:9", "9:16", "1:1"])
        ar_layout.addWidget(self.ar_combo)
        ord_layout.addLayout(ar_layout)

        qual_layout = QHBoxLayout()
        qual_layout.addWidget(QLabel("Quality:"))
        self.qual_combo = QComboBox()
        self.qual_combo.addItems(["High (CRF 18)", "Medium (CRF 23)", "Preview (CRF 28)"])
        qual_layout.addWidget(self.qual_combo)
        ord_layout.addLayout(qual_layout)

        ord_group.setLayout(ord_layout)
        middle_layout.addWidget(ord_group)

        # Cloud Engines
        engines_group = QGroupBox("Cloud Engines")
        engines_layout = QVBoxLayout()

        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("API Vault:"))
        self.api_combo = QComboBox()
        api_layout.addWidget(self.api_combo)
        engines_layout.addLayout(api_layout)

        img_layout = QHBoxLayout()
        img_layout.addWidget(QLabel("Image Engine:"))
        self.img_combo = QComboBox()
        self.img_combo.addItems(["Runware (SOTA)", "Gemini (Fallback)"])
        img_layout.addWidget(self.img_combo)
        engines_layout.addLayout(img_layout)

        voice_layout = QHBoxLayout()
        voice_layout.addWidget(QLabel("Voice Engine:"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["edge-tts (Neural)"])
        voice_layout.addWidget(self.voice_combo)
        engines_layout.addLayout(voice_layout)

        engines_group.setLayout(engines_layout)
        middle_layout.addWidget(engines_group)

        main_layout.addLayout(middle_layout)

        # --- 3. Telemetry ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready for Dispatch")
        main_layout.addWidget(self.progress_bar)

        self.terminal = QTextBrowser()
        self.terminal.setOpenExternalLinks(True)
        main_layout.addWidget(self.terminal, stretch=3)

        # --- 4. Deployment Deck ---
        action_layout = QHBoxLayout()
        self.abort_btn = QPushButton("🔴 ABORT MISSION")
        self.abort_btn.setObjectName("abortBtn")
        self.abort_btn.setEnabled(False)
        self.abort_btn.clicked.connect(self.abort_mission)
        
        self.launch_btn = QPushButton("🚀 LAUNCH PRODUCTION")
        self.launch_btn.setObjectName("launchBtn")
        self.launch_btn.setMinimumHeight(45)
        self.launch_btn.clicked.connect(self.launch_production)

        action_layout.addWidget(self.abort_btn)
        action_layout.addStretch()
        action_layout.addWidget(self.launch_btn, stretch=1)
        
        main_layout.addLayout(action_layout)

    def load_api_vault(self):
        self.api_combo.clear()
        reasoning_key = str(os.getenv("FIREWORKS_API_KEY", "") or "").strip()
        image_key = str(os.getenv("BLF_FLUX2PRO", "") or "").strip()

        def _mask_key(raw_key: str) -> str:
            if len(raw_key) >= 8:
                return f"{raw_key[:4]}...{raw_key[-4:]}"
            if len(raw_key) >= 2:
                return f"{raw_key[:2]}..."
            return "***"

        if reasoning_key:
            self.api_combo.addItem(f"🟢 Reasoning key detected (FIREWORKS_API_KEY: {_mask_key(reasoning_key)})")
        else:
            self.api_combo.addItem("⚠️ Reasoning key missing (FIREWORKS_API_KEY)")

        if image_key:
            self.api_combo.addItem(f"🟢 Image key detected (BLF_FLUX2PRO: {_mask_key(image_key)})")
        else:
            self.api_combo.addItem("⚠️ Image key missing (BLF_FLUX2PRO)")

        self.api_combo.setToolTip(
            'Set keys with: setx FIREWORKS_API_KEY "<reasoning_key>" and setx BLF_FLUX2PRO "<image_key>", then relaunch app.'
        )

    def append_to_terminal(self, text, color="#e0e0e0"):
        # Very simple HTML formatting for terminal lines
        html = f'<span style="color: {color};">{text.replace(" ", "&nbsp;")}</span><br>'
        self.terminal.moveCursor(self.terminal.textCursor().MoveOperation.End)
        self.terminal.insertHtml(html)
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())

    def parse_telemetry_line(self, line):
        """Color-codes terminal output and extracts progress data."""
        clean_line = line.strip()
        if not clean_line: return

        if "❌" in clean_line or "[ERROR]" in clean_line:
            self.append_to_terminal(clean_line, "#ff4d4f")
        elif "✅" in clean_line or "[QA PASSED]" in clean_line:
            self.append_to_terminal(clean_line, "#00e676")
        elif "[COMMANDER]" in clean_line:
            self.append_to_terminal(clean_line, "#00c6ff")
        elif "[INTEL]" in clean_line:
            self.append_to_terminal(clean_line, "#b388ff")
        else:
            self.append_to_terminal(clean_line, "#888888" if clean_line.startswith("  ") else "#e0e0e0")

        # Regex out Epoch progress: E.g., "E[3/13]" or "Epoch 3/13"
        match = re.search(r'E\[?(\d+)/(\d+)\]?', clean_line)
        if match:
            self.current_epoch = int(match.group(1))
            self.epoch_total = int(match.group(2))
            pct = int((self.current_epoch / self.epoch_total) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"Forging... Epoch {self.current_epoch}/{self.epoch_total}")

    def launch_production(self):
        desc = self.description_input.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Invalid Request", "Mission Brief description cannot be empty.")
            return

        mode = strip_mode_label(self.mode_combo.currentText())
        if mode != "MODE_NARRATE":
            meta = get_dead_end_metadata(mode) or get_dead_end_metadata("legacy_launcher")
            message = str(meta.get("message", "Legacy launcher supports MODE_NARRATE compatibility runs only."))
            self.append_to_terminal(message, "#ff4d4f")
            QMessageBox.warning(self, "Legacy Compatibility Shell", message)
            return

        legacy_meta = get_dead_end_metadata("legacy_launcher")

        # Setup UI for active process
        self.terminal.clear()
        self.append_to_terminal("💥 LAUNCH SEQUENCE INITIATED...", "#ffab00")
        self.append_to_terminal(str(legacy_meta.get("message", "")), "#888888")
        self.append_to_terminal(f"Target: {COMMANDER_SCRIPT}", "#888888")
        
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Initializing Pipeline...")
        self.launch_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.description_input.setEnabled(False)

        duration_seconds = int(self.dur_combo.currentText().replace("s", ""))
        duration_plan = resolve_duration_plan(
            input_source="USER_CONTEXT",
            context_rewrite="force",
            narration_style="documentary",
            context_text=desc,
            requested_target_duration=duration_seconds,
        )
        stamp = time.strftime("%Y%m%d_%H%M%S")
        prepared = prepare_narrate_launch(
            script=desc,
            stamp=stamp,
            request_prompt="Create narrated video from provided script.",
            duration_plan=duration_plan,
            narration_style="documentary",
            context_rewrite="force",
            watermark_mode="on",
            voice_preset=DEFAULT_VOICE_PRESET_ID,
            key_probe="off",
            python_executable=sys.executable,
            commander_path=COMMANDER_SCRIPT,
            app_root=APP_STATION_DIR,
            expected_root_name="video_production_agent",
            ui_profile="legacy_launcher:compatibility",
            session_id="legacy-launcher",
            launch_source="legacy_launcher_compat",
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        persist_launch_payload(prepared.payload, stamp)

        self.process.setProgram(sys.executable)
        self.process.setArguments(prepared.arguments)
        self.process.start()

    def abort_mission(self):
        reply = QMessageBox.question(self, "Abort Mission", 
                                    "Are you sure you want to abort the current TVC production?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.append_to_terminal("🔴 ABORT SIGNAL TRANSMITTED. Terminating pipeline...", "#ff4d4f")
            self.process.kill()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf-8", errors="replace")
        for line in stdout.splitlines():
            self.parse_telemetry_line(line)

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf-8", errors="replace")
        for line in stderr.splitlines():
            self.append_to_terminal(line.strip(), "#ff4d4f")

    def process_finished(self, exit_code, exit_status):
        self.launch_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.description_input.setEnabled(True)
        if exit_status == QProcess.ExitStatus.CrashExit:
            self.progress_bar.setFormat("Mission Aborted")
            self.append_to_terminal("❌ PROCESS KILLED", "#ff4d4f")
        elif exit_code != 0:
            self.progress_bar.setFormat(f"Failed (Exit {exit_code})")
            self.append_to_terminal(f"❌ PROCESS FAILED WITH EXIT CODE {exit_code}", "#ff4d4f")
        else:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Mission Accomplished")
            self.append_to_terminal("✅ PROCESS COMPLETED SUCCESSFULLY", "#00e676")

    def process_error(self, error):
        self.append_to_terminal(f"❌ QProcess Error: {self.process.errorString()}", "#ff4d4f")
        self.launch_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.description_input.setEnabled(True)


if __name__ == "__main__":
    # Remove console window for Windows
    import ctypes
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    # Try to load a SOTA font if available
    app.setFont(QFont("Segoe UI", 10))
    
    window = TVCLauncher()
    window.show()
    sys.exit(app.exec())
