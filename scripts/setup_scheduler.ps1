# Law + area-designation change detection - Windows Task Scheduler registration
# Run as Administrator: .\scripts\setup_scheduler.ps1
#
# Schedule: 09:00 / 18:00 (하루 2회)
# 09:00 — 전날/새벽 발표 반영
# 18:00 — 장중(오전 10~11시) 보도자료 반영

$TaskName    = "TaxRAG-LawChangeDetect"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir      = Join-Path $ProjectRoot "data\logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ── Python 경로 탐색 (conda는 Admin 세션에서 PATH에 없을 수 있음) ─────────────
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue)
if ($PythonExe) {
    $PythonExe = $PythonExe.Source
} else {
    $candidates = @(
        "$env:USERPROFILE\anaconda3\python.exe",
        "$env:USERPROFILE\miniconda3\python.exe",
        "C:\ProgramData\anaconda3\python.exe",
        "C:\ProgramData\miniconda3\python.exe",
        "C:\anaconda3\python.exe",
        "C:\miniconda3\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $PythonExe = $c; break }
    }
}

if (-not $PythonExe) {
    Write-Error "Python을 찾을 수 없습니다. conda 경로를 확인하세요."
    exit 1
}

Write-Host "Python: $PythonExe"

# ── 태스크 액션 ───────────────────────────────────────────────────────────────
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m scripts.detect_law_changes --embed" `
    -WorkingDirectory $ProjectRoot

# ── 트리거 (09:00 / 18:00) ────────────────────────────────────────────────────
$Trigger0900 = New-ScheduledTaskTrigger -Daily -At "09:00"
$Trigger1800 = New-ScheduledTaskTrigger -Daily -At "18:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

# ── 기존 태스크 제거 후 재등록 ────────────────────────────────────────────────
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

# ── [2] 유권해석·예규·결정례 증분 수집 (매일 02:00) ──────────────────────────
# collect_and_embed_rulings.py:
#   - 수집: --resume으로 기존 파일 스킵 (무료 HTTP)
#   - 임베딩: 신규 파일이 있을 때만 실행 (Upstage API 비용 절감)
$RulingsTaskName = "TaxRAG-RulingsCollect"

$RulingsAction = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "scripts\collect_and_embed_rulings.py" `
    -WorkingDirectory $ProjectRoot

$RulesTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"

$RulingsSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$existingRulings = Get-ScheduledTask -TaskName $RulingsTaskName -ErrorAction SilentlyContinue
if ($existingRulings) {
    Unregister-ScheduledTask -TaskName $RulingsTaskName -Confirm:$false
    Write-Host "기존 유권해석 태스크 제거 완료"
}

Register-ScheduledTask `
    -TaskName $RulingsTaskName `
    -Action $RulingsAction `
    -Trigger $RulesTrigger `
    -Settings $RulingsSettings `
    -Description "Tax-RAG: 유권해석·예규·결정례 증분 수집 + 신규 있을 때만 임베딩 (매일 02:00)" `
    -RunLevel Highest

Write-Host ""
Write-Host "=== 등록 완료 ==="
Write-Host ""
Write-Host "[$TaskName]"
Write-Host "  Python   : $PythonExe"
Write-Host "  Schedule : 09:00 / 18:00 (하루 2회) — 법령 개정 감지"
Write-Host ""
Write-Host "[$RulingsTaskName]"
Write-Host "  Python   : $PythonExe"
Write-Host "  Schedule : 02:00 (매일) — 유권해석·예규 증분 수집 (신규 있을 때만 임베딩)"
Write-Host ""
Write-Host "수동 실행:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Start-ScheduledTask -TaskName '$RulingsTaskName'"
