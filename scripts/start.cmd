@echo off
setlocal
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --no-build-isolation -e . || exit /b 1
x2red serve --host 127.0.0.1 --port 8787 %*
