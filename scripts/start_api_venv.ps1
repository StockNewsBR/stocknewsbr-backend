param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $repoRoot "venv\Scripts\python.exe"
$runtimeDir = Join-Path $repoRoot "runtime"
$bootstrapLog = Join-Path $runtimeDir "api-start.log"
$stdoutLog = Join-Path $runtimeDir "api-stdout.log"
$stderrLog = Join-Path $runtimeDir "api-stderr.log"

function Write-StartupLog {
  param([string]$Message)
  $line = "$(Get-Date -Format "yyyy-MM-dd HH:mm:ss") $Message"
  Write-Host $line
  Add-Content -Path $bootstrapLog -Value $line
}

if (-not (Test-Path $runtimeDir)) {
  New-Item -ItemType Directory -Path $runtimeDir | Out-Null
}

if (-not (Test-Path $python)) {
  throw "Project venv python not found at $python"
}

$runtimeCheck = & $python -c "import sys; print('python_executable=' + sys.executable); print('python_version=' + sys.version.replace(chr(10), ' ')); raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 11)"
$runtimeCheck | ForEach-Object { Write-StartupLog $_ }
if ($LASTEXITCODE -ne 0) {
  throw "Project venv must use Python 3.11. Recreate it with: py -3.11 -m venv venv; .\venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
$processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })

foreach ($processId in $processIds) {
  try {
    $process = Get-Process -Id $processId -ErrorAction Stop
    Write-StartupLog "Stopping stale process on port $Port | pid=$processId | name=$($process.ProcessName)"
    Stop-Process -Id $processId -Force
  } catch {
    Write-StartupLog "Process on port $Port already stopped | pid=$processId"
  }
}

Set-Location $repoRoot
$env:PYTHONUNBUFFERED = "1"

Write-StartupLog "Starting StockNewsBR API | host=$HostName | port=$Port"
$arguments = @("-m", "uvicorn", "main:app", "--host", $HostName, "--port", [string]$Port)
$apiProcess = Start-Process `
  -FilePath $python `
  -ArgumentList $arguments `
  -WorkingDirectory $repoRoot `
  -WindowStyle Hidden `
  -PassThru `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog

Write-StartupLog "Started API process | pid=$($apiProcess.Id) | python=$python"

$deadline = (Get-Date).AddSeconds(30)
do {
  Start-Sleep -Milliseconds 500
  $listener = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1
} while (-not $listener -and (Get-Date) -lt $deadline)

if (-not $listener) {
  Write-StartupLog "API failed to listen on port $Port within timeout"
  throw "API failed to listen on port $Port. Check $stdoutLog and $stderrLog."
}

$runtimeProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
Write-StartupLog "API listening | pid=$($listener.OwningProcess) | executable=$($runtimeProcess.ExecutablePath)"
Write-StartupLog "API command | $($runtimeProcess.CommandLine)"
Write-StartupLog "Runtime note | Windows may show the base Python executable for a venv redirector; trust the app Runtime bootstrap sys.executable line above."
