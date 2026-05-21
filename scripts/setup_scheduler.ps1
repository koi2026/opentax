# Law + area-designation change detection - Windows Task Scheduler registration
# Run as Administrator: .\scripts\setup_scheduler.ps1
#
# Schedule: 09:00 / 18:00 (하루 2회)
# 09:00 — 전날/새벽 발표 반영
# 18:00 — 장중(오전 10~11시) 보도자료 반영

$TaskName    = "TaxRAG-LawChangeDetect"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe   = (Get-Command python).Source
$LogDir      = Join-Path $ProjectRoot "data\logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# 법령 개정 감지 + 규제지역 감지 통합 실행
# --embed: 신규 법령 버전 발견 시 Pinecone 자동 업로드
$ArgString = "-m scripts.detect_law_changes --embed"

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ArgString `
    -WorkingDirectory $ProjectRoot

# 하루 2회 트리거 (09:00 / 18:00)
$Trigger0900 = New-ScheduledTaskTrigger -Daily -At "09:00"
$Trigger1800 = New-ScheduledTaskTrigger -Daily -At "18:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "기존 태스크 제거 완료"
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($Trigger0900, $Trigger1800) `
    -Settings $Settings `
    -Description "Tax-RAG: 법령 개정 + 규제지역 변경 감지 + Pinecone reindex (하루 2회)" `
    -RunLevel Highest

Write-Host ""
Write-Host "=== 등록 완료 ==="
Write-Host "Task     : $TaskName"
Write-Host "Schedule : 09:00 / 18:00 (하루 2회)"
Write-Host "Log      : $LogDir\law_change_detect.log"
Write-Host ""
Write-Host "수동 실행:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "주의: 기존 스케줄러가 등록된 경우 재등록 필요 (관리자 PowerShell):"
Write-Host "  .\scripts\setup_scheduler.ps1"
