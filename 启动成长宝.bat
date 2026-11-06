@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  ChengZhangBao one-click launcher
rem  Backend : FastAPI  http://127.0.0.1:8300  (dedicated port,
rem            avoids clash with other apps on :8000)
rem  Frontend: Vite     http://localhost:5173
rem  NOTE: keep this file inside D:\ChengZhangBao so the desktop
rem        shortcut never breaks on update.
rem ============================================================

rem ---- 1. Start backend if not already running (identity-checked) ----
rem A service on :8300 only counts as ours if its OpenAPI exposes auth/login
curl -s -m 2 http://127.0.0.1:8300/openapi.json 2>nul | findstr /c:"auth/login" >nul
if errorlevel 1 (
    start "CZB-Backend" /min cmd /c "cd /d ""%~dp0backend"" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8300"
)

rem ---- 2. Start frontend if not already running (identity-checked) ----
rem A service on :5173 only counts as ours if it serves our client.ts (czb_token)
curl -s -m 2 http://127.0.0.1:5173/src/api/client.ts 2>nul | findstr /c:"czb_token" >nul
if errorlevel 1 (
    start "CZB-Frontend" /min cmd /c "cd /d ""%~dp0frontend"" && npm run dev"
)

rem ---- 3. Wait briefly, then open browser ----
timeout /t 5 /nobreak >nul
start "" http://localhost:5173/

endlocal
exit
