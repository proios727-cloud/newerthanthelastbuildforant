# Sports desk — standalone paper bot

The paper worker is now under runtime/bot.py. It is separate from the optional eve conversational agent and uses Python standard library only. No Node, model key, real trading deposit, or private order transport is needed to run the paper worker itself. Sports market collection additionally needs an Odds API key and verified mapping; crypto uses public Kraken data.

Start with runtime/README.md. The default configuration deliberately retains safety/cost blocks; a running loop does not imply trades or positive returns. See ../CASH-READINESS.md and ../VALIDATION.md for verified costs and tests. Existing computer must remain awake; this is not a deployed cloud service.

On Mac/Linux run `./start-paper.sh`; on Windows with Python Launcher installed run `start-paper.bat`. The scripts choose $1,000 paper bankroll unless PAPER_BANKROLL is set. A database cannot silently switch bankroll or desk. New test amounts need a separate --db path. To stop, use the stop-paper script or Ctrl+C. To restart after HALT, explicitly remove runtime/HALT and review the saved state first.

The sports default mapping is unverified and cannot trade; copy the config to a local file, review exact event/ticker/outcome/rules/fees and pass --config runtime/config.local.json. Supply ODDS_API_KEY in the process environment, never in a shared archive or chat. Optional eve agent uses its own model credential field guide and is not wired as the tick execution controller. Live market orders are not implemented. Crypto strategy backtests and limitations are in runtime/results and runtime/backtest.py.
