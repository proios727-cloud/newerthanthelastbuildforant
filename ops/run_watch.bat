@echo off
rem Intraday watch pass: mark quotes + stop/target checks. Runs every 15 min.
cd /d C:\Users\proio\newerthanthelastbuildforant
.venv\Scripts\python.exe -m fund loop --watch >> ledger\loop.log 2>&1