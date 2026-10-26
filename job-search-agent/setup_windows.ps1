$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "Job Scout local setup" -ForegroundColor Cyan
Write-Host "Private resume/profile/email settings stay under your Windows user folder." -ForegroundColor Yellow

$PythonCommand = Get-Command py -ErrorAction SilentlyContinue
if (-not $PythonCommand) { $PythonCommand = Get-Command python -ErrorAction SilentlyContinue }
if (-not $PythonCommand) {
    throw "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ and rerun this script."
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $ProjectRoot ".venv")
    } else {
        & python -m venv (Join-Path $ProjectRoot ".venv")
    }
}
if (-not (Test-Path $VenvPython)) { throw "Could not create Python virtual environment." }

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements-auto-apply.txt")
& $VenvPython -m playwright install chromium

$TaskName = "JobScoutAutoApply"
$RunnerPath = Join-Path $ProjectRoot "apply_agent.py"
$Arguments = '"' + $RunnerPath + '" --submit --max-applications 5'
$Action = New-ScheduledTaskAction -Execute $VenvPython -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At 9:20AM
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Run the locally configured Job Scout auto-apply agent at 9:20 AM daily." -Force | Out-Null

Write-Host ""
Write-Host "Setup complete. Start the local setup UI with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe -m streamlit run local_app.py"
Write-Host ""
Write-Host "IMPORTANT: first save your profile and resume in the local UI, test email, and run a dry-run before enabling auto-submit."
Write-Host "The scheduled task is registered but the agent will safely stop until a profile and resume are configured."
Write-Host "For automatic daily runs, your PC must be on and your Windows user session logged in."
