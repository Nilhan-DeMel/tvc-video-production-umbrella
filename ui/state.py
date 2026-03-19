from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from .paths import UI_STATE_PATH


@dataclass
class UIState:
    theme_id: str = "aurora_graphite"
    density: str = "cozy"
    performance_mode: str = "balanced"
    motion_profile: str = "cinematic"
    layout_mode: str = "command_deck"
    reduced_motion: bool = False
    inspector_density: str = "comfortable"
    panel_visibility: Dict[str, bool] = field(
        default_factory=lambda: {
            "left_nav": True,
            "right_inspector": True,
            "command_preview": True,
            "live_console": True,
            "video_preview": True,
        }
    )
    splitter_state: str = ""
    recent_runs: List[str] = field(default_factory=list)


def load_ui_state() -> UIState:
    if not os.path.exists(UI_STATE_PATH):
        return UIState()
    try:
        with open(UI_STATE_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        base = UIState()
        for key in (
            "theme_id",
            "density",
            "performance_mode",
            "motion_profile",
            "layout_mode",
            "reduced_motion",
            "inspector_density",
            "panel_visibility",
            "splitter_state",
            "recent_runs",
        ):
            if key in payload:
                setattr(base, key, payload[key])
        if not isinstance(base.panel_visibility, dict):
            base.panel_visibility = UIState().panel_visibility
        if not isinstance(base.recent_runs, list):
            base.recent_runs = []
        if base.inspector_density not in {"comfortable", "compact"}:
            base.inspector_density = "comfortable"
        if base.motion_profile not in {"cinematic", "focused", "calm"}:
            base.motion_profile = "cinematic"
        if base.layout_mode not in {"command_deck", "balanced_shell"}:
            base.layout_mode = "command_deck"
        base.reduced_motion = bool(base.reduced_motion)
        return base
    except Exception:
        return UIState()


def save_ui_state(state: UIState):
    os.makedirs(os.path.dirname(UI_STATE_PATH), exist_ok=True)
    with open(UI_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(asdict(state), fh, indent=2, ensure_ascii=True)
