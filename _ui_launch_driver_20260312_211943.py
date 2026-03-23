import os
import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QProcess

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())

from tvc_launcher import TVCLauncher

SCRIPT_TEXT = """The world moves in rhythm, light, and quiet confidence.

A founder steps through polished offices as the day comes alive.

Teams gather, screens glow, and ideas move with purpose.

Meetings begin, conversations flow, and real business takes shape.

Your brand deserves more than flat posts and forgettable visuals.

I create AI-powered videos with elegance, energy, and visual presence.

Show your people, your service, your spaces, and your standard.

Show motion, confidence, clarity, and a business that feels alive.

Bring your message to life with refined social media and LinkedIn videos.

Connect with me on LinkedIn to get social media and LinkedIn videos that promote your business, at the best market price point."""

app = QApplication([])
launcher = TVCLauncher()
launcher.description_input.setPlainText(SCRIPT_TEXT)
launcher.mode_combo.setCurrentText("MODE_NARRATE")
launcher.dur_combo.setCurrentText("60s")
print("[UI-DRIVER] Launching via TVCLauncher.launch_production()")
launcher.launch_production()

start = time.time()
last_state = None
while True:
    app.processEvents()
    state = launcher.process.state()
    if state != last_state:
        print(f"[UI-DRIVER] QProcess state={int(state)}")
        last_state = state
    if state == QProcess.ProcessState.NotRunning:
        break
    if time.time() - start > 7200:
        print("[UI-DRIVER] Timeout reached, killing process")
        launcher.process.kill()
        break
    time.sleep(1.0)

exit_code = launcher.process.exitCode()
print(f"[UI-DRIVER] Completed. exit_code={exit_code}")
sys.exit(0 if exit_code == 0 else exit_code)
