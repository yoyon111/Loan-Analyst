param([switch]$Postgres)
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
$apiProcess = Start-Process -FilePath (Join-Path $projectRoot '.venv/Scripts/python.exe') -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
try { & npm.cmd run dev } finally { if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id } }
