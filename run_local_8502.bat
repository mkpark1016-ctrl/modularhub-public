@echo off
setlocal

cd /d "%~dp0"

echo Project root: %CD%
echo.
echo Dashboard URL:
echo   http://127.0.0.1:8502
echo.
echo Keep this CMD or PowerShell window open while using the dashboard.
echo Closing this window will stop the Streamlit server.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment Python was not found.
    echo.
    echo Run these commands first:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo   .venv\Scripts\python.exe db\init_db.py
    echo   .venv\Scripts\python.exe scripts\load_sample_data.py
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" --version
echo.
".venv\Scripts\python.exe" -m streamlit --version
echo.

".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502

echo.
echo Streamlit stopped.
pause
