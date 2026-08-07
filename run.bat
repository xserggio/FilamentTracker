@echo off
cd /d "%~dp0"
py -m pip show pywebview >nul 2>&1 || py -m pip install -r requirements.txt
start "" pyw app.py
