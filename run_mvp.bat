@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python 가상환경이 없습니다. README의 설치 방법을 확인해 주세요.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
