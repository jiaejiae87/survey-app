@echo off
title GitHub Push Helper

cd /d "%~dp0"

".venv\Scripts\python.exe" push_to_github.py

pause
