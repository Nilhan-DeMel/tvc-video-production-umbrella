from pathlib import Path


def test_prepare_narrate_launch_auto_duration_builds_context_and_tokens(monkeypatch, tmp_path):
    import tvc_launch_contract as contract

    monkeypatch.setattr(contract, "EVIDENCE_ROOT", str(tmp_path / "Evidence"))
    monkeypatch.setattr(contract, "UI_PAYLOAD_ROOT", str(tmp_path / "Evidence" / "ui_launch_payloads"))

    prepared = contract.prepare_narrate_launch(
        script="A deterministic premium script.",
        stamp="20260318_120000",
        request_prompt="Create narrated video from provided script.",
        duration_plan={
            "duration_mode": "auto",
            "target_duration": None,
            "estimated_duration_seconds": 12,
            "requested_target_duration_seconds": None,
        },
        narration_style="documentary",
        context_rewrite="off",
        watermark_mode="on",
        voice_preset="style_default",
        key_probe="off",
        python_executable="python",
        commander_path="D:/app/supreme_commander.py",
        app_root="D:/app",
        expected_root_name="video_production_agent",
        ui_profile="studio:cinematic",
        session_id="session-1",
        launch_source="studio_agent_ui_v2",
    )

    assert Path(prepared.context_file).exists()
    assert prepared.arguments == ["D:/app/supreme_commander.py", *prepared.cli_tokens]
    assert prepared.payload.command_tokens == ["python", *prepared.arguments]
    assert prepared.payload.context_file == prepared.context_file
    assert prepared.payload.duration_mode == "auto"
    assert "--duration" not in prepared.cli_tokens

    payload_path = contract.persist_launch_payload(prepared.payload, "20260318_120000")
    assert Path(payload_path).exists()


def test_prepare_narrate_launch_manual_duration_includes_duration_flag(monkeypatch, tmp_path):
    import tvc_launch_contract as contract

    monkeypatch.setattr(contract, "EVIDENCE_ROOT", str(tmp_path / "Evidence"))

    prepared = contract.prepare_narrate_launch(
        script="Rewrite-enabled script.",
        stamp="20260318_120001",
        request_prompt="Create narrated video from provided script.",
        duration_plan={
            "duration_mode": "manual",
            "target_duration": 75,
            "estimated_duration_seconds": 14,
            "requested_target_duration_seconds": 75,
        },
        narration_style="sales_saas",
        context_rewrite="force",
        watermark_mode="on",
        voice_preset="style_default",
        key_probe="on",
        python_executable="python",
        commander_path="D:/app/supreme_commander.py",
        app_root="D:/app",
        expected_root_name="video_production_agent",
        ui_profile="legacy:compat",
        session_id="session-2",
        launch_source="legacy_launcher_compat",
    )

    idx = prepared.cli_tokens.index("--duration")
    assert prepared.cli_tokens[idx + 1] == "75"
    assert prepared.payload.target_duration == 75
    assert prepared.payload.requested_target_duration_seconds == 75


def test_dead_end_metadata_exposes_mode_and_surface_labels():
    import tvc_launch_contract as contract

    generative = contract.get_dead_end_metadata("MODE_GENERATIVE")
    launcher = contract.get_dead_end_metadata("legacy_launcher")
    runner = contract.get_dead_end_metadata("tvc_ui_runner.py")

    assert generative["path_state"] == "dead_end"
    assert "MODE_NARRATE" in generative["message"]
    assert launcher["path_state"] == "compatibility_dead_end"
    assert runner["path_state"] == "deprecated_unused"
