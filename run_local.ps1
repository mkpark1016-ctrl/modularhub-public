$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "Project root: $ProjectRoot"

$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ActivateScript)) {
    Write-Host ""
    Write-Host "Virtual environment was not found."
    Write-Host "Run this first:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\activate"
    Write-Host "  pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host ""
    Write-Host "Python executable was not found in .venv."
    Write-Host "Run this first:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\activate"
    Write-Host "  pip install -r requirements.txt"
    exit 1
}

$env:VIRTUAL_ENV = Join-Path $ProjectRoot ".venv"
$env:PATH = "$(Join-Path $ProjectRoot '.venv\Scripts');$env:PATH"

Write-Host "Python version:"
& $PythonExe --version

Write-Host ""
Write-Host "Checking Streamlit installation:"
& $PythonExe -m streamlit --version

Write-Host ""
Write-Host "Starting Streamlit dashboard..."
Write-Host "Keep this PowerShell window open while using the dashboard."
Write-Host "Open this URL in your browser:"
Write-Host "  http://127.0.0.1:8501"
Write-Host ""

& $PythonExe -m streamlit run app.py --server.port 8501
