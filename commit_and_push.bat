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
copy /y App_mobile_js_fixed.js zuzan-app\src\App.mobile.js

echo === Staging ===
git add zuzan-app/src/App.js
git add zuzan-backend/main.py
git add zuzan-backend/crypto.py
git add zuzan-backend/companies.py
git add zuzan-backend/suppliers.py
git add zuzan-backend/database.py
git add zuzan-backend/payroll.py
git add zuzan-backend/journal.py
git add zuzan-backend/quotes.py
git add zuzan-backend/email_service.py
git add zuzan-backend/purchase_orders.py
git add zuzan-backend/auth.py
git add zuzan-backend/leave.py
git add zuzan-app/src/App.mobile.js
git add App_mobile_js_fixed.js
git diff --cached --stat

echo === Committing ===
git -c user.email="dev@solutha.co.za" -c user.name="ZuZan Dev" commit -m "feat: simplified mobile app -- Invoices, Expenses, Quotes only"

echo === Pushing ===
git push origin main

echo === Done — commit hash: ===
git rev-parse HEAD

pause
