param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
$taskCandidates = @(
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'),
    (Join-Path $taskRoot 'tools\python\python.exe')
)
$taskPython = $taskCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $taskPython) {
    $taskCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($taskCommand -and $taskCommand.Source -notmatch 'WindowsApps') { $taskPython = $taskCommand.Source }
}
if (-not $taskPython) { throw 'Python 3.10 or newer is required. Install Python or use the Codex bundled runtime.' }
$taskExisting = $null
try {
    $taskConfig = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/config' -TimeoutSec 2
    $taskExisting = $taskConfig
} catch {}
if ($taskExisting) {
    if ($taskExisting.name -ne 'PC Lab' -or $taskExisting.project_root -ne $taskRoot) { throw 'Port 8787 is occupied by another app.' }
    if ($taskExisting.version -eq '0.12.13') {
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8787' }
        exit 0
    }
    if ($taskExisting.active_live_job) { throw 'An older PC Lab has an active game task. Stop that task before updating the service.' }
    Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/shutdown' -Method Post -Headers @{'X-PC-Token'=$taskExisting.token} -ContentType 'application/json' -Body '{}' | Out-Null
    for ($taskStopAttempt=0; $taskStopAttempt -lt 30; $taskStopAttempt++) {
        Start-Sleep -Milliseconds 100
        try { Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/config' -TimeoutSec 1 | Out-Null }
        catch { break }
    }
}
New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot 'output') | Out-Null
$taskLaunchArguments = '-m pc_lab serve'
if (-not $NoBrowser) { $taskLaunchArguments += ' --open' }
Start-Process -FilePath $taskPython -ArgumentList $taskLaunchArguments -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'output\server.log') -RedirectStandardError (Join-Path $taskRoot 'output\server-error.log')
for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
    Start-Sleep -Milliseconds 200
    try {
        $taskReady = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/config' -TimeoutSec 1
        if ($taskReady.name -eq 'PC Lab') { exit 0 }
    } catch {}
}
throw ('PC Lab startup failed. See ' + (Join-Path $taskRoot 'output\server-error.log'))
