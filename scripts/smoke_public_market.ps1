param(
  [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

function Invoke-Json($Path) {
  $url = "$BaseUrl$Path"
  Write-Host "GET $url"
  return Invoke-RestMethod -Uri $url -TimeoutSec 20
}

function Assert-QuotePrice($Payload, [string[]]$Symbols) {
  foreach ($symbol in $Symbols) {
    $item = @($Payload.items) | Where-Object { $_.symbol -eq $symbol } | Select-Object -First 1
    if (-not $item) {
      throw "Missing quote item for $symbol"
    }
    $source = [string]$item.source
    $status = [string]$item.quote_status
    if ([string]::IsNullOrWhiteSpace($status)) {
      throw "Quote for $symbol is missing quote_status; API may not be running current code"
    }
    if ($source -eq "empty" -or $status -eq "empty" -or $status -eq "partial") {
      throw "Quote for $symbol was treated as success with source=$source quote_status=$status"
    }
    $price = [double]::NaN
    if (-not [double]::TryParse([string]$item.price, [ref]$price) -or $price -le 0) {
      throw "Quote for $symbol has no valid price. source=$($item.source)"
    }
    Write-Host "PASS quote $symbol price=$price source=$source quote_status=$status"
  }
}

function Assert-QuoteEmptyIsNotSuccess($Symbol) {
  $payload = Invoke-Json "/public/market/quote/$Symbol"
  if ($payload.source -ne "empty") {
    Write-Host "SKIP empty quote guard for $Symbol source=$($payload.source) quote_status=$($payload.quote_status)"
    return
  }
  if ($payload.quote_status -ne "empty") {
    throw "Empty quote for $Symbol is missing explicit quote_status=empty; actual=$($payload.quote_status)"
  }
  $price = [double]::NaN
  if ([double]::TryParse([string]$payload.price, [ref]$price) -and $price -gt 0) {
    throw "Empty quote guard failed for ${Symbol}: source=empty but price=$price"
  }
  Write-Host "PASS empty quote is explicit for $Symbol source=$($payload.source) quote_status=$($payload.quote_status)"
}

function Assert-ChartPayload($Payload, [string]$Symbol, [string]$Range, [bool]$RequireBars) {
  if ($null -eq $Payload -or ($Payload.PSObject.Properties.Count -eq 0)) {
    throw "Chart for $Symbol range=$Range returned silent empty object"
  }
  $bars = @($Payload.ohlc)
  if ($bars -and $bars.Count -ge 2) {
    Write-Host "PASS chart $Symbol range=$Range bars=$($bars.Count) fallback=$($Payload.fallback)"
    return
  }
  if ($RequireBars) {
    throw "Chart for $Symbol range=$Range returned empty or too few bars"
  }
  if ($Payload.status -ne "empty" -or -not $Payload.fallback -or -not $Payload.provider_status) {
    throw "Chart fallback for $Symbol range=$Range is not explicit. status=$($Payload.status) fallback=$($Payload.fallback) provider_status=$($Payload.provider_status)"
  }
  Write-Host "PASS chart explicit fallback $Symbol range=$Range status=$($Payload.status) provider_status=$($Payload.provider_status)"
}

function Assert-Chart($Symbol, $Range, [bool]$RequireBars = $true) {
  $payload = Invoke-Json "/public/market/chart/$Symbol`?range=$Range"
  Assert-ChartPayload $payload $Symbol $Range $RequireBars
}

function Assert-NewsShape($Symbol, [bool]$RequireItems = $false) {
  $payload = Invoke-Json "/public/market/news/$Symbol`?limit=6"
  if ($payload.symbol -ne $Symbol) {
    throw "News payload symbol mismatch. expected=$Symbol actual=$($payload.symbol)"
  }
  if ($null -eq $payload.items) {
    throw "News payload for $Symbol has no items array"
  }
  if ($null -eq $payload.report -or $null -eq $payload.cache) {
    throw "News payload for $Symbol has no report/cache metadata"
  }
  if ($RequireItems -and [int]$payload.count -lt 1) {
    throw "News payload for $Symbol should have ticker-specific news. provider_status=$($payload.cache.provider_status) provider_error=$($payload.cache.provider_error)"
  }
  if ([int]$payload.count -lt 1) {
    if ($payload.report.status -ne "empty" -and $payload.cache.status -notin @("empty", "cold", "stale_fallback")) {
      throw "News empty state for $Symbol is not explicit. cache=$($payload.cache.status) report=$($payload.report.status)"
    }
  }
  foreach ($item in @($payload.items)) {
    $itemTicker = [string]$item.ticker
    if ($itemTicker -and $itemTicker -ne $Symbol) {
      throw "News item for $Symbol reused ticker $itemTicker without explicit selected ticker"
    }
  }
  Write-Host "PASS news $Symbol count=$($payload.count) cache=$($payload.cache.status) report=$($payload.report.status)"
}

$requiredSymbols = @("F", "AAPL", "PETR4", "BBDC4", "BTCUSD", "META34")
$quotePayload = Invoke-Json "/public/market/quotes?symbols=$($requiredSymbols -join ',')"
Assert-QuotePrice $quotePayload $requiredSymbols
Assert-QuoteEmptyIsNotSuccess "ZZZZ999"

Assert-Chart "F" "1D"
Assert-Chart "F" "1W"
Assert-Chart "F" "1M"
Assert-Chart "F" "3M"
Assert-Chart "F" "1Y"
Assert-Chart "AAPL" "1D" $false
Assert-Chart "PETR4" "1D" $false
Assert-Chart "BTCUSD" "1D" $false
Assert-Chart "META34" "1D" $false
Assert-NewsShape "F" $true
Assert-NewsShape "PETR4" $false

Write-Host "Smoke public market checks passed."
