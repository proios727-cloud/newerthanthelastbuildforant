@echo off
rem Daily research loop for the 24/7 Agent Hedge Fund (PAPER mode).
rem Scheduled by ops/daily_loop.xml (Task Scheduler). One full loop per run.
cd /d C:\Users\proio\newerthanthelastbuildforant
.venv\Scripts\python.exe -m fund loop --once >> ledger\loop.log 2>&1