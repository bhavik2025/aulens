"""Final verdict on the full real-data history: baseline strategy vs. a volatility-gated variant.

Walk-forward: choose (lookback, entry_z) on the previous 6 months, trade the next month, roll.
Holdout: the last 3 months are traded once with settings chosen on everything before them.
Writes reports/final_summary.csv, reports/final_trades.csv, reports/final_monthly.csv.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aulens import ingest, analytics as an, backtest as bt  # noqa: E402
from aulens.costs import CostModel  # noqa: E402
from aulens.specs import PAIRS, SPECS  # noqa: E402

TRAIN, TEST, HOLD = (int(x) for x in (sys.argv[1:4] if len(sys.argv) > 3 else (6, 1, 3)))
df = an.add_fine_price(ingest.load_folder(ROOT / "data" / "raw"))
cm = CostModel()
carry = an.implied_carry(df)
gold = an.front_contract(df, "GOLDM")["fine_px"]
gate = bt.volatility_gate(gold)
P = bt.Params()
print(f"data {df['date'].min().date()} -> {df['date'].max().date()} ({df['date'].nunique()} days); "
      f"train {TRAIN}m / test {TEST}m / holdout last {HOLD}m; gate on {gate.mean():.0%} of days")

rows, trades_all = [], []
for variant, g in (("baseline", None), ("vol-gated", gate)):
    for pair in PAIRS:
        a, b, la, lb = PAIRS[pair]
        sp = an.pair_spread(df, pair, carry, tender_buffer_days=P.tender_buffer + P.max_hold + 3)
        folds, tr, hold = bt.walk_forward(sp, df, pair, cm, train_months=TRAIN, test_months=TEST,
                                          holdout_months=HOLD, min_trades=1, gate=g)
        s = bt.summary(tr)
        _, daily = bt.run(sp, df, pair, P, cm, gate=g)
        beta = bt.gold_attribution(daily, gold, la * SPECS[a].lot_g)["beta"]
        wf = tr[tr["segment"] == "walk-forward"] if len(tr) else tr
        ho = tr[tr["segment"] == "holdout"] if len(tr) else tr
        rows.append({"variant": variant, "pair": pair, "trades": s["trades"],
                     "gross_rs": round(s.get("gross_rs", 0)), "costs_rs": round(s.get("costs_rs", 0)),
                     "net_rs": round(s.get("net_rs", 0)), "wf_trades": len(wf), "wf_net_rs": round(wf["net"].sum()) if len(wf) else 0,
                     "holdout_trades": len(ho), "holdout_net_rs": round(ho["net"].sum()) if len(ho) else 0,
                     "hit_rate": round(s.get("hit_rate", np.nan), 2), "t_stat": round(s.get("t_stat_net", np.nan), 2),
                     "gold_beta": round(beta, 3), "verdict": s["verdict"]})
        if len(tr):
            trades_all.append(tr.assign(pair=pair, variant=variant))

res = pd.DataFrame(rows)
tr = pd.concat(trades_all, ignore_index=True)
out = ROOT / "reports"; out.mkdir(exist_ok=True)
tag = f"_{TRAIN}{TEST}{HOLD}"
res.to_csv(out / f"final_summary{tag}.csv", index=False)
tr.to_csv(out / f"final_trades{tag}.csv", index=False)
tr["month"] = pd.to_datetime(tr["exit_date"]).dt.to_period("M").astype(str)
monthly = tr.pivot_table(index="month", columns="variant", values="net", aggfunc="sum").fillna(0).round(0)
monthly.to_csv(out / f"final_monthly{tag}.csv")

pd.set_option("display.width", 260)
print(res.drop(columns="verdict").to_string(index=False))
print("\nPooled across all six pairs (trades overlap in time, so this overstates independence):")
for v, g in tr.groupby("variant"):
    n = g["net"]
    t = n.mean() / (n.std(ddof=1) / np.sqrt(len(n))) if len(n) > 1 else np.nan
    ho = g[g["segment"] == "holdout"]["net"]
    print(f"  {v:10s} trades {len(n):3d}  gross {g['gross'].sum():>10,.0f}  costs {g['costs'].sum():>9,.0f}  "
          f"net {n.sum():>10,.0f}  hit {(n > 0).mean():.0%}  t {t:.2f}  | holdout trades {len(ho)} net {ho.sum():,.0f}")
print("\nNet P&L by exit month (Rs):")
print(monthly.to_string())
