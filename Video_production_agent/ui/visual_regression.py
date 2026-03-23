from __future__ import annotations

import os
import time

from PyQt6.QtWidgets import QApplication

from .main_window import TVCStudioAgentWindow
from .paths import EVIDENCE_ROOT


def capture_golden_states() -> str:
    platform = str(os.environ.get("TVC_UI_CAPTURE_PLATFORM", "") or "").strip().lower()
    if platform:
        os.environ["QT_QPA_PLATFORM"] = platform
    os.environ["TVC_UI_CAPTURE"] = "1"
    app = QApplication.instance() or QApplication([])
    win = TVCStudioAgentWindow()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(EVIDENCE_ROOT, "ui_golden", stamp)
    os.makedirs(out_dir, exist_ok=True)

    sizes = [(1366, 768), (1920, 1080), (2560, 1440)]
    pages = [
        (0, "narrate"),
        (1, "post"),
        (2, "runs"),
        (3, "settings"),
    ]
    for w, h in sizes:
        win.resize(w, h)
        app.processEvents()
        for page_idx, page_name in pages:
            win.left_nav.setCurrentRow(page_idx)
            app.processEvents()
            shot = win.grab()
            shot.save(os.path.join(out_dir, f"{w}x{h}_{page_name}.png"))

    win.close()
    return out_dir


if __name__ == "__main__":
    folder = capture_golden_states()
    print(folder)
