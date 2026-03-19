Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [string]$FireworksApiKey,
    [string]$BflImageApiKey
)

if (-not $FireworksApiKey) {
    $FireworksApiKey = Read-Host "Enter Fireworks reasoning key (persist as FIREWORKS_API_KEY)"
}

if (-not $BflImageApiKey) {
    $BflImageApiKey = Read-Host "Enter BFL image key (persist as BLF_FLUX2PRO)"
}

$FireworksApiKey = ($FireworksApiKey ?? "").Trim()
$BflImageApiKey = ($BflImageApiKey ?? "").Trim()
if (-not $FireworksApiKey -or -not $BflImageApiKey) {
    Write-Host "[SETUP-ERROR] One or more keys are empty. Nothing changed."
    exit 1
}

# Persist at user scope for new sessions.
setx FIREWORKS_API_KEY "$FireworksApiKey" | Out-Null
setx BLF_FLUX2PRO "$BflImageApiKey" | Out-Null

# Also apply to current session for immediate use.
$env:FIREWORKS_API_KEY = $FireworksApiKey
$env:BLF_FLUX2PRO = $BflImageApiKey

Write-Host "[SETUP-OK] FIREWORKS_API_KEY and BLF_FLUX2PRO set for this session and persisted for your user profile."
Write-Host "[SETUP-NOTE] Restart app/terminal sessions that were already open."
exit 0
