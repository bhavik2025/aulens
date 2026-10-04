"""Reproduce the 'first look at real MCX data' numbers in the Round 1 deck.

Usage:  python scripts/first_look.py
Needs:  data/raw/2026-10-01.csv (Bhavcopy) and data/raw/*Detail report.xls (MCX date-wise turnover report).
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aulens import ingest, analytics as an  # noqa: E402

RAW = ROOT / "data" / "raw"

# 1) One Bhavcopy day: matched-expiry premiums and GOLDM vs GOLDTEN after carry
df = an.add_fine_price(ingest.load_folder(RAW))
day = df[df["volume"] > 0]
piv = day.pivot(index="expiry", columns="symbol", values="fine_px")
for sym in ("GOLDGUINEA", "GOLDPETAL"):
    prem = (np.log(piv[sym] / piv["GOLDTEN"]) * 1e4).dropna().round(1)
    print(f"{sym} vs GOLDTEN, same expiry (bps):", prem.to_dict())

m = df[df["symbol"] == "GOLDM"].set_index("expiry")
t = df[df["symbol"] == "GOLDTEN"].set_index("expiry")
liquid = m[m["volume"] > 0].sort_values("volume", ascending=False).index[:2].sort_values()
r = np.log(m.loc[liquid[1], "fine_px"] / m.loc[liquid[0], "fine_px"]) / ((liquid[1] - liquid[0]).days / 365)
print(f"Implied carry from GOLDM {liquid[0].date()} / {liquid[1].date()}: {r:.2%}")
for em, et in (("2026-11-05", "2026-10-30"), ("2026-12-04", "2026-11-30")):
    em, et = pd.Timestamp(em), pd.Timestamp(et)
    if em in m.index and et in t.index:
        raw = np.log(m.loc[em, "close"] / t.loc[et, "close"]) * 1e4
        adj = (np.log(m.loc[em, "fine_px"] / t.loc[et, "fine_px"]) - r * (em - et).days / 365) * 1e4
        print(f"GOLDM {em.date()} vs GOLDTEN {et.date()}: raw {raw:.1f} bps -> adjusted {adj:.1f} bps")

# 2) Turnover report: turnover-weighted price per gram (mixes expiries, so rough)
files = list(RAW.glob("*Detail report*.xls"))
if files:
    tv = pd.read_html(files[0])[0]
    tv["Date"] = pd.to_datetime(tv["Date"], format="%d %b %Y")
    lot = {"GOLDM": 100, "GOLDTEN": 10, "GOLDGUINEA": 8, "GOLDPETAL": 1}
    pur = {"GOLDM": 0.995, "GOLDTEN": 0.999, "GOLDGUINEA": 0.999, "GOLDPETAL": 0.999}
    g = tv[(tv["Instrument"] == "FUTCOM") & tv["Commodity"].isin(lot)].copy()
    g["fine"] = g["Total Value (Lakhs)"] * 1e5 / (g["Traded Contract (Lots)"] * g["Commodity"].map(lot)) / g["Commodity"].map(pur)
    p = g.pivot(index="Date", columns="Commodity", values="fine")
    print(f"Turnover report: {p.index.min().date()} to {p.index.max().date()}, {len(p)} days")
    for sym in ("GOLDGUINEA", "GOLDPETAL"):
        prem = np.log(p[sym] / p["GOLDTEN"]) * 1e4
        print(f"{sym} above GOLDTEN on {(prem > 0).sum()}/{prem.notna().sum()} days; median {prem.median():.0f} bps")
    avg = g.groupby("Commodity").agg(lots_per_day=("Traded Contract (Lots)", "mean"),
                                      value_cr_per_day=("Total Value (Lakhs)", lambda v: (v / 100).mean()))
    print(avg.round(0))
