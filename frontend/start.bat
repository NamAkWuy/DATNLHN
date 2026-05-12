@echo off
chcp 65001 > nul
echo === Khoi dong Frontend ===

cd /d "%~dp0"

if not exist "node_modules" (
    echo [!] Chua co node_modules, dang chay npm install...
    npm install
)

echo [+] Dang chay frontend tai http://localhost:5173
echo     Nhan Ctrl+C de dung
echo.
npm run dev
pause
