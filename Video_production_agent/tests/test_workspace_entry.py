from pathlib import Path


REPO_ROOT = Path(r"D:\AI-Apps-In-Drive\App_Station\tvc_umbrella_repo")


def test_workspace_launcher_assets_exist_and_point_to_canonical_repo():
    launch_script = REPO_ROOT / "scripts" / "launch_tvc_codex_workspace.ps1"
    shortcut_tool = REPO_ROOT / "tools" / "create_tvc_codex_workspace_shortcut.py"

    assert launch_script.exists()
    assert shortcut_tool.exists()

    text = launch_script.read_text(encoding="utf-8")
    assert "OpenAI.Codex_2p2nqsd0c76g0!App" in text
    assert 'Join-Path $RepoRoot "Video_production_agent"' in text
    assert "TVC Codex Workspace" in text
