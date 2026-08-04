param(
  [string]$ApiHost = "127.0.0.1",
  [int]$ApiPort = 8000,
  [string]$WebHost = "127.0.0.1",
  [int]$WebPort = 3000,
  [string]$PanelTicker = "F",
  [ValidateSet("dev", "start")]
  [string]$WebMode = "dev",
  [switch]$SkipSmoke,
  [switch]$SkipBrowserSmoke
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $repoRoot "runtime"
$startLog = Join-Path $runtimeDir "start-all-local.log"
$webStdoutLog = Join-Path $runtimeDir "web-stdout.log"
$webStderrLog = Join-Path $runtimeDir "web-stderr.log"
$browserStdoutLog = Join-Path $runtimeDir "browser-smoke-stdout.log"
$browserStderrLog = Join-Path $runtimeDir "browser-smoke-stderr.log"

function Write-Log {
  param([string]$Message)
  $line = "$(Get-Date -Format "yyyy-MM-dd HH:mm:ss") $Message"
  Write-Host $line
  Add-Content -Path $startLog -Value $line
}

function Stop-PortListeners {
  param(
    [int]$Port,
    [string]$Name
  )

  $connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
  $processIds = @(
    $connections |
      Select-Object -ExpandProperty OwningProcess -Unique |
      Where-Object { $_ -gt 0 }
  )

  if ($processIds.Count -eq 0) {
    Write-Log "No stale $Name process on port $Port"
    return
  }

  foreach ($processId in $processIds) {
    try {
      $process = Get-Process -Id $processId -ErrorAction Stop
      Write-Log "Stopping stale $Name process | port=$Port | pid=$processId | name=$($process.ProcessName)"
      Stop-Process -Id $processId -Force
    } catch {
      Write-Log "Stale $Name process already stopped | port=$Port | pid=$processId"
    }
  }

  Start-Sleep -Milliseconds 500
}

function Wait-HttpOk {
  param(
    [string]$Url,
    [string]$Name,
    [int]$TimeoutSeconds = 60
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $lastError = $null

  do {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        Write-Log "$Name ready | url=$Url | status=$($response.StatusCode)"
        return $response
      }
      $lastError = "status=$($response.StatusCode)"
    } catch {
      $lastError = $_.Exception.Message
    }

    Start-Sleep -Milliseconds 750
  } while ((Get-Date) -lt $deadline)

  throw "$Name did not become ready at $Url within $TimeoutSeconds seconds. Last error: $lastError"
}

function Assert-VenvPython {
  $python = Join-Path $repoRoot "venv\Scripts\python.exe"
  if (-not (Test-Path $python)) {
    throw "Project venv python not found at $python"
  }

  $runtimeCheck = & $python -c "import sys; print('python_executable=' + sys.executable); print('python_version=' + sys.version.replace(chr(10), ' ')); raise SystemExit(0 if sys.version_info[:3] == (3, 11, 9) else 119)"
  $runtimeCheck | ForEach-Object { Write-Log $_ }

  if ($LASTEXITCODE -ne 0) {
    throw "Project venv must use Python 3.11.9. Current runtime did not match the required patch version."
  }

  return $python
}

function Write-SourceFingerprint {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    Write-Log "source_missing | path=$Path"
    return
  }

  $item = Get-Item -LiteralPath $Path
  $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
  Write-Log "source_fingerprint | path=$Path | sha256=$($hash.Hash.Substring(0, 12)) | mtime=$($item.LastWriteTime.ToString('s'))"
}

function Get-ListeningProcess {
  param([int]$Port)

  $listener = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1

  if (-not $listener) {
    return $null
  }

  return Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
}

function Invoke-BrowserSmoke {
  param([string]$PanelUrl)

  if ($SkipBrowserSmoke) {
    Write-Log "Browser smoke skipped by flag"
    return
  }

  $node = (Get-Command node.exe -ErrorAction Stop).Source
  $webRoot = Join-Path $repoRoot "apps\web"
  $webRuntimeDir = Join-Path $webRoot "runtime"
  if (-not (Test-Path $webRuntimeDir)) {
    New-Item -ItemType Directory -Path $webRuntimeDir | Out-Null
  }

  $smokeScriptPath = Join-Path $webRuntimeDir ".start-all-browser-smoke.js"
  $playwrightScript = @'
const { chromium } = require("playwright");
const url = process.argv[2];

(async () => {
  let browser;
  const consoleErrors = [];
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    if (!response || !response.ok()) {
      throw new Error(`panel response failed status=${response ? response.status() : "none"}`);
    }
    await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
    const body = await page.locator("body").innerText({ timeout: 30000 });
    if (!/(StockNewsBR|Ford|\bF\b|Gr.fico|Not.cias|IA)/i.test(body)) {
      throw new Error(`panel loaded without expected content body_chars=${body.length}`);
    }
    console.log(`browser_panel_ok status=${response.status()} body_chars=${body.length} console_errors=${consoleErrors.length}`);
    if (consoleErrors.length > 0) {
      console.log(`browser_console_errors=${consoleErrors.slice(0, 3).join(" | ")}`);
    }
  } finally {
    if (browser) await browser.close();
  }
})().catch((error) => {
  console.error(`browser_panel_failed ${error.stack || error.message || error}`);
  process.exit(1);
});
'@

  Write-Log "Running browser smoke | url=$PanelUrl | node=$node"
  Set-Content -Path $smokeScriptPath -Value $playwrightScript -Encoding UTF8
  Remove-Item -Path $browserStdoutLog, $browserStderrLog -Force -ErrorAction SilentlyContinue
  try {
    $browserProcess = Start-Process `
      -FilePath $node `
      -ArgumentList @($smokeScriptPath, $PanelUrl) `
      -WorkingDirectory $webRoot `
      -WindowStyle Hidden `
      -Wait `
      -PassThru `
      -RedirectStandardOutput $browserStdoutLog `
      -RedirectStandardError $browserStderrLog

    if (Test-Path $browserStdoutLog) {
      Get-Content $browserStdoutLog | ForEach-Object { Write-Log "browser_stdout | $_" }
    }
    if (Test-Path $browserStderrLog) {
      Get-Content $browserStderrLog | ForEach-Object { Write-Log "browser_stderr | $_" }
    }

    if ($browserProcess.ExitCode -ne 0) {
      throw "Browser smoke failed for $PanelUrl"
    }
    Write-Log "Browser smoke passed | url=$PanelUrl"
  } finally {
    Remove-Item -Path $smokeScriptPath -Force -ErrorAction SilentlyContinue
  }
}

function Clear-WebDevCache {
  param([string]$WebRoot)

  if ($WebMode -ne "dev") {
    return
  }

  $nextDir = Join-Path $WebRoot ".next"
  if (-not (Test-Path -LiteralPath $nextDir)) {
    return
  }

  $resolvedWebRoot = (Resolve-Path -LiteralPath $WebRoot).Path
  $resolvedNextDir = (Resolve-Path -LiteralPath $nextDir).Path
  if (-not $resolvedNextDir.StartsWith($resolvedWebRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove Next cache outside web root: $resolvedNextDir"
  }

  Write-Log "Clearing stale Next dev cache | path=$resolvedNextDir"
  Remove-Item -LiteralPath $resolvedNextDir -Recurse -Force
}

if (-not (Test-Path $runtimeDir)) {
  New-Item -ItemType Directory -Path $runtimeDir | Out-Null
}

Set-Content -Path $startLog -Value ""
Remove-Item -Path $webStdoutLog, $webStderrLog, $browserStdoutLog, $browserStderrLog -Force -ErrorAction SilentlyContinue

$apiBaseUrl = "http://$ApiHost`:$ApiPort"
$webBaseUrl = "http://$WebHost`:$WebPort"
$panelUrl = "$webBaseUrl/panel/$PanelTicker"

Write-Log "Runtime start-all bootstrap | repo=$repoRoot"
$python = Assert-VenvPython
Write-Log "Runtime ports | api_host=$ApiHost | api_port=$ApiPort | web_host=$WebHost | web_port=$WebPort"
Write-Log "Runtime python | path=$python | required=3.11.9"
Write-SourceFingerprint (Join-Path $repoRoot "main.py")
Write-SourceFingerprint (Join-Path $repoRoot "apps\web\app\panel\[slug]\page.tsx")
Write-SourceFingerprint (Join-Path $repoRoot "apps\web\components\workspace-shell.tsx")

Stop-PortListeners -Port $ApiPort -Name "API"
Stop-PortListeners -Port $WebPort -Name "web"

$apiScript = Join-Path $PSScriptRoot "start_api_venv.ps1"
Write-Log "Starting API through venv script | script=$apiScript"
& $apiScript -HostName $ApiHost -Port $ApiPort

$apiProcess = Get-ListeningProcess -Port $ApiPort
if (-not $apiProcess) {
  throw "API process is not listening on port $ApiPort after startup."
}
Write-Log "API port confirmed | port=$ApiPort | pid=$($apiProcess.ProcessId) | executable=$($apiProcess.ExecutablePath)"
Write-Log "API command | $($apiProcess.CommandLine)"
Wait-HttpOk -Url "$apiBaseUrl/" -Name "API" -TimeoutSeconds 60 | Out-Null

$webRoot = Join-Path $repoRoot "apps\web"
if (-not (Test-Path $webRoot)) {
  throw "Web app root not found at $webRoot"
}

Clear-WebDevCache -WebRoot $webRoot

$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$previousApiBase = $env:NEXT_PUBLIC_API_BASE
$env:NEXT_PUBLIC_API_BASE = $apiBaseUrl
try {
  $webArguments = @("run", $WebMode, "--", "--hostname", $WebHost, "--port", [string]$WebPort)
  Write-Log "Starting web | mode=$WebMode | cwd=$webRoot | npm=$npm | api_base=$apiBaseUrl"
  $webProcess = Start-Process `
    -FilePath $npm `
    -ArgumentList $webArguments `
    -WorkingDirectory $webRoot `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $webStdoutLog `
    -RedirectStandardError $webStderrLog
} finally {
  $env:NEXT_PUBLIC_API_BASE = $previousApiBase
}

Write-Log "Started web process | pid=$($webProcess.Id) | stdout=$webStdoutLog | stderr=$webStderrLog"
Wait-HttpOk -Url $panelUrl -Name "Web panel" -TimeoutSeconds 120 | Out-Null

$webRuntimeProcess = Get-ListeningProcess -Port $WebPort
if (-not $webRuntimeProcess) {
  throw "Web process is not listening on port $WebPort after startup."
}
Write-Log "Web port confirmed | port=$WebPort | pid=$($webRuntimeProcess.ProcessId) | executable=$($webRuntimeProcess.ExecutablePath)"
Write-Log "Web command | $($webRuntimeProcess.CommandLine)"

if (-not $SkipSmoke) {
  $smokeScript = Join-Path $PSScriptRoot "smoke_public_market.ps1"
  Write-Log "Running API smoke | script=$smokeScript | base_url=$apiBaseUrl"
  & $smokeScript -BaseUrl $apiBaseUrl
  Write-Log "API smoke passed | script=$smokeScript"
  Invoke-BrowserSmoke -PanelUrl $panelUrl
} else {
  Write-Log "Smoke skipped by flag"
}

Write-Log "Runtime start-all done | api=$apiBaseUrl | web=$webBaseUrl | panel=$panelUrl"
