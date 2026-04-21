@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  ORION — AREP Dev Server
::  Starts FastAPI backend + Vite frontend in separate windows.
::  Usage: start.bat [--no-reload]
:: ============================================================

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%arep_implementation"
set "FRONTEND_DIR=%ROOT%orion-frontend"

set "UVICORN_EXTRA=--reload"
if "%~1"=="--no-reload" set "UVICORN_EXTRA="

echo.
echo   ╔═══════════════════════════════════════╗
echo   ║     ORION  —  AREP  Dev Server        ║
echo   ╚═══════════════════════════════════════╝
echo.

:: ── dependency checks ──────────────────────────────────────
where uvicorn >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uvicorn not found.
    echo         Run:  cd arep_implementation ^&^& pip install -e ".[api]"
    pause & exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js from https://nodejs.org
    pause & exit /b 1
)

:: ── launch backend in its own window ───────────────────────
echo [ORION] Starting backend  →  http://localhost:8000  (docs: /docs)
start "ORION Backend" cmd /k "cd /d "%BACKEND_DIR%" && uvicorn arep.api.app:app --host 0.0.0.0 --port 8000 %UVICORN_EXTRA%"

:: short pause so uvicorn binds before Vite opens the browser
timeout /t 2 /nobreak >nul

:: ── launch frontend in its own window ──────────────────────
echo [ORION] Starting frontend →  http://localhost:5173
start "ORION Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo.
echo   Both services are running in separate windows.
echo   Backend   →  http://localhost:8000  (API docs: /docs)
echo   Frontend  →  http://localhost:5173
echo.
echo   Close the backend / frontend windows individually to stop each service.
echo.
pause
