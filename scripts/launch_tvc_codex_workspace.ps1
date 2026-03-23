$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LiveAppRoot = Join-Path $RepoRoot "Video_production_agent"
$CodexAppTarget = "shell:AppsFolder\OpenAI.Codex_2p2nqsd0c76g0!App"
$WorkspaceTitle = "TVC Codex Workspace"

try {
    Set-Clipboard -Value $LiveAppRoot
}
catch {
    # Clipboard is best effort only.
}

Start-Process explorer.exe $LiveAppRoot
Start-Process explorer.exe $CodexAppTarget

Write-Host "$WorkspaceTitle launched."
Write-Host "Live app root: $LiveAppRoot"
Write-Host "The live app path has been copied to the clipboard when available."
