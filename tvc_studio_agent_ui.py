import os
import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import TVCStudioAgentWindow
from ui.paths import APP_ROOT, EXPECTED_ROOT_NAME


def main():
    if os.path.basename(os.path.normpath(APP_ROOT)).lower() != EXPECTED_ROOT_NAME:
        raise SystemExit(
            f"TVC Studio Agent launch blocked: root must be {EXPECTED_ROOT_NAME}. Current root: {APP_ROOT}"
        )
    app = QApplication(sys.argv)
    win = TVCStudioAgentWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

