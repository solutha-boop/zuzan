@echo off
cd /d C:\Zuzan

echo === Ensuring git credential helper is set ===
git config --global credential.helper wincred

echo === Removing lock files ===
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\refs\heads\main.lock del /f .git\refs\heads\main.lock

echo === Copying fixed files ===
copy /y App_js_fixed.js zuzan-app\src\App.js
copy /y App_mobile_js_fixed.js zuzan-app\src\App.mobile.js

echo === Patching backend files ===
where py >nul 2>&1 && py patch_backend.py || where python >nul 2>&1 && python patch_backend.py || echo [WARN] Python not found — skipping backend patch

echo === Staging all tracked changes (usage: commit_and_push.bat "your message") ===
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
git add zuzan-backend/journal_check.py
git add clock.html
git add netlify.toml
git diff --cached --stat

echo === Committing ===
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%I
if "%~1"=="" (set MSG=feat: termination reasons modal, employment category (temp labour/learnership/foreign national UIF/SDL exemption), reinstate with history [%STAMP%]) else (set MSG=%~1 [%STAMP%])
git -c user.email="dev@solutha.co.za" -c user.name="ZuZan Dev" commit -m "%MSG%" --allow-empty

echo === Pushing ===
git push origin main
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Push failed. Check the error above.
    echo Common fixes:
    echo   1. Run: git config --global credential.helper wincred
    echo   2. Then: git push origin main  (and sign in when prompted)
    pause
    exit /b 1
)

echo === Done — commit hash: ===
git rev-parse HEAD

pause
