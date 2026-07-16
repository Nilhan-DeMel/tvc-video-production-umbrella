from pathlib import Path


def test_legacy_shortcut_generator_targets_canonical_repo():
    path = Path(__file__).resolve().parents[1] / "create_shortcut.vbs"
    text = path.read_text(encoding="utf-8")
    assert r"D:\AI-Apps-In-Drive\App_Station\Video_production_agent\Launch_TVC_Empire.vbs" in text
    assert r"D:\AI-Apps-In-Drive\App_Station\Video_production\Launch_TVC_Empire.vbs" not in text
    assert r"D:\AI-Apps-In-Drive\App_Station\Video_production_agent\tvc_icon.ico" in text
