@echo off
cd /d "%~dp0"
type nul > runtime\HALT
echo Paper HALT requested; inspect process shutdown.
pause
