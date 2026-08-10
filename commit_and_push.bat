@echo off
cd /d C:\Zuzan

echo === Removing lock files ===
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\refs\heads\main.lock del /f .git\refs\heads\main.lock

echo === Copying fixed files ===
copy /y App_js_fixed.js zuzan-app\src\App.js
copy /y App_mobile_js_fixed.js zuzan-app\src\App.mobile.js

echo === Patching backend files ===
py patch_backend.py 2>nul || python patch_backend.py 2>nul || python3 patch_backend.py 2>nul || echo [WARN] Python not found — skipping backend patch

echo === Staging all tracked changes ===
git add -u
git add zuzan-app/src/App.js
git add zuzan-app/src/App.mobile.js
git add zuzan-landing.html
git add audit_reports/
git add zuzan-backend/companies.py
git add zuzan-backend/payroll.py
git add zuzan-backend/billing.py
git add zuzan-backend/main.py
git add netlify.toml
git diff --cached --stat

echo === Committing ===
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
set STAMP=%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%
git -c user.email="dev@solutha.co.za" -c user.name="ZuZan Dev" commit -m "feat: profile name edit — PATCH /auth/me endpoint + Profile settings tab [%STAMP%]" --allow-empty

echo === Pushing ===
git push origin main

echo === Done — commit hash: ===
git rev-parse HEAD

pause
