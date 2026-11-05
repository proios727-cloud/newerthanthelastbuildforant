# TradingAgents integration

Upstream: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache-2.0). Not vendored; installed via `setup.sh`.

## How the graph runs (LangGraph)

```
START ─┬─ Market Analyst ───────┐
       ├─ Sentiment Analyst ────┤   (parallel, each loops agent⇄tools, then wrap_up)
       ├─ News Analyst ─────────┤
       └─ Fundamentals Analyst ─┘
                 │
      Bull Researcher ⇄ Bear Researcher   (max_debate_rounds)
                 │
         Research Manager  → investment plan
                 │
              Trader       → trade proposal
                 │
 Aggressive ⇄ Neutral ⇄ Conservative     (max_risk_discuss_rounds)
                 │
        Portfolio Manager  → final rating → END
```

Source: `tradingagents/graph/setup.py`, agents under `tradingagents/agents/`.
Data vendors: Yahoo (default), Alpha Vantage, SEC EDGAR, FRED, Reddit, StockTwits, Polymarket.

## Mapping to this desk (`desk.json` seats)

| TradingAgents role | Desk seat / charter |
|---|---|
| Market / Fundamentals / News / Sentiment analysts | `charters/analyst.md`, `charters/macro.md` |
| Bull ⇄ Bear researchers + Research Manager | `charters/quant.md` (thesis) |
| Trader | `charters/trader.md` (order *preview* only) |
| Risk debators (aggr/neutral/cons) | `charters/risk.md` (veto) |
| Portfolio Manager | `charters/pm.md` (coordinator) |
| Report output (`reporting.py`) | `charters/reporter.md` |

TradingAgents emits a rating, never an order. Desk rule stands: nothing executes without the human `EXECUTE`.

## Run it

```bash
bash integrations/tradingagents/setup.sh          # clone + venv + install + tests
cp integrations/tradingagents/.env.example ~/.tradingagents.env  # add keys
python integrations/tradingagents/run_desk.py NVDA 2026-09-30
```

Output lands in `shadow.jsonl` as a PAPER-mode signal row.

## Backtest

```bash
python integrations/tradingagents/backtest_desk.py NVDA,SPY,AAPL 2026-06-01 2026-08-31 7
```

Scores each rating (Buy/Overweight/Hold/Underweight/Sell) by how often it called the direction correctly (hit rate) and its mean alpha vs. the benchmark. It evaluates decision quality only; there's no position sizing or fills. Results go to `integrations/tradingagents/results/`.
