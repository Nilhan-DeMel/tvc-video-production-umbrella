from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_APP_ROOT = REPO_ROOT / "Video_production_agent"
WORKSPACE_LAUNCH_SCRIPT = REPO_ROOT / "scripts" / "launch_tvc_codex_workspace.ps1"
ICON_PATH = LIVE_APP_ROOT / "tvc_icon.ico"


def _desktop_path() -> Path:
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def _pythonw() -> str:
    exe = os.path.abspath(sys.executable)
    if exe.lower().endswith("python.exe"):
        alt = exe[:-10] + "pythonw.exe"
        if os.path.exists(alt):
            return alt
    return exe


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def refresh_shortcuts() -> list[Path]:
    desktop = _desktop_path()
    target_pythonw = _pythonw()
    shortcuts = [
        {
            "name": "TVC Studio Agent.lnk",
            "target": target_pythonw,
            "arguments": f'"{LIVE_APP_ROOT / "tvc_studio_agent_ui.py"}"',
            "working_directory": str(LIVE_APP_ROOT),
            "icon": str(ICON_PATH) + ",0",
            "description": "TVC Studio Agent (tvc_umbrella_repo)",
        },
        {
            "name": "TVC Emperor.lnk",
            "target": "wscript.exe",
            "arguments": f'"{LIVE_APP_ROOT / "Launch_TVC_Empire.vbs"}"',
            "working_directory": str(LIVE_APP_ROOT),
            "icon": str(ICON_PATH) + ",0",
            "description": "Launch TVC Video Production (tvc_umbrella_repo)",
        },
        {
            "name": "TVC Codex Workspace.lnk",
            "target": "powershell.exe",
            "arguments": f'-NoProfile -ExecutionPolicy Bypass -File "{WORKSPACE_LAUNCH_SCRIPT}"',
            "working_directory": str(REPO_ROOT),
            "icon": str(ICON_PATH) + ",0",
            "description": "Open the canonical TVC workspace and launch Codex from the umbrella repo.",
        },
    ]

    created: list[Path] = []
    for shortcut in shortcuts:
        shortcut_path = desktop / shortcut["name"]
        ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut({_ps_quote(str(shortcut_path))})
$sc.TargetPath = {_ps_quote(shortcut['target'])}
$sc.Arguments = {_ps_quote(shortcut['arguments'])}
$sc.WorkingDirectory = {_ps_quote(shortcut['working_directory'])}
$sc.IconLocation = {_ps_quote(shortcut['icon'])}
$sc.Description = {_ps_quote(shortcut['description'])}
$sc.Save()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        created.append(shortcut_path)
    return created


def main() -> None:
    created = refresh_shortcuts()
    for path in created:
        print(f"Refreshed shortcut: {path}")


if __name__ == "__main__":
    main()
