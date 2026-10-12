# Cost and cash readiness — 11 October 2026 ET

No real funds are required to build or run paper experiments. No account balance, KYC, bank approval or personally available fee tier has been inspected. No deposits, subscriptions or orders were made.

| Item | Cost verified from official sources | Scope |
|---|---|---|
| Local deterministic Python runners | $0 software subscription | Existing computer, internet and electricity; computer must stay awake |
| Crypto public Kraken data | No trading account credential required | Public REST market data; rate limits/uptime apply |
| Sports odds test key | Free 500 credits/month | Limited tests, not continuous two-sport coverage |
| Sports odds paid plans | 20K credits $30/month; 100K $59; 5M $119 | Subscribe only after measured collection needs |
| Optional always-on VM | 1GiB $6/month; 2GiB $12/month | Estimate sufficient for light Python collection, not benchmarked capacity; separate processes and databases |
| Optional LLM agents | Metered, unnecessary for deterministic loops | Not an every-tick requirement; separate credentials and caps |

Illustrative quota budget: NFL + MLB, moneyline, two bookmaker regions = four credits per full odds polling cycle. At five-minute polling over eight hours/day for 30 days, odds consume 11,520 credits. Two score requests/cycle would add 5,760 = 17,280, fitting 20K; this runner currently does not implement live score execution. One-minute equivalent is 86,400 total, fitting 100K. Runtime explicit bookmaker selections may have different credit cost. Requests, markets and bookmaker groups must be measured. A faster polling loop cannot make upstream data fresher.

## Trading and funding fees

Kraken Pro current entry tier: maker 0.40%, taker 0.80% per side. Taker/taker entry and exit cost approximately 1.6% before spread and slippage. Actual rates depend on account tier and product. Instant Buy has a different schedule and spread. Do not simulate lower fees merely to make a backtest look profitable.

Kalshi current general event taker formula is multiplier × 0.07 × contracts × price × (1−price), with rounding and series exceptions. At 50¢, the fee table lists $1.75 for 100 contracts; single contracts list 2¢. KXNFLGAME and KXMLBGAME maker fees are not necessarily zero. Exact fees need current series metadata and order-fill verification. Configured paper reserves are estimates, not broker reconciled actual fees.

Kraken ACH via Plaid: no deposit processing fee, $1 minimum, verified US account and supported same-name bank required. Funds may be available for trading within minutes; seven-day withdrawal hold applies. Kalshi ACH: free, $10 minimum; full settlement typically within five business days. Card deposits may add up to 2%. Neither bank connection is verified here.

## Capital

- **Needed today: $0 trading deposits.** Use independent $1,000 paper balances or any chosen amount.
- **Optional later pilot reserve: $250 per desk ($500 total).** This is a suggested experiment budget, not an exchange minimum or sufficient-capital/profit claim. Commit only after strategy and execution validation and explicit live authorization.
- Subscriptions and trading bankroll are separate. A paid sports feed can be larger than returns on a small experimental account; measure economics before paying.
- Live exchange order minimums and configured position limits jointly determine whether a small account can enter. Kraken AssetPairs metadata is authoritative at startup; requirements change with asset prices. The checked public snapshot had BTC ordermin 0.00005, SOL 0.06, USD costmin 0.50; at snapshot asks those were about $4.19 BTC and $6.73 SOL before fees. This is not a current guaranteed minimum dollar amount or evidence the user can trade.

## Cash-readiness gates

Paper mode does not become live when funds are deposited. There is no private order transport in these runners. Outstanding live prerequisites include identity/bank verification, exchange eligible products and actual fee tiers, credential permissions, broker reconciliation, order-state handling, tested kill switches and authenticated private fills. Sports also needs licensed odds, reviewed market matching, settlement/fee mapping and better live-state inputs before in-play execution. A working collector is not a demonstrated profitable strategy.

## Official references

- https://the-odds-api.com/#pricing
- https://the-odds-api.com/liveapi/guides/v4/
- https://www.digitalocean.com/pricing/droplets
- https://www.kraken.com/features/fee-schedule
- https://docs.kraken.com/api/docs/rest-api/get-tradable-asset-pairs/
- https://support.kraken.com/articles/8795459449492-how-do-i-fund-my-account-with-usd-using-ach-via-plaid-
- https://kalshi.com/docs/kalshi-fee-schedule.pdf
- https://help.kalshi.com/en/articles/13823798-bank-deposits
