"""Deprecated compatibility shim.

DEAD-END PATH: this file is no longer generated or required by active launch
surfaces. Modern Studio UI and the legacy launcher now dispatch directly to
supreme_commander.py.
"""

import sys

from supreme_commander import supreme_video_commander


if __name__ == "__main__":
    supreme_video_commander(" ".join(sys.argv[1:]), cli_tokens=list(sys.argv[1:]) if len(sys.argv) > 1 else None)
