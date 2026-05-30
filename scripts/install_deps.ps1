# Install ALL Road SOS / TADS dependencies into .venv
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Test-Path Env:SSLKEYLOGFILE) {
    Write-Host "Removing SSLKEYLOGFILE (blocks pip on some Windows setups): $env:SSLKEYLOGFILE"
    Remove-Item Env:SSLKEYLOGFILE
}

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "Installing requirements.txt (this may take several minutes for torch/transformers)..."
& $python -m pip install -r requirements.txt

Write-Host "Verifying imports..."
& $python scripts/verify_deps.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path "yolov8n.pt")) {
    Write-Host "Downloading YOLO weights..."
    Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
    & $python scripts/download_weights.py
}

Write-Host ""
Write-Host "Setup complete. Run dashboard:"
Write-Host "  .venv\Scripts\streamlit.exe run dashboard/app.py"
