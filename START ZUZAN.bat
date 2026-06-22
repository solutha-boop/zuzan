@echo off
title ZuZan - SA Bookkeeping Platform
color 0B

echo.
echo  ================================================
echo    ZuZan - SA Bookkeeping Platform
echo    Starting all services...
echo  ================================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  ERROR: Python not found. Install from https://python.org
    pause
    exit /b
)
echo  [1/4] Python found.

:: ── Start Python Backend ──────────────────────────────────────────────────────
echo  [2/4] Starting ZuZan backend...
cd /d "%~dp0zuzan-backend"

if not exist ".deps_installed" (
    echo  Installing backend dependencies (first run only)...
    pip install fastapi uvicorn sqlalchemy alembic pydantic pydantic-settings python-dotenv passlib bcrypt python-jose httpx
    echo. > .deps_installed
)

:: Initialize database on first run
if not exist "zuzan.db" (
    echo  Initializing database...
    python -c "from database import init_db; init_db()"
    echo  Database created!
)

start "ZuZan Backend" cmd /k "python start.py --reload"
echo  Backend running on http://localhost:8001
echo.
timeout /t 5 /nobreak >NUL

:: ── Start React Frontend ──────────────────────────────────────────────────────
echo  [3/4] Starting ZuZan frontend...
cd /d "%~dp0zuzan-app"

if not exist "node_modules" (
    echo  Installing frontend dependencies (first run only, 3-5 min)...
    call npm install
    call npm install recharts
)

start "ZuZan Frontend" cmd /k "npm start"
echo  Frontend starting on http://localhost:3000
echo.
timeout /t 4 /nobreak >NUL

:: ── Open Browser ──────────────────────────────────────────────────────────────
echo  [4/4] Opening ZuZan in browser...
timeout /t 6 /nobreak >NUL
start http://localhost:3000

:: ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo  ================================================
echo    ZuZan is running!
echo.
echo    App:      http://localhost:3000
echo    Backend:  http://localhost:8001
echo    API Docs: http://localhost:8001/docs
echo    Landing:  Open zuzan-landing.html in browser
echo  ================================================
echo.
pause
