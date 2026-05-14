# Build switch2pc.exe with PyInstaller.
#
# Usage:
#   .\scripts\build.ps1
#
# Assumes you have a venv activated and `pip install -e .[dev]` has been run.

$ErrorActionPreference = "Stop"

$root = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $root

Write-Host "==> Cleaning previous build..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist

Write-Host "==> Running PyInstaller..." -ForegroundColor Cyan
pyinstaller --clean --noconfirm switch2pc.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$exe = Join-Path $root "dist\switch2pc.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Expected $exe but it wasn't produced."
    exit 1
}

$size = (Get-Item $exe).Length / 1MB
Write-Host ("==> Built $exe ({0:N1} MB)" -f $size) -ForegroundColor Green
