"""Walk-forward backtest of every pair on the real data in data/raw.

Usage: python scripts/run_backtest.py [train_months] [test_months] [holdout_months]
Defaults 3 1 1 while history is short; use 12 3 6 once a full year+ is available.
Writes reports/backtest_summary.csv and reports/backtest_trades.csv.
"""
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aulens import ingest, analytics as an, backtest as bt  # noqa: E402
from aulens.costs import CostModel  # noqa: E402
from aulens.specs import PAIRS, SPECS  # noqa: E402

tr_m, te_m, ho_m = (int(x) for x in (sys.argv[1:4] if len(sys.argv) > 3 else (3, 1, 1)))
df = an.add_fine_price(ingest.load_folder(ROOT / "data" / "raw"))
days = pd.Series(sorted(df["date"].unique()))
gaps = days.diff().dt.days
if (gaps > 20).any():  # an isolated later file (e.g. a one-off sample day) is left out of the backtest
    cut = days[gaps > 20].iloc[0]
    df = df[df["date"] < cut]
print(f"data: {df['date'].min().date()} to {df['date'].max().date()}, {df['date'].nunique()} days; "
      f"walk-forward train {tr_m}m / test {te_m}m, holdout {ho_m}m")
cm = CostModel()
carry = an.implied_carry(df)
gold = an.front_contract(df, "GOLDM")["fine_px"]
rows, all_trades = [], []
for pair in PAIRS:
    sp = an.pair_spread(df, pair, carry)
    folds, trades, hold = bt.walk_forward(sp, df, pair, cm, train_months=tr_m, test_months=te_m, holdout_months=ho_m, min_trades=1)
    s = bt.summary(trades)
    a, b, la, lb = PAIRS[pair]
    _, daily = bt.run(sp, df, pair, bt.Params(), cm)
    attr = bt.gold_attribution(daily, gold, la * SPECS[a].lot_g)
    rows.append({"pair": pair, "spread_days": len(sp), "oos_trades": s["trades"],
                 "gross_rs": round(s.get("gross_rs", 0)), "costs_rs": round(s.get("costs_rs", 0)),
                 "net_rs": round(s.get("net_rs", 0)), "hit_rate": round(s.get("hit_rate", float("nan")), 2),
                 "t_stat": round(s.get("t_stat_net", float("nan")), 2), "holdout_trades": hold["trades"],
                 "holdout_net_rs": round(hold["net"]), "gold_beta": round(attr["beta"], 3), "verdict": s["verdict"]})
    if len(trades):
        all_trades.append(trades.assign(pair=pair))
res = pd.DataFrame(rows)
(ROOT / "reports").mkdir(exist_ok=True)
res.to_csv(ROOT / "reports" / "backtest_summary.csv", index=False)
if all_trades:
    pd.concat(all_trades).to_csv(ROOT / "reports" / "backtest_trades.csv", index=False)
pd.set_option("display.width", 250)
print(res.drop(columns="verdict").to_string(index=False))
for r in rows:
    print(f"{r['pair']}: {r['verdict']}")
