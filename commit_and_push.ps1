param([string]$Message = "")

Set-Location "C:\Zuzan"

Write-Host "=== Ensuring git credential helper ===" -ForegroundColor Cyan
git config --global credential.helper manager

Write-Host "=== Removing lock files ===" -ForegroundColor Cyan
@(".git\index.lock", ".git\HEAD.lock", ".git\refs\heads\main.lock") | ForEach-Object {
    if (Test-Path $_) { Remove-Item -Force $_; Write-Host "  Removed $_" }
}

Write-Host "=== Copying fixed files ===" -ForegroundColor Cyan
Copy-Item "App_js_fixed.js"        "zuzan-app\src\App.js"         -Force
Copy-Item "App_mobile_js_fixed.js" "zuzan-app\src\App.mobile.js"  -Force

Write-Host "=== Patching backend files ===" -ForegroundColor Cyan
$py = if (Get-Command py     -ErrorAction SilentlyContinue) { "py" }
      elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
      else { $null }
if ($py) {
    $job = Start-Job { param($p) & $p "C:\Zuzan\patch_backend.py" } -ArgumentList $py
    $done = Wait-Job $job -Timeout 30
    if (-not $done) {
        Stop-Job $job; Write-Host "[WARN] patch_backend.py timed out — skipping" -ForegroundColor Yellow
    } else {
        Receive-Job $job
    }
    Remove-Job $job -Force
} else {
    Write-Host "[WARN] Python not found — skipping backend patch" -ForegroundColor Yellow
}

Write-Host "=== Staging files ===" -ForegroundColor Cyan
$filesToAdd = @(
    "zuzan-app/src/App.js",
    "zuzan-app/src/App.mobile.js",
    "zuzan-landing.html",
    "audit_reports/",
    "zuzan-backend/companies.py",
    "zuzan-backend/payroll.py",
    "zuzan-backend/billing.py",
    "zuzan-backend/main.py",
    "zuzan-backend/database.py",
    "zuzan-backend/auth.py",
    "zuzan-backend/email_service.py",
    "zuzan-backend/accountant.py",
    "zuzan-backend/integrations.py",
    "zuzan-backend/clocking.py",
    "zuzan-backend/journal_check.py",
    "clock.html",
    "netlify.toml",
    "commit_and_push.bat",
    "commit_and_push.ps1",
    "patch_backend.py"
)
git add -u
foreach ($f in $filesToAdd) {
    if (Test-Path $f) { git add $f }
}
git diff --cached --stat

Write-Host "=== Committing ===" -ForegroundColor Cyan
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$msg   = if ($Message) { "$Message [$stamp]" } else {
    "fix: NBCPSS grade badge uses security_grade, area dropdown with rural/urban med-aid rates [$stamp]"
}
git -c user.email="dev@solutha.co.za" -c user.name="ZuZan Dev" commit -m $msg --allow-empty

Write-Host "=== Pushing ===" -ForegroundColor Cyan
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Push failed — see above." -ForegroundColor Red
    Write-Host "  Fix: run  git push origin main  in a terminal and sign in when prompted." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "=== Done ===" -ForegroundColor Green
git rev-parse HEAD
Read-Host "Press Enter to close"
