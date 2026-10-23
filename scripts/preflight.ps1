# Windows preflight. Prints nothing once this machine has passed.
$ErrorActionPreference = "Stop"
$Version = 1
if ($env:XDG_CACHE_HOME) {
    $Stamp = Join-Path $env:XDG_CACHE_HOME "analyze-video\preflight.json"
} else {
    $Stamp = Join-Path $env:USERPROFILE ".cache\analyze-video\preflight.json"
}

function Get-Hint([string]$Name) {
    switch ($Name) {
        "python3" { "winget install --id Python.Python.3.12 -e" }
        "Pillow" { "py -3 -m pip install Pillow" }
        "ffmpeg" { "winget install --id Gyan.FFmpeg -e" }
        "whisper-cli" { "Download whisper-bin-x64.zip from https://github.com/ggml-org/whisper.cpp/releases, unzip it, and put the folder that holds whisper-cli.exe on PATH." }
        "curl" { "Install curl.exe and put it on PATH" }
        default { "Install $Name and rerun" }
    }
}

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return (& py -3 -c "import sys; print(sys.executable)").Trim()
        }
    }
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $cmd) { continue }
        & $cmd.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $cmd.Source }
    }
    return $null
}

function Find-Tool([string]$Name) {
    # Programs only. Windows PowerShell 5.1 makes curl an alias for Invoke-WebRequest,
    # and an alias has no path, so curl.exe would look missing.
    $cmd = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    return $null
}

$Python = Find-Python
if ((Test-Path -LiteralPath $Stamp) -and $Python) {
    $env:STAMP = $Stamp
    $env:VERSION = "$Version"
    # The code goes to Python on stdin. Windows PowerShell 5.1 strips the double
    # quotes inside a native argument, which breaks python -c.
    @'
import json, os, sys
from pathlib import Path
stamp = Path(os.environ["STAMP"])
try:
    data = json.loads(stamp.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
if data.get("version") != int(os.environ["VERSION"]):
    raise SystemExit(1)
tools = data.get("tools") or {}
if os.path.realpath(sys.executable) != tools.get("python3"):
    raise SystemExit(1)
if sys.version_info < (3, 9):
    raise SystemExit(1)
for name in ("ffmpeg", "ffprobe", "whisper-cli", "curl"):
    path = tools.get(name) or ""
    if not path or not os.access(path, os.X_OK):
        raise SystemExit(1)
try:
    import PIL
except ImportError:
    raise SystemExit(1)
'@ | & $Python -
    if ($LASTEXITCODE -eq 0) { exit 0 }
}

$Missing = @()
function Add-Missing([string]$Name, [string]$Detail) {
    $script:Missing += "- ${Name}: ${Detail}`n  $(Get-Hint $Name)"
}

if (-not $Python) {
    $old = Get-Command python3 -ErrorAction SilentlyContinue
    if ($old) {
        $got = (& $old.Source -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null)
        if (-not $got) { $got = "unknown" }
        Add-Missing "python3" "need 3.9+ (found $($got.Trim()))"
    } else {
        Add-Missing "python3" "not on PATH (need 3.9+)"
    }
} else {
    & $Python -c "import PIL" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Add-Missing "Pillow" "not installed for $Python"
    }
}

$Ffmpeg = Find-Tool "ffmpeg"
$Ffprobe = Find-Tool "ffprobe"
if (-not $Ffmpeg -or -not $Ffprobe) {
    Add-Missing "ffmpeg" "ffmpeg and ffprobe must both be on PATH"
}
$Whisper = Find-Tool "whisper-cli"
if (-not $Whisper) {
    Add-Missing "whisper-cli" "not on PATH"
}
$Curl = Find-Tool "curl"
if (-not $Curl) {
    Add-Missing "curl" "not on PATH (used to download the Whisper model)"
}

if ($Missing.Count -gt 0) {
    [Console]::Error.WriteLine("prerequisite missing:")
    foreach ($line in $Missing) {
        [Console]::Error.WriteLine($line)
    }
    exit 1
}

$env:STAMP = $Stamp
$env:VERSION = "$Version"
$env:PY = $Python
$env:FFMPEG = $Ffmpeg
$env:FFPROBE = $Ffprobe
$env:WHISPER = $Whisper
$env:CURL = $Curl
@'
import json, os, sys
from pathlib import Path
import PIL
stamp = Path(os.environ["STAMP"])
stamp.parent.mkdir(parents=True, exist_ok=True)
data = {
    "version": int(os.environ["VERSION"]),
    "python_version": "%d.%d.%d" % sys.version_info[:3],
    "pillow": getattr(PIL, "__version__", ""),
    "tools": {
        "python3": os.path.realpath(sys.executable),
        "ffmpeg": os.path.realpath(os.environ["FFMPEG"]),
        "ffprobe": os.path.realpath(os.environ["FFPROBE"]),
        "whisper-cli": os.path.realpath(os.environ["WHISPER"]),
        "curl": os.path.realpath(os.environ["CURL"]),
    },
}
stamp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
'@ | & $Python -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
exit 0
