@echo off
chcp 65001 > nul
echo ========================================================
echo   NEXTGEN AI - Enterprise Energy Intelligence Platform
echo   Developer: Shohjahon Abdullayev
echo ========================================================
echo.
echo [1/3] Backend API server ishga tushirilmoqda (port 8000)...
start "NextGen Backend API" cmd /k ".\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"

echo [2/3] Telegram Bot ishga tushirilmoqda (@nextgenuzz_bot)...
start "NextGen Telegram Bot" cmd /k ".\.venv\Scripts\python.exe -m bots.run demo"

echo [3/3] Next.js Veb-platforma ishga tushirilmoqda (port 3000)...
start "NextGen Frontend Web" cmd /k "node frontend/node_modules/next/dist/bin/next start frontend -p 3000"

timeout /t 3 > nul
echo.
echo ✅ Barcha xizmatlar muvaffaqiyatli ishga tushirildi!
echo 🌐 Sayt manzili: http://localhost:3000
echo 🤖 Telegram Bot: @nextgenuzz_bot
echo.
start http://localhost:3000/login
pause
