@echo off
chcp 65001 > nul
echo === Khoi dong toan bo he thong ===
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.

start "Backend - FastAPI" cmd /k "cd /d "%~dp0backend" && start.bat"
timeout /t 3 > nul
start "Frontend - React" cmd /k "cd /d "%~dp0frontend" && start.bat"

echo [+] Da mo 2 cua so terminal
echo     Backend: http://localhost:8000/docs
echo     Frontend: http://localhost:5173
