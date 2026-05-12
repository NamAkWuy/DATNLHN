@echo off
chcp 65001 > nul
echo === Khoi dong Backend ===
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set TF_ENABLE_ONEDNN_OPTS=0

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Chua co venv, dang tao...
    "C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe" -m venv venv
    echo [+] Dang cai packages...
    venv\Scripts\pip.exe install -r requirements.txt
)

echo [+] Dang chay backend tai http://localhost:8000
echo     Swagger UI: http://localhost:8000/docs
echo     Nhan Ctrl+C de dung
echo.
venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
pause
