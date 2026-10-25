@echo off
cd /d C:\Zuzan

echo === Setting credential helper ===
git config --global credential.helper manager

echo === Removing lock files ===
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\refs\heads\main.lock del /f .git\refs\heads\main.lock

echo === Copying fixed files ===
copy /y App_js_fixed.js zuzan-app\src\App.js
copy /y App_mobile_js_fixed.js zuzan-app\src\App.mobile.js

echo === Patching backend files ===
python patch_backend.py 2>nul || py patch_backend.py 2>nul || echo [WARN] Python patch skipped

echo === Staging files ===
git add -u
git add zuzan-app/src/App.js
git add zuzan-app/src/App.mobile.js
git add zuzan-landing.html
git add audit_reports/
git add zuzan-backend/companies.py
git add zuzan-backend/payroll.py
git add zuzan-backend/billing.py
git add zuzan-backend/main.py
git add zuzan-backend/database.py
git add zuzan-backend/auth.py
git add zuzan-backend/email_service.py
git add zuzan-backend/accountant.py
git add zuzan-backend/integrations.py
git add zuzan-backend/clocking.py
git add zuzan-backend/xero_migrate.py
git add zuzan-backend/journal_check.py
git add clock.html
git add netlify.toml
git add commit_and_push.bat
git add patch_backend.py
git diff --cached --stat

echo === Committing ===
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%I
if "%~1"=="" (set MSG=feat: Xero migration wizard + partial payments + multi-entity switcher [%STAMP%]) else (set MSG=%~1 [%STAMP%])
git -c user.email="dev@solutha.co.za" -c user.name="ZuZan Dev" commit -m "%MSG%" --allow-empty

echo === Pushing ===
git push origin main
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Push failed. Run this in a terminal to fix:
    echo   cd C:\Zuzan ^&^& git push origin main
    pause
    exit /b 1
)

echo === Done ===
git rev-parse HEAD
pause
