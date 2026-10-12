param([switch]$Postgres, [switch]$Lan)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { python -m venv .venv }
& ./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
if (-not (Test-Path -LiteralPath 'node_modules')) {
  & npm.cmd ci
  if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed.' }
}
if ($Postgres) {
  & docker compose up -d --wait db
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not start.' }
  $env:DATABASE_URL = 'postgresql+psycopg://investoffice:investoffice@127.0.0.1:5432/investoffice'
} elseif (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'sqlite:///./investoffice.db' }
$env:DEMO_MODE = 'true'
if ($Lan) {
  $lanAddress = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | ForEach-Object { $_.IPv4Address.IPAddress } | Where-Object { $_ -and $_ -ne '127.0.0.1' -and $_ -notlike '169.254.*' } | Select-Object -First 1
  if (-not $lanAddress) { throw 'Could not find an active Wi-Fi IPv4 address. Connect to Wi-Fi and retry.' }
  $parsedAddress = [System.Net.IPAddress]::Parse($lanAddress)
  $bytes = $parsedAddress.GetAddressBytes()
  $private = ($bytes[0] -eq 10) -or ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
  if ($parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or -not $private) { throw 'The selected network address is not a private IPv4 address. LAN mode only supports private IPv4 networks.' }
  $env:LAN_IP = $lanAddress
  Write-Host "InvestOffice is available to devices on this Wi-Fi at http://${lanAddress}:3000"
  Write-Host 'Keep this terminal open. Only share it with people on a trusted private network.'
} else {
  Remove-Item Env:\LAN_IP -ErrorAction SilentlyContinue
}
$apiProcess = Start-Process -FilePath (Join-Path $projectRoot '.venv/Scripts/python.exe') -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
try {
  if ($Lan) { & .\node_modules\.bin\next.cmd dev --hostname $lanAddress }
  else { & npm.cmd run dev }
} finally { if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id } }
