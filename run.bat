@echo off
REM Double-click this file to start Jobber.
cd /d "%~dp0"
python -m streamlit run app.py
pause
