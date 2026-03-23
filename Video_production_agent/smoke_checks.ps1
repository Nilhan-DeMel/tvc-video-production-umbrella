Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($PSScriptRoot) {
    Set-Location -LiteralPath $PSScriptRoot
}

function Invoke-SmokeCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath
    )

    Write-Host ""
    Write-Host "=== RUNNING: $ScriptPath ==="
    python $ScriptPath
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "=== FAIL: $ScriptPath (exit $exitCode) ==="
        exit $exitCode
    }

    Write-Host "=== PASS: $ScriptPath ==="
}

Write-Host "Starting API smoke checks..."
Invoke-SmokeCheck -ScriptPath "test_kimi_smoke.py"
Invoke-SmokeCheck -ScriptPath "test_image_smoke.py"
Write-Host ""
Write-Host "All smoke checks passed."
exit 0
