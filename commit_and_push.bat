@echo off
cd /d C:\Zuzan

echo === Removing lock files ===
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\refs\heads\main.lock del /f .git\refs\heads\main.lock

echo === Fetching from GitHub ===
git fetch origin

echo === Resetting staging area ===
git reset HEAD

echo === Copying fixed files ===
copy /y App_js_fixed.js zuzan-app\src\App.js
copy /y App_mobile_js_fixed.js zuzan-app\src\App.mobile.js

echo === Patching backend files ===
py patch_backend.py 2>nul || python patch_backend.py 2>nul || python3 patch_backend.py 2>nul || echo [WARN] Python not found — skipping backend patch

echo === Staging ===
git add patch_backend.py
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
git add zuzan-backend/fixed_assets.py
git add zuzan-backend/portal.py
git add zuzan-backend/stitch.py
git add zuzan-backend/saltedge.py
git add zuzan-backend/requirements.txt
git add zuzan-backend/start.py
git add zuzan-backend/financial_statements.py
git add zuzan-backend/bank_direct_feeds.py
git add zuzan-backend/documents.py
git add zuzan-backend/csv_import.py
git add zuzan-backend/category_rules.py
git add zuzan-backend/budgets.py
git add zuzan-backend/analytics.py
git add zuzan-backend/billing.py
git add zuzan-backend/recurring_invoices.py
git add zuzan-backend/credit_notes.py
git add "START ZUZAN.bat"
git add audit_reports/
git diff --cached --stat

echo === Committing ===
git -c user.email="dev@solutha.co.za" -c user.name="ZuZan Dev" commit -m "fix: client-side subscription status correction — expired+future trial_ends treated as trial 