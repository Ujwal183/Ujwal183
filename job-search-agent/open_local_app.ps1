$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "Run .\setup_windows.ps1 first to install Job Scout." -ForegroundColor Yellow
  exit 1
}
Set-Location $ProjectRoot
& $VenvPython -m streamlit run (Join-Path $ProjectRoot "local_app.py")
