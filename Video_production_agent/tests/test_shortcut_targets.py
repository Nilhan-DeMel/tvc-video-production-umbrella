from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_shortcut_generator_is_self_rooted_and_not_hardcoded_to_standalone_path():
    path = REPO_ROOT / "create_shortcut.vbs"
    text = path.read_text(encoding="utf-8")
    assert "WScript.ScriptFullName" in text
    assert "GetParentFolderName" in text
    assert "Launch_TVC_Empire.vbs" in text
    assert "tvc_icon.ico" in text
    assert r"D:\AI-Apps-In-Drive\App_Station\Video_production_agent\Launch_TVC_Empire.vbs" not in text
    assert r"D:\AI-Apps-In-Drive\App_Station\Video_production\Launch_TVC_Empire.vbs" not in text
