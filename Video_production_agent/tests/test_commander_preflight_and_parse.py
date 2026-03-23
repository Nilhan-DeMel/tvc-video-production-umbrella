import importlib
import json
import sys
from pathlib import Path

import pytest


def _load_commander(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test_preflight_key_123456")
    if "supreme_commander" in sys.modules:
        del sys.modules["supreme_commander"]
    import supreme_commander

    importlib.reload(supreme_commander)
    monkeypatch.setattr(supreme_commander, "OUTPUT_DIR", str(tmp_path))
    return supreme_commander


def test_parse_narrate_runtime_flags_from_tokens_windows_path(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    context_file = tmp_path / "ctx file.txt"
    context_file.write_text("hello from context", encoding="utf-8")

    tokens = [
        "--context-file",
        str(context_file),
        "--context-rewrite",
        "off",
        "--watermark-mode",
        "on",
        "Create",
        "video",
    ]

    cleaned, resolved, ctx_path, style, rewrite, watermark, voice_preset, key_probe = (
        commander.parse_narrate_runtime_flags_from_tokens(tokens)
    )
    assert cleaned == "Create video"
    assert resolved == "hello from context"
    assert Path(ctx_path) == context_file
    assert style == "documentary"
    assert rewrite == "off"
    assert watermark == "on"
    assert voice_preset == "style_default"
    assert key_probe == ""


def test_parse_narrate_context_file_drive_root_rejected(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    tokens = ["--context-file", r"D:\\", "Create", "video"]
    with pytest.raises(ValueError) as exc:
        commander.parse_narrate_runtime_flags_from_tokens(tokens)
    assert "drive root" in str(exc.value).lower() or "directory" in str(exc.value).lower()


def test_parse_narrate_runtime_flags_from_tokens_key_probe(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    context_file = tmp_path / "ctx.txt"
    context_file.write_text("ctx", encoding="utf-8")
    tokens = [
        "--context-file",
        str(context_file),
        "--key-probe",
        "on",
        "Create",
        "video",
    ]
    _, _, _, _, _, _, _, key_probe = commander.parse_narrate_runtime_flags_from_tokens(tokens)
    assert key_probe == "on"


def test_parse_narrate_runtime_flags_from_tokens_voice_preset(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    tokens = [
        "--voice-preset",
        "jenny_marketing",
        "Create",
        "video",
    ]
    cleaned, _, _, _, _, _, voice_preset, _ = commander.parse_narrate_runtime_flags_from_tokens(tokens)
    assert cleaned == "Create video"
    assert voice_preset == "jenny_marketing"


def test_supreme_video_commander_user_context_uses_auto_duration(monkeypatch, tmp_path, capsys):
    commander = _load_commander(monkeypatch, tmp_path)
    context_file = tmp_path / "ctx.txt"
    context_file.write_text("One two three four five six seven eight nine ten.", encoding="utf-8")

    captured = {}

    monkeypatch.setattr(
        commander,
        "_startup_preflight_for_narrate",
        lambda **kwargs: (True, {"resolved": {}, "key_probe_mode": "off"}),
    )

    def _fake_dispatch(mode, request, output_path, **kwargs):
        captured.update(kwargs)
        return {"mode": mode, "status": "success", "output": str(tmp_path / "out.mp4"), "error": None, "size_mb": None}

    monkeypatch.setattr(commander, "dispatch_weapon", _fake_dispatch)

    commander.supreme_video_commander(
        "Create narrated video from provided script",
        cli_tokens=[
            "--mode",
            "MODE_NARRATE",
            "--context-file",
            str(context_file),
            "Create narrated video from provided script",
        ],
    )

    output = capsys.readouterr().out
    assert "Duration Override Detected" not in output
    assert "Duration Mode: AUTO_FROM_SCRIPT" in output
    assert captured["input_source"] == "USER_CONTEXT"
    assert captured["duration_mode"] == "auto"
    assert captured["requested_target_duration_seconds"] is None
    assert int(captured["target_duration"]) > 0


def test_supreme_video_commander_ignores_manual_duration_for_deterministic_user_context(monkeypatch, tmp_path, capsys):
    commander = _load_commander(monkeypatch, tmp_path)
    context_file = tmp_path / "ctx.txt"
    context_file.write_text("One two three four five six seven eight nine ten.", encoding="utf-8")

    captured = {}

    monkeypatch.setattr(
        commander,
        "_startup_preflight_for_narrate",
        lambda **kwargs: (True, {"resolved": {}, "key_probe_mode": "off"}),
    )

    def _fake_dispatch(mode, request, output_path, **kwargs):
        captured.update(kwargs)
        return {"mode": mode, "status": "success", "output": str(tmp_path / "out.mp4"), "error": None, "size_mb": None}

    monkeypatch.setattr(commander, "dispatch_weapon", _fake_dispatch)

    commander.supreme_video_commander(
        "Create narrated video from provided script",
        cli_tokens=[
            "--mode",
            "MODE_NARRATE",
            "--duration",
            "60",
            "--context-file",
            str(context_file),
            "Create narrated video from provided script",
        ],
    )

    output = capsys.readouterr().out
    assert "Duration Override Detected" not in output
    assert "manual duration ignored" in output
    assert captured["duration_mode"] == "auto"
    assert captured["requested_target_duration_seconds"] is None


def test_supreme_video_commander_force_rewrite_keeps_manual_duration(monkeypatch, tmp_path, capsys):
    commander = _load_commander(monkeypatch, tmp_path)
    context_file = tmp_path / "ctx.txt"
    context_file.write_text("One two three four five six seven eight nine ten.", encoding="utf-8")

    captured = {}

    monkeypatch.setattr(
        commander,
        "_startup_preflight_for_narrate",
        lambda **kwargs: (True, {"resolved": {}, "key_probe_mode": "off"}),
    )

    def _fake_dispatch(mode, request, output_path, **kwargs):
        captured.update(kwargs)
        return {"mode": mode, "status": "success", "output": str(tmp_path / "out.mp4"), "error": None, "size_mb": None}

    monkeypatch.setattr(commander, "dispatch_weapon", _fake_dispatch)

    commander.supreme_video_commander(
        "Create narrated video from provided script",
        cli_tokens=[
            "--mode",
            "MODE_NARRATE",
            "--duration",
            "75",
            "--context-file",
            str(context_file),
            "--context-rewrite",
            "force",
            "Create narrated video from provided script",
        ],
    )

    output = capsys.readouterr().out
    assert "Duration Override Detected: 75s" in output
    assert captured["duration_mode"] == "manual"
    assert captured["requested_target_duration_seconds"] == 75
    assert captured["target_duration"] == 75


def test_startup_preflight_missing_keys_writes_artifact(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    monkeypatch.setattr(
        commander,
        "try_get_secret",
        lambda alias: {
            "ok": False,
            "error_code": "missing_env",
            "message": "missing",
            "canonical_secret": "FIREWORKS_API_KEY" if alias == "key_HGmChvaB" else "BLF_FLUX2PRO",
        },
    )

    ok, meta = commander._startup_preflight_for_narrate(
        mode="MODE_NARRATE",
        request_text="Create video ad",
        cli_tokens=["--mode", "MODE_NARRATE"],
        run_attempt_id="attempt-test-1",
        key_probe_mode="off",
    )

    assert ok is False
    artifact = Path(meta["artifact"])
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["error_code"] == "missing_env"
    assert "FIREWORKS_API_KEY" in payload["missing"]


def test_startup_preflight_user_scope_resolution(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)

    def _fake_try(alias):
        if alias == "key_HGmChvaB":
            return {
                "ok": True,
                "key": "fw_key",
                "resolved_env_var": "FIREWORKS_API_KEY",
                "resolved_scope": "user",
                "canonical_secret": "FIREWORKS_API_KEY",
            }
        return {
            "ok": True,
            "key": "flux_key",
            "resolved_env_var": "BLF_FLUX2PRO",
            "resolved_scope": "user",
            "canonical_secret": "BLF_FLUX2PRO",
        }

    monkeypatch.setattr(commander, "try_get_secret", _fake_try)
    ok, meta = commander._startup_preflight_for_narrate(
        mode="MODE_NARRATE",
        request_text="Create video ad",
        cli_tokens=[],
        run_attempt_id="attempt-test-2",
        key_probe_mode="off",
    )
    assert ok is True
    assert meta["resolved"]["fireworks"]["scope"] == "user"
    assert meta["resolved"]["flux"]["scope"] == "user"


def test_dispatch_weapon_marks_mode_generative_as_dead_end(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)

    result = commander.dispatch_weapon(
        mode="MODE_GENERATIVE",
        request="Create generative video",
        output_path=str(tmp_path / "out.mp4"),
    )

    assert result["status"] == "unsupported_mode"
    assert "dead-end path" in str(result["error"]).lower()


def test_dispatch_weapon_marks_mode_extend_as_dead_end(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)

    result = commander.dispatch_weapon(
        mode="MODE_EXTEND",
        request="Extend this video",
        output_path=str(tmp_path / "out.mp4"),
    )

    assert result["status"] == "unsupported_mode"
    assert "dead-end path" in str(result["error"]).lower()


def test_startup_preflight_probe_auth_failure(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    monkeypatch.setattr(
        commander,
        "try_get_secret",
        lambda alias: {
            "ok": True,
            "key": "k",
            "resolved_env_var": "FIREWORKS_API_KEY" if alias == "key_HGmChvaB" else "BLF_FLUX2PRO",
            "resolved_scope": "process",
            "canonical_secret": "FIREWORKS_API_KEY" if alias == "key_HGmChvaB" else "BLF_FLUX2PRO",
        },
    )
    monkeypatch.setattr(
        commander,
        "_probe_fireworks_key",
        lambda key: {"ok": False, "error_code": "invalid_key", "message": "401", "endpoint": "fw", "status_code": 401},
    )
    monkeypatch.setattr(
        commander,
        "_probe_bfl_key",
        lambda key: {"ok": True, "error_code": "", "message": "ok", "endpoint": "bfl", "status_code": 200},
    )

    ok, meta = commander._startup_preflight_for_narrate(
        mode="MODE_NARRATE",
        request_text="Create video ad",
        cli_tokens=[],
        run_attempt_id="attempt-test-3",
        key_probe_mode="on",
    )
    assert ok is False
    assert meta["error_code"] == "invalid_key"
    assert Path(meta["artifact"]).exists()


def test_startup_preflight_probe_unreachable(monkeypatch, tmp_path):
    commander = _load_commander(monkeypatch, tmp_path)
    monkeypatch.setattr(
        commander,
        "try_get_secret",
        lambda alias: {
            "ok": True,
            "key": "k",
            "resolved_env_var": "FIREWORKS_API_KEY" if alias == "key_HGmChvaB" else "BLF_FLUX2PRO",
            "resolved_scope": "process",
            "canonical_secret": "FIREWORKS_API_KEY" if alias == "key_HGmChvaB" else "BLF_FLUX2PRO",
        },
    )
    monkeypatch.setattr(
        commander,
        "_probe_fireworks_key",
        lambda key: {"ok": False, "error_code": "probe_unreachable", "message": "timeout", "endpoint": "fw", "status_code": 0},
    )
    monkeypatch.setattr(
        commander,
        "_probe_bfl_key",
        lambda key: {"ok": True, "error_code": "", "message": "ok", "endpoint": "bfl", "status_code": 200},
    )

    ok, meta = commander._startup_preflight_for_narrate(
        mode="MODE_NARRATE",
        request_text="Create video ad",
        cli_tokens=[],
        run_attempt_id="attempt-test-4",
        key_probe_mode="on",
    )
    assert ok is False
    assert meta["error_code"] == "probe_unreachable"
    assert Path(meta["artifact"]).exists()


def test_supreme_video_commander_accepts_contract_built_tokens(monkeypatch, tmp_path):
    import tvc_launch_contract as contract

    commander = _load_commander(monkeypatch, tmp_path)
    monkeypatch.setattr(contract, "EVIDENCE_ROOT", str(tmp_path / "Evidence"))

    prepared = contract.prepare_narrate_launch(
        script="One two three four five six seven eight nine ten.",
        stamp="20260318_121500",
        request_prompt="Create narrated video from provided script.",
        duration_plan={
            "duration_mode": "auto",
            "target_duration": None,
            "estimated_duration_seconds": 5,
            "requested_target_duration_seconds": None,
        },
        narration_style="documentary",
        context_rewrite="off",
        watermark_mode="on",
        voice_preset="style_default",
        key_probe="off",
        python_executable=sys.executable,
        commander_path=str(tmp_path / "supreme_commander.py"),
        app_root=str(tmp_path),
        expected_root_name="video_production_agent",
        ui_profile="studio:cinematic",
        session_id="session-contract",
        launch_source="studio_agent_ui_v2",
    )

    captured = {}

    monkeypatch.setattr(
        commander,
        "_startup_preflight_for_narrate",
        lambda **kwargs: (True, {"resolved": {}, "key_probe_mode": "off"}),
    )

    def _fake_dispatch(mode, request, output_path, **kwargs):
        captured.update(kwargs)
        return {
            "mode": mode,
            "status": "success",
            "output": str(tmp_path / "out.mp4"),
            "error": None,
            "size_mb": None,
        }

    monkeypatch.setattr(commander, "dispatch_weapon", _fake_dispatch)

    commander.supreme_video_commander(
        prepared.payload.request_prompt,
        cli_tokens=prepared.cli_tokens,
    )

    assert captured["input_source"] == "USER_CONTEXT"
    assert captured["duration_mode"] == "auto"
    assert captured["requested_target_duration_seconds"] is None
