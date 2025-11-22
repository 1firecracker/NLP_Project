# One-click startup script for frontend and backend servers (PowerShell version)
# This script starts both backend and frontend in separate windows

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Agent for Exam" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get the directory where the script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start backend server
Write-Host "Starting backend server..." -ForegroundColor Yellow
$BackendPath = Join-Path $ScriptDir "backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$BackendPath'; .\venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" -WindowStyle Normal

# Wait for backend to start
Start-Sleep -Seconds 2

# Start frontend server
Write-Host "Starting frontend server..." -ForegroundColor Yellow
$FrontendPath = Join-Path $ScriptDir "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$FrontendPath'; npm run dev" -WindowStyle Normal

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Startup completed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend server: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Frontend server: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tips:" -ForegroundColor Yellow
Write-Host "- Both services are running in separate windows" -ForegroundColor Gray
Write-Host "- Close the corresponding window to stop the service" -ForegroundColor Gray
Write-Host "- Backend logs are displayed in the backend window" -ForegroundColor Gray
Write-Host "- Frontend logs are displayed in the frontend window" -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to exit"