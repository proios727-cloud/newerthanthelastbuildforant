@echo off
cd /d "%~dp0"
if not defined PAPER_BANKROLL set PAPER_BANKROLL=1000
py -3 runtime\bot.py --config runtime\config.example.json --bankroll %PAPER_BANKROLL% --loop 300 %*
pause
