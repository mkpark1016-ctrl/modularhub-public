$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Port = 8501

Write-Host "Checking port $Port..."
$Result = netstat -ano | findstr ":$Port"

if (-not $Result) {
    Write-Host "현재 8501 포트에서 실행 중인 Streamlit 서버가 없습니다."
    Write-Host "앱을 실행하려면 프로젝트 루트에서 아래 명령을 실행하세요:"
    Write-Host "  .\run_local.ps1"
    exit 0
}

Write-Host $Result
Write-Host ""
Write-Host "포트가 사용 중입니다. 마지막 열이 PID입니다."
Write-Host "PID의 프로세스 이름을 확인하려면 아래 명령을 실행하세요:"
Write-Host "  tasklist /FI `"PID eq <PID>`""
