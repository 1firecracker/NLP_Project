@echo off
REM 启动后端服务器
cd /d %~dp0
call venv\Scripts\activate.bat
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

