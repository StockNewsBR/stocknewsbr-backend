param(
  [string]$ManifestPath = "data/help_videos.json",
  [string]$OutputDir = "media/help-videos",
  [string]$FontPath = "C:/Windows/Fonts/segoeui.ttf"
)

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
  Write-Error "ffmpeg nao encontrado. Instale ffmpeg e rode novamente."
  exit 1
}

if (-not (Test-Path $ManifestPath)) {
  Write-Error "Manifesto de videos nao encontrado em $ManifestPath"
  exit 1
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$items = Get-Content $ManifestPath -Raw | ConvertFrom-Json

foreach ($item in $items) {
  $slug = $item.slug
  $title = [string]$item.title
  if ($item.PSObject.Properties.Name -contains "subtitle" -and $item.subtitle) {
    $subtitle = [string]$item.subtitle
  }
  else {
    $subtitle = "Demonstracao StockNewsBR"
  }
  $output = Join-Path $OutputDir "$slug.mp4"

  & $ffmpeg.Source `
    -y `
    -f lavfi -i "color=c=0x07111b:s=1280x720:d=12" `
    -vf "drawtext=fontfile='$FontPath':text='$title':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=(h-text_h)/2-40,drawtext=fontfile='$FontPath':text='$subtitle':fontcolor=0x95a9bd:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2+36" `
    -c:v libx264 `
    -pix_fmt yuv420p `
    $output
}
