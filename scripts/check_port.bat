@echo off
setlocal

echo Checking port 8501...
netstat -ano | findstr :8501
if errorlevel 1 (
    echo No process is currently using port 8501.
) else (
    echo Port 8501 is in use. The last column is the PID.
    echo To inspect a PID, run: tasklist /FI "PID eq ^<PID^>"
)

echo.
echo Checking port 8502...
netstat -ano | findstr :8502
if errorlevel 1 (
    echo No process is currently using port 8502.
) else (
    echo Port 8502 is in use. The last column is the PID.
    echo To inspect a PID, run: tasklist /FI "PID eq ^<PID^>"
)

echo.
pause
