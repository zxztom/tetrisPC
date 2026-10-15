param([int]$Cycles=0,[ValidateSet("dpc","pure4")][string]$CycleMode="pure4")
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'launch.ps1') -NoBrowser
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Could not start PC Lab.' }
$taskConfig = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/config' -TimeoutSec 5
if ($taskConfig.name -ne 'PC Lab' -or $taskConfig.project_root -ne $taskRoot) { throw 'Port 8787 belongs to another app.' }
if ($taskConfig.active_live_job) { Write-Output 'Random PC is already running.'; exit 0 }
$taskRequest = @{live_mode='visible';cycle_mode=$CycleMode;rotation_rules='SRS+';wait_start=$true;launch_game=$true;auto_retry=$taskConfig.settings.recover_on_failure;recover_on_failure=$taskConfig.settings.recover_on_failure;max_retries=$taskConfig.settings.max_retries;restart=$false;max_cycles=$Cycles;operation_interval_ms=$taskConfig.settings.operation_interval_ms;speed_preset=$taskConfig.settings.speed_preset} | ConvertTo-Json
$taskJob = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/live' -Method Post -Headers @{'X-PC-Token'=$taskConfig.token} -ContentType 'application/json' -Body $taskRequest
$taskJob | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot 'output\active-live-job.json') -Encoding UTF8
Write-Output 'Random PC is waiting for a fresh SOLO CUSTOM game. F8 or Esc stops it.'
