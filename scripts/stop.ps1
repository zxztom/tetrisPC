$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
try { $taskConfig = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/config' -TimeoutSec 2 }
catch { Write-Output 'PC Lab is not running.'; exit 0 }
if ($taskConfig.name -ne 'PC Lab' -or $taskConfig.project_root -ne $taskRoot) {
    throw 'The app on port 8787 does not belong to this project. Nothing was stopped.'
}
Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/shutdown' -Method Post -Headers @{'X-PC-Token'=$taskConfig.token} -ContentType 'application/json' -Body '{}' | Out-Null
for ($taskAttempt = 0; $taskAttempt -lt 20; $taskAttempt++) {
    Start-Sleep -Milliseconds 100
    try { Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/config' -TimeoutSec 1 | Out-Null }
    catch { Write-Output 'PC Lab stopped.'; exit 0 }
}
throw 'Shutdown did not complete. Check output/server-error.log.'
