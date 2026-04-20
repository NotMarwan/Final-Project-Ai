$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $root ".runlogs\\colab_bridge"
$serverOut = Join-Path $logs "bridge-server.out.log"
$serverErr = Join-Path $logs "bridge-server.err.log"
$tunnelOut = Join-Path $logs "cloudflared.out.log"
$tunnelErr = Join-Path $logs "cloudflared.err.log"

New-Item -ItemType Directory -Force -Path $logs | Out-Null

Push-Location $root
python backend\prepare_colab_bundle.py | Out-Null

$existingServer = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
if ($existingServer) {
  Stop-Process -Id $existingServer -Force
  Start-Sleep -Seconds 1
}

Start-Process -FilePath cmd.exe -ArgumentList '/c', 'python backend\colab_bridge_server.py 1>".runlogs\colab_bridge\bridge-server.out.log" 2>".runlogs\colab_bridge\bridge-server.err.log"' -WorkingDirectory $root | Out-Null
Start-Sleep -Seconds 2

$cloudflared = Join-Path $root 'backend\cloudflared-windows-amd64.exe'
if (-not (Test-Path $cloudflared)) {
  throw "cloudflared binary not found at $cloudflared"
}

if (Test-Path $tunnelOut) {
  Remove-Item $tunnelOut -Force
}
if (Test-Path $tunnelErr) {
  Remove-Item $tunnelErr -Force
}

Start-Process -FilePath $cloudflared -ArgumentList 'tunnel', '--url', 'http://127.0.0.1:8765', '--protocol', 'http2', '--no-autoupdate', '--logfile', $tunnelErr -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr -WorkingDirectory $root | Out-Null
Start-Sleep -Seconds 8

$url = $null
foreach ($candidate in @($tunnelOut, $tunnelErr)) {
  if (-not (Test-Path $candidate)) {
    continue
  }

  $match = Select-String -Path $candidate -Pattern 'https://[-a-z0-9]+\.trycloudflare\.com' | Select-Object -Last 1
  if ($match) {
    $url = $match.Matches[0].Value
    break
  }
}

Write-Host "Bridge ready."
Write-Host "Manifest: http://127.0.0.1:8765/manifest"
if ($url) {
  $readyNotebook = python backend\render_colab_notebook.py --bridge-url $url
  $launchInfo = Join-Path $logs "colab-launch.txt"
  @(
    "Public URL: $url"
    "Manifest: $url/manifest"
    "Ready notebook: $readyNotebook"
    "Template notebook: $(Join-Path $root 'notebooks\colab_zero_touch_train.ipynb')"
  ) | Set-Content -Path $launchInfo -Encoding UTF8

  Write-Host "Public URL: $url"
  Write-Host "Ready notebook: $readyNotebook"
} else {
  Write-Host "Public URL not found yet. Check $tunnelErr"
}

Pop-Location
