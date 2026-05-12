@echo off
chcp 65001 > nul
echo === Khoi dong Kiosk Cham Cong ===

cd /d "%~dp0"

echo [+] Dang chay Kiosk...
echo     Nhan Q hoac ESC de thoat
echo     Nhan SPACE de nhan dien ngay
echo     Nhan R de dang ky khuon mat (nhap ma NV, Enter xac nhan)
echo.
venv\Scripts\python.exe main.py
pause
