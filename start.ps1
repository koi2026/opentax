# Tax-RAG 로컬 실행 스크립트
# 실행: .\start.ps1
# 종료: Ctrl+C 후 작업 관리자에서 Python 프로세스 종료

$ProjectRoot = $PSScriptRoot
$PythonExe   = "C:\Users\user\anaconda3\python.exe"

Write-Host "=== Tax-RAG 시작 ===" -ForegroundColor Cyan
Write-Host ""

# FastAPI 백엔드 (포트 8000)
Write-Host "[1] FastAPI API 서버 시작 (포트 8000)..." -ForegroundColor Yellow
$api = Start-Process -NoNewWindow -FilePath $PythonExe `
    -ArgumentList "-m uvicorn src.api.chat_api:app --host 0.0.0.0 --port 8000 --reload" `
    -WorkingDirectory $ProjectRoot `
    -PassThru `
    -RedirectStandardOutput "$ProjectRoot\logs\api.log" `
    -RedirectStandardError  "$ProjectRoot\logs\api_err.log"

Start-Sleep -Seconds 3

# Streamlit 프론트엔드 (포트 8501)
Write-Host "[2] Streamlit UI 시작 (포트 8501)..." -ForegroundColor Yellow
$ui = Start-Process -NoNewWindow -FilePath $PythonExe `
    -ArgumentList "-m streamlit run src/ui.py --server.address 0.0.0.0 --server.port 8501 --server.headless true" `
    -WorkingDirectory $ProjectRoot `
    -PassThru `
    -RedirectStandardOutput "$ProjectRoot\logs\ui.log" `
    -RedirectStandardError  "$ProjectRoot\logs\ui_err.log"

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "=== 실행 완료 ===" -ForegroundColor Green
Write-Host "  API  : http://localhost:8000"
Write-Host "  UI   : http://localhost:8501"
Write-Host ""
Write-Host "로그:"
Write-Host "  API  : logs\api.log"
Write-Host "  UI   : logs\ui.log"
Write-Host ""
Write-Host "종료하려면 아래 명령어 실행:"
Write-Host "  Stop-Process -Id $($api.Id), $($ui.Id)"
