"""Quick health check of data/raw: coverage per month, missing weekdays, and the
GOLDGUINEA / GOLDPETAL premium over GOLDTEN at the same expiry.
Usage: python scripts/check_data.py"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aulens import ingest, analytics as an  # noqa: E402

log = []
df = an.add_fine_price(ingest.load_folder(ROOT / "data" / "raw", log))
print("validation log:", log or "clean")
days = df.groupby(df["date"].dt.to_period("M"))["date"].nunique()
for m, n in days.items():
    wd = pd.bdate_range(m.start_time, m.end_time)
    have = set(df.loc[df["date"].dt.to_period("M") == m, "date"])
    miss = [d.strftime("%d") for d in wd if d not in have]
    rows = df[df["date"].dt.to_period("M") == m].groupby("date").size()
    print(f"{m}: {n} days, rows/day {sorted(rows.unique())}, weekdays without a file: {miss or 'none'}")

out = []
for dt, g in df[df["volume"] > 0].groupby("date"):
    p = g.pivot_table(index="expiry", columns="symbol", values="fine_px")
    need = ["GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]
    if not set(need) <= set(p.columns):
        continue
    e = [x for x in p.index if (x - dt).days > 6 and p.loc[x, need].notna().all()]
    if e:
        e = e[0]
        out.append({"date": dt, "GUINEA": np.log(p.loc[e, "GOLDGUINEA"] / p.loc[e, "GOLDTEN"]) * 1e4,
                    "PETAL": np.log(p.loc[e, "GOLDPETAL"] / p.loc[e, "GOLDTEN"]) * 1e4})
o = pd.DataFrame(out).set_index("date")
print("\nPremium over GOLDTEN, same expiry (bps):")
print(o.groupby(o.index.to_period("M")).agg(["median", "min", "max"]).round(0))
print("days above zero:", {c: f"{(o[c] > 0).sum()}/{len(o)}" for c in o})
