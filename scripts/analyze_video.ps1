# Windows entry point. preflight.ps1 is silent once this machine has passed.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $Root "scripts\preflight.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($env:XDG_CACHE_HOME) {
    $Stamp = Join-Path $env:XDG_CACHE_HOME "analyze-video\preflight.json"
} else {
    $Stamp = Join-Path $env:USERPROFILE ".cache\analyze-video\preflight.json"
}
$data = Get-Content -Raw -LiteralPath $Stamp | ConvertFrom-Json
& $data.tools.python3 (Join-Path $Root "scripts\analyze_video.py") @args
exit $LASTEXITCODE
