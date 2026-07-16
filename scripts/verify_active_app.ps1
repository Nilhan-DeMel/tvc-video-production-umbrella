$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python .\tools\check_live_boundary.py
    if ($LASTEXITCODE -ne 0) {
        throw "Live boundary verification failed with exit code $LASTEXITCODE."
    }
    pytest -q -c .\Video_production_agent\pytest.ini .\Video_production_agent\tests
    if ($LASTEXITCODE -ne 0) {
        throw "Active application tests failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
