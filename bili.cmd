@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m bili_transcript %*
) else (
  uv run python -m bili_transcript %*
)
