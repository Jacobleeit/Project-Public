@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 backup_report.py --demo
goto check_result
:use_python
python backup_report.py --demo
:check_result
if errorlevel 1 goto failed
start "" "%~dp0reports\backup_report.html"
goto done
:failed
echo Demo could not run. Install Python 3.10 or newer and try again.
:done
pause
