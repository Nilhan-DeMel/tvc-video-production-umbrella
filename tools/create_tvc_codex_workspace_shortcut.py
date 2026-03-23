from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_SCRIPT = REPO_ROOT / "scripts" / "launch_tvc_codex_workspace.ps1"
LIVE_APP_ROOT = REPO_ROOT / "Video_production_agent"
SHORTCUT_NAME = "TVC Codex Workspace.lnk"


def _desktop_path() -> Path:
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_shortcut() -> Path:
    if not LAUNCH_SCRIPT.exists():
        raise FileNotFoundError(f"Launch script not found: {LAUNCH_SCRIPT}")

    shortcut_path = _desktop_path() / SHORTCUT_NAME
    icon_path = LIVE_APP_ROOT / "tvc_icon.ico"
    target = "powershell.exe"
    arguments = f'-NoProfile -ExecutionPolicy Bypass -File "{LAUNCH_SCRIPT}"'

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut({_ps_quote(str(shortcut_path))})
$sc.TargetPath = {_ps_quote(target)}
$sc.Arguments = {_ps_quote(arguments)}
$sc.WorkingDirectory = {_ps_quote(str(REPO_ROOT))}
$sc.IconLocation = {_ps_quote(str(icon_path) + ',0')}
$sc.Description = "Open the canonical TVC workspace and launch Codex from the umbrella repo."
$sc.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return shortcut_path


def main() -> None:
    path = create_shortcut()
    print(f"Created shortcut: {path}")


if __name__ == "__main__":
    main()
