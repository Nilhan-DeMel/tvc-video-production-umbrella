$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python .\tools\check_live_boundary.py
    pytest -q -c .\Video_production_agent\pytest.ini .\Video_production_agent\tests
}
finally {
    Pop-Location
}
