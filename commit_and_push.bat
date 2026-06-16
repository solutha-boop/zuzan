@echo off
cd /d C:\Zuzan

echo === Removing lock files ===
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock

echo === Fetching from GitHub ===
git fetch origin

echo === Resetting staging area ===
git reset HEAD

echo === Copying fixed files ===
copy /y App_js_fixed.js zuzan-app\src\App.js

echo === Staging ===
git add zuzan-app/src/App.js
git add zuzan-backend/main.py
git add zuzan-backend/crypto.py
git add zuzan-backend/companies.py
git add zuzan-backend/suppliers.py
git add zuzan-backend/database.py
git add zuzan-backend/payroll.py
git diff --cached --stat

echo === Committing ===
git -c user.email="dev@zuzan.co.za" -c user.name="ZuZan Dev" commit -m "fix: admin dashboard refresh button — loading state, visible errors, last-updated timestamp"

echo === Pushing ===
git push origin main

echo === Done — commit hash: ===
git rev-parse HEAD

pause
