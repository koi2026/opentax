# Law change detection - Windows Task Scheduler registration
# Run as Administrator: .\scripts\setup_scheduler.ps1

$TaskName    = "TaxRAG-LawChangeDetect"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe   = (Get-Command python).Source
$LogDir      = Join-Path $ProjectRoot "data\logs"
$LogFile     = Join-Path $LogDir "law_change_detect.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$ArgString = "-m scripts.detect_law_changes --embed"

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ArgString `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At "23:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10)

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task"
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Tax-RAG law change detection + Pinecone reindex" `
    -RunLevel Highest

Write-Host ""
Write-Host "=== Registered ==="
Write-Host "Task     : $TaskName"
Write-Host "Schedule : Daily 23:00"
Write-Host "Log      : $LogFile"
Write-Host ""
Write-Host "Manual test:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
