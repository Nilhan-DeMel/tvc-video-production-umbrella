from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = ROOT / "Video_production_agent"

SCAN_DIRS = [
    LIVE_ROOT / "ui",
    LIVE_ROOT / "tvc_nodes",
]

SCAN_FILES = [
    LIVE_ROOT / "create_shortcut.vbs",
    LIVE_ROOT / "make_agent_ui_shortcut.py",
    LIVE_ROOT / "make_shortcut.py",
    LIVE_ROOT / "supreme_commander.py",
    LIVE_ROOT / "tvc_duration.py",
    LIVE_ROOT / "tvc_key_audit.py",
    LIVE_ROOT / "tvc_langgraph_core.py",
    LIVE_ROOT / "tvc_launch_contract.py",
    LIVE_ROOT / "tvc_launcher.py",
    LIVE_ROOT / "tvc_postproduction.py",
    LIVE_ROOT / "tvc_studio_agent_ui.py",
    LIVE_ROOT / "tvc_vault.py",
    LIVE_ROOT / "tvc_voice_registry.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(r"App_Station[\\\\/]+Video_production(?=[\\\\/])", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9_])Video_production(?=[\\\\/])", re.IGNORECASE),
]


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in SCAN_FILES:
        if path.exists():
            files.append(path)
    for folder in SCAN_DIRS:
        if not folder.exists():
            continue
        files.extend(
            p
            for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in {".py", ".vbs", ".ps1", ".bat", ".cmd", ".json", ".toml"}
        )
    seen: set[Path] = set()
    ordered: list[Path] = []
    for item in files:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def main() -> int:
    findings: list[str] = []
    for path in _candidate_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            findings.append(f"{path}: unreadable ({exc})")
            continue
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path}:{line_no}: forbidden legacy runtime reference -> {match.group(0)}")
    if findings:
        print("Live boundary check failed:")
        for item in findings:
            print(item)
        return 1
    print("Live boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
