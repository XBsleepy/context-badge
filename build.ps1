$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venv = Join-Path $PSScriptRoot ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $venv
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip in the packaging venv."
}

& $python -m pip install "pyinstaller>=6.3"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install PyInstaller."
}

& $python -m PyInstaller --noconfirm --clean .\context-badge.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

$built = Join-Path $PSScriptRoot "dist\ContextBadge.exe"
if (-not (Test-Path -LiteralPath $built)) {
    throw "Expected $built was not produced."
}

Write-Host "Built $built"
