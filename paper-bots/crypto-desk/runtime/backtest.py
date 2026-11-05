"""Bounded public-history replay. Hypothetical, not live execution evidence."""
import argparse
import json
from pathlib import Path
import time
import bot


def prepare(rows, interval, daily, now):
    bot.closed_candles(rows,interval,now)
    bot.closed_candles(daily,86400,now)
    rows=[list(map(float,r[:5])) for r in rows if float(r[0])+interval<=now]
    days=[list(map(float,r[:5])) for r in daily if float(r[0])+86400<=now]
    close=[r[4] for r in rows]
    fast,slow=bot.ema(close,20),bot.ema(close,50)
    daily_ema=bot.ema([r[4] for r in days],50)
    regimes=[]
    for row in rows:
        eligible=[j for j,d in enumerate(days) if d[0]+86400<=row[0]+interval]
        j=eligible[-1] if eligible else -1
        regimes.append(j>=50 and daily_ema[j] is not None and days[j][4]>daily_ema[j] and daily_ema[j]>daily_ema[j-1])
    return rows,fast,slow,regimes


def simulate(prepared, start, end, strategy, fee=.008, slippage=.0005, cap=.005):
    rows,fast,slow,regime=prepared
    cash=1000.0; units=0.0; entry=0; basis=0; entered=0; peak=1000.; drawdown=0.; trades=[]; fees=0.; blocked=0;curve=[]
    estimated_cost=2*(fee+slippage)
    def sell(price, stamp, reason):
        nonlocal cash,units,fees
        execution=price*(1-slippage); commission=units*execution*fee
        proceeds=units*execution-commission
        cash+=proceeds;fees+=commission
        trades.append({"entry_time":entered,"exit_time":stamp,"reason":reason,"net_pnl":proceeds-basis})
        units=0
    for i in range(start,end):
        stamp,opening,high,low,close=rows[i]
        intrabar_exit=False
        # All decisions use prior COMPLETED bars. Fill at next OPEN plus assumed cost.
        j=i-1
        if units and (fast[j]<slow[j] or stamp-entered>=72*3600):
            sell(opening,stamp,"prior_bar_trend_or_time")
        if units:
            stop=entry*.96; target=entry*1.08
            if opening<=stop:
                sell(opening,stamp,"gap_below_stop")
            elif low<=stop:
                sell(stop,stamp,"stop_first_if_both_touched")
                intrabar_exit=True
            elif high>=target:
                sell(max(opening,target),stamp,"take_profit")
                intrabar_exit=opening<target
        cross=fast[j]>slow[j] and fast[j-1]<=slow[j-1]
        if strategy=="pullback":
            cross=fast[j]>slow[j] and rows[j][4]>fast[j] and rows[j-1][4]<=fast[j-1]
        elif strategy=="breakout":
            cross=fast[j]>slow[j] and rows[j][4]>max(r[2] for r in rows[j-20:j])
        condition=cross and regime[j]
        # Never travel backwards to this bar's OPEN after an intrabar exit.
        if not units and condition and not intrabar_exit:
            if estimated_cost>cap:
                blocked+=1
            else:
                entry=opening*(1+slippage);entered=stamp
                notional=min(cash*.1/(1+fee),cash/(1+fee));units=notional/entry
                commission=notional*fee;basis=notional+commission;cash-=basis;fees+=commission
                # Same-bar stops after the OPEN entry are possible; adverse order first.
                if low<=entry*.96:
                    sell(min(opening,entry*.96),stamp,"entry_bar_stop")
                elif high>=entry*1.08:
                    sell(entry*1.08,stamp,"entry_bar_take_profit")
        equity=cash+units*close*(1-slippage)*(1-fee)
        peak=max(peak,equity);drawdown=max(drawdown,(peak-equity)/peak)
        curve.append({"timestamp":stamp,"net_equity":equity})
    if units:
        interval=rows[1][0]-rows[0][0]
        sell(rows[end-1][4],rows[end-1][0]+interval,"window_end_liquidation_at_close")
    peak=max(peak,cash);drawdown=max(drawdown,(peak-cash)/peak)
    return {"strategy":strategy,"initial":1000,"final":cash,"net_profit":cash-1000,"net_return_fraction":cash/1000-1,
            "max_sampled_drawdown_fraction":drawdown,"closed_trades":len(trades),"fees":fees,"cost_blocked_candidates":blocked,
            "estimated_cost_cap":cap,"trade_log":trades,"equity_curve":curve}


def benchmark(rows,start,end,exposure,fee=.008,slippage=.0005):
    stake=1000*exposure/(1+fee)
    units=stake/(rows[start][1]*(1+slippage))
    final=1000-stake-stake*fee+units*rows[end-1][4]*(1-slippage)*(1-fee)
    return {"name":f"buy_hold_{exposure:.0%}_exposure","net_profit":final-1000,"final":final}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path)
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent/"results")
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.fixture:
        snapshot=json.loads(args.fixture.read_text())
        source="KRAKEN_PUBLIC_SAVED_REPLAY" if snapshot.get("source")=="KRAKEN_PUBLIC" else "SYNTHETIC_FIXTURE"
    else:
        snapshot={"captured_at":time.time(),"source":"KRAKEN_PUBLIC","pairs":{}}
        for pair,alias in bot.PAIRS.items():
            intervals={}
            for interval in (60,240,1440):
                result,stamp=bot.request_public("OHLC",{"pair":alias,"interval":interval})
                keys=[k for k in result if k!="last"]
                if len(keys)!=1:raise ValueError("ambiguous pair history")
                intervals[str(interval)]={"received_at":stamp,"rows":result[keys[0]]}
            snapshot["pairs"][pair]=intervals
        snapshot["captured_at"]=time.time();source="KRAKEN_PUBLIC"
    (args.output/"source_snapshot.json").write_text(json.dumps(snapshot,indent=2))
    reports=[]
    for pair,intervals in snapshot["pairs"].items():
        for minutes in (60,240):
            prepared=prepare(intervals[str(minutes)]["rows"],minutes*60,intervals["1440"]["rows"],snapshot["captured_at"])
            rows=prepared[0]; split=len(rows)*2//3
            for label,start,end in (("earlier_two_thirds",52,split),("untouched_final_third",split,len(rows))):
                if end-start<2:raise ValueError("insufficient historical test window")
                entries=[]
                for cap in (.005,.02):
                    for strategy in ("ema_cross","pullback","breakout"):
                        entries.append(simulate(prepared,start,end,strategy,cap=cap))
                reports.append({"pair":pair,"interval_minutes":minutes,"segment":label,"start_utc_epoch":rows[start][0],"end_utc_epoch":rows[end-1][0]+minutes*60,"bars":end-start,
                                "strategies":entries,"benchmarks":[{"name":"cash","final":1000,"net_profit":0},benchmark(rows,start,end,.1),benchmark(rows,start,end,1)]})
    report={"mode":"HYPOTHETICAL HISTORICAL PAPER BACKTEST","source":source,"fee_rate_per_side":.008,"adverse_slippage_per_side":.0005,
            "settings_selected_without_test_optimization":True,"capital_per_asset":1000,"portfolio_aggregate":None,
            "limitations":["720 bars maximum: about30 days1h/120days4h; not durable edge proof","dailyEMA50 and intradayEMA20/50;50-bar minimum warmup, not runtime250","quote/depth history absent; spread represented only by adverse slippage reserve","0.5% cap deployable default blocks1.7%cost;2%cap alternative research only","stop4%/target8%;10%exposure;72h time exit fixed hypotheses","no venue minimums, precision, queue or latency simulation in historical replay","reported drawdown sampled at bar close after stop/target;intrabar equity drawdown may be worse"],"reports":reports}
    (args.output/"backtest_report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({"source":source,"reports":[{"pair":r["pair"],"interval":r["interval_minutes"],"segment":r["segment"],"bars":r["bars"],"net_results":[{"strategy":s["strategy"],"cap":s["estimated_cost_cap"],"pnl":round(s["net_profit"],2),"trades":s["closed_trades"]} for s in r["strategies"]],"benchmarks":r["benchmarks"]} for r in reports]},indent=2))


if __name__=="__main__":main()
