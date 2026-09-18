@echo off
title RTO E-Challan System
cd /d "%~dp0"

echo Starting AI Driven Camera Detected RTO E-Challan System...
echo.

if not exist "backend\.venv\Scripts\python.exe" (
  echo Backend virtual environment not found.
  echo Run these commands first:
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Installing frontend packages...
  cd frontend
  call npm install
  cd ..
)

start "RTO Backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
timeout /t 3 /nobreak >nul
start "RTO Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Backend : http://127.0.0.1:8000
echo Frontend: http://localhost:5173
echo Login   : ADMIN001  /  Admin@123
echo.
start http://localhost:5173
echo Two terminal windows were opened. Keep them running while you use the app.
pause
