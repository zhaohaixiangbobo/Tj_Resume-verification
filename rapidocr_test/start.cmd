@echo off
chcp 65001 >nul
cd /d "%~dp0"
"D:\3-anaconda\envs\py312\python.exe" app.py
if errorlevel 1 pause
