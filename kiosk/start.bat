@echo off
chcp 65001 > nul
echo === Khoi dong Kiosk Cham Cong ===

cd /d "%~dp0"

echo [+] Dang chay Kiosk...
if "%API_BASE_URL%"=="" (
    echo     API: http://localhost:8000/api/v1
) else (
    echo     API: %API_BASE_URL%
)
echo     Nhan Q hoac ESC de thoat
echo     Nhan R de dang ky khuon mat (nhap ma NV, Enter xac nhan)
echo.
venv\Scripts\python.exe main.py
pause
