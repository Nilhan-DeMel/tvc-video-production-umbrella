import os
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication


def test_legacy_launcher_uses_shared_contract_and_does_not_write_runner(monkeypatch, tmp_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    import tvc_launcher

    app = QApplication.instance() or QApplication([])
    win = tvc_launcher.TVCLauncher()

    captured = {}

    def fake_prepare(**kwargs):
        captured["prepare"] = kwargs
        return SimpleNamespace(
            context_file=str(tmp_path / "ctx.txt"),
            cli_tokens=["--mode", "MODE_NARRATE", "--context-file", str(tmp_path / "ctx.txt"), "Create narrated video"],
            arguments=[str(tmp_path / "supreme_commander.py"), "--mode", "MODE_NARRATE", "--context-file", str(tmp_path / "ctx.txt"), "Create narrated video"],
            payload=SimpleNamespace(schema_version="ui_launch_payload.v2"),
        )

    monkeypatch.setattr(tvc_launcher, "prepare_narrate_launch", fake_prepare)
    monkeypatch.setattr(tvc_launcher, "persist_launch_payload", lambda payload, stamp: str(tmp_path / "payload.json"))
    monkeypatch.setattr(tvc_launcher, "APP_STATION_DIR", str(tmp_path))
    monkeypatch.setattr(tvc_launcher, "COMMANDER_SCRIPT", str(tmp_path / "supreme_commander.py"))
    monkeypatch.setattr(win.process, "start", lambda: None)

    win.description_input.setPlainText("A legacy-launch compatibility run.")
    win.mode_combo.setCurrentIndex(0)
    win.launch_production()

    assert "prepare" in captured
    assert not (tmp_path / "tvc_ui_runner.py").exists()
    assert win.process.program() == tvc_launcher.sys.executable
    assert win.process.arguments() == [
        str(tmp_path / "supreme_commander.py"),
        "--mode",
        "MODE_NARRATE",
        "--context-file",
        str(tmp_path / "ctx.txt"),
        "Create narrated video",
    ]

    win.close()
