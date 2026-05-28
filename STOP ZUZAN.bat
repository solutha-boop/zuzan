@echo off
title ZuZan - Stopping
color 0C

echo.
echo  ================================================
echo    ZuZan - Stopping all services...
echo  ================================================
echo.

taskkill /FI "WINDOWTITLE eq ZuZan Backend*" /F >NUL 2>&1
taskkill /FI "WINDOWTITLE eq ZuZan Frontend*" /F >NUL 2>&1

for /f "tokens=5" %%a in ('netstat -aon ^| find ":8001" ^| find "LISTENING"') do taskkill /PID %%a /F >NUL 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3000" ^| find "LISTENING"') do taskkill /PID %%a /F >NUL 2>&1

echo  ZuZan stopped successfully.
echo.
pause
