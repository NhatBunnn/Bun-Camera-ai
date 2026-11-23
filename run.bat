@echo off
chcp 65001 >nul
echo Đang khởi chạy Bun Camera AI...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)
pause
