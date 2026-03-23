from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


APP_ROOT = os.path.abspath(os.path.dirname(__file__))
EXPECTED_ROOT_NAME = "video_production_agent"
COMMANDER_PATH = os.path.join(APP_ROOT, "supreme_commander.py")
EVIDENCE_ROOT = os.path.join(APP_ROOT, "Evidence")
UI_PAYLOAD_ROOT = os.path.join(EVIDENCE_ROOT, "ui_launch_payloads")

MODE_NARRATE = "MODE_NARRATE"

DEAD_END_METADATA: Dict[str, Dict[str, str]] = {
    "MODE_GENERATIVE": {
        "path_state": "dead_end",
        "message": (
            "DEAD-END PATH: MODE_GENERATIVE is disabled in Fireworks-only mode. "
            "Use MODE_NARRATE for Fireworks-backed production."
        ),
    },
    "MODE_EXTEND": {
        "path_state": "dead_end",
        "message": (
            "DEAD-END PATH: MODE_EXTEND is disabled in Fireworks-only mode (Veo path unavailable). "
            "Use MODE_NARRATE for Fireworks-backed production."
        ),
    },
    "legacy_launcher": {
        "path_state": "compatibility_dead_end",
        "message": (
            "COMPATIBILITY PATH: the legacy launcher is retained for safety only. "
            "Use the Modern Studio UI as the canonical front door."
        ),
    },
    "tvc_ui_runner.py": {
        "path_state": "deprecated_unused",
        "message": (
            "DEPRECATED PATH: tvc_ui_runner.py is no longer part of the active launch path. "
            "Modern Studio UI and legacy launcher both dispatch directly to supreme_commander.py."
        ),
    },
}


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def write_json(path: str, payload):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)


@dataclass
class LaunchPayloadV2:
    schema_version: str
    timestamp: str
    mode: str
    request_prompt: str
    context_text: str
    context_file: str
    target_duration: Optional[int]
    duration_mode: str
    estimated_duration_seconds: Optional[int]
    requested_target_duration_seconds: Optional[int]
    narration_style: str
    context_rewrite: str
    watermark_mode: str
    voice_preset: str
    key_probe: str
    command_tokens: List[str]
    app_root: str
    expected_root_name: str
    ui_profile: str
    session_id: str
    launch_source: str


@dataclass
class PreparedNarrateLaunch:
    context_file: str
    cli_tokens: List[str]
    arguments: List[str]
    payload: LaunchPayloadV2


def get_dead_end_metadata(key: str) -> Dict[str, str]:
    return dict(DEAD_END_METADATA.get(str(key or ""), {}))


def strip_mode_label(label: str) -> str:
    raw = str(label or "").strip()
    if not raw:
        return ""
    return raw.split(" ", 1)[0].strip()


def write_context_file(script: str, suffix: str) -> str:
    root = os.path.join(EVIDENCE_ROOT, "ui_context_inputs")
    ensure_dir(root)
    path = os.path.join(root, f"context_{suffix}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(script or ""))
    return path


def build_narrate_cli_tokens(
    *,
    context_file: str,
    request_prompt: str,
    narration_style: str,
    context_rewrite: str,
    watermark_mode: str,
    voice_preset: str,
    key_probe: str,
    duration_plan: Dict[str, object],
) -> List[str]:
    tokens = [
        "--mode",
        MODE_NARRATE,
        "--context-file",
        context_file,
        "--narration-style",
        str(narration_style or "documentary").strip(),
        "--context-rewrite",
        str(context_rewrite or "off").strip(),
        "--watermark-mode",
        str(watermark_mode or "on").strip(),
        "--voice-preset",
        str(voice_preset or "style_default").strip(),
        "--key-probe",
        str(key_probe or "off").strip(),
        str(request_prompt or "Create narrated video from provided script.").strip(),
    ]
    if str(duration_plan.get("duration_mode", "manual") or "manual") != "auto":
        manual_duration = duration_plan.get("target_duration")
        if manual_duration is None:
            manual_duration = duration_plan.get("requested_target_duration_seconds")
        if manual_duration is not None:
            tokens[0:0] = ["--duration", str(int(manual_duration))]
    return tokens


def prepare_narrate_launch(
    *,
    script: str,
    stamp: str,
    request_prompt: str,
    duration_plan: Dict[str, object],
    narration_style: str,
    context_rewrite: str,
    watermark_mode: str,
    voice_preset: str,
    key_probe: str,
    python_executable: str,
    commander_path: str = COMMANDER_PATH,
    app_root: str = APP_ROOT,
    expected_root_name: str = EXPECTED_ROOT_NAME,
    ui_profile: str,
    session_id: str,
    launch_source: str,
    timestamp: Optional[str] = None,
) -> PreparedNarrateLaunch:
    context_file = write_context_file(script, stamp)
    cli_tokens = build_narrate_cli_tokens(
        context_file=context_file,
        request_prompt=request_prompt,
        narration_style=narration_style,
        context_rewrite=context_rewrite,
        watermark_mode=watermark_mode,
        voice_preset=voice_preset,
        key_probe=key_probe,
        duration_plan=duration_plan,
    )
    arguments = [str(commander_path), *cli_tokens]
    payload = LaunchPayloadV2(
        schema_version="ui_launch_payload.v2",
        timestamp=str(timestamp or "").strip(),
        mode=MODE_NARRATE,
        request_prompt=str(request_prompt or "").strip(),
        context_text=str(script or ""),
        context_file=context_file,
        target_duration=duration_plan.get("target_duration"),
        duration_mode=str(duration_plan.get("duration_mode", "auto") or "auto"),
        estimated_duration_seconds=duration_plan.get("estimated_duration_seconds"),
        requested_target_duration_seconds=duration_plan.get("requested_target_duration_seconds"),
        narration_style=str(narration_style or "documentary").strip(),
        context_rewrite=str(context_rewrite or "off").strip(),
        watermark_mode=str(watermark_mode or "on").strip(),
        voice_preset=str(voice_preset or "style_default").strip(),
        key_probe=str(key_probe or "off").strip(),
        command_tokens=[str(python_executable), *arguments],
        app_root=str(app_root or APP_ROOT),
        expected_root_name=str(expected_root_name or EXPECTED_ROOT_NAME),
        ui_profile=str(ui_profile or ""),
        session_id=str(session_id or ""),
        launch_source=str(launch_source or ""),
    )
    return PreparedNarrateLaunch(
        context_file=context_file,
        cli_tokens=cli_tokens,
        arguments=arguments,
        payload=payload,
    )


def persist_launch_payload(payload: LaunchPayloadV2, stamp: str) -> str:
    ensure_dir(UI_PAYLOAD_ROOT)
    path = os.path.join(UI_PAYLOAD_ROOT, f"ui_launch_payload_{stamp}.json")
    write_json(path, asdict(payload))
    return path
