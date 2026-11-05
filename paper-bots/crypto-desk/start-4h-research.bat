@echo off
cd /d "%~dp0"
if not defined PAPER_BANKROLL set PAPER_BANKROLL=1000
py -3 runtime\bot.py --config runtime\config.4h-research.json --db runtime\state\4h-research.sqlite --bankroll %PAPER_BANKROLL% --loop --interval 60 %*
pause
