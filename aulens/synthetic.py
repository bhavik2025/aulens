"""SYNTHETIC demo data — for testing the pipeline only, never for conclusions.

Generates Bhavcopy-shaped rows for the four gold contracts: a random-walk gold price,
cost-of-carry futures curves, contract-specific mean-reverting noise (larger for thin
contracts) and fake volume / open interest. Output columns match ingest.finalize().
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .specs import SPECS
from .ingest import finalize


def _expiries(start, end, day_lo, day_hi):
    out = []
    for m in pd.period_range(start - pd.DateOffset(months=1), end + pd.DateOffset(months=8), freq="M"):
        last = m.days_in_month
        day = min(day_hi, last) if day_hi >= 27 else day_lo + 2
        d = pd.Timestamp(year=m.year, month=m.month, day=day)
        while d.weekday() >= 5:
            d -= pd.Timedelta(days=1)
        out.append(d)
    return out


def make(start="2023-01-02", end="2026-09-30", seed=7, carry=0.065, s0=5800.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, end)
    spot = s0 * np.exp(np.cumsum(rng.normal(0.0004, 0.009, len(days))))
    exp = {"GOLDM": _expiries(days[0], days[-1], 3, 5)}
    for s in ("GOLDTEN", "GOLDGUINEA", "GOLDPETAL"):
        exp[s] = _expiries(days[0], days[-1], 27, 31)
    noise_sd = {"GOLDM": 0.0003, "GOLDTEN": 0.0006, "GOLDGUINEA": 0.0012, "GOLDPETAL": 0.0012}
    vol_base = {"GOLDM": 20000, "GOLDTEN": 3000, "GOLDGUINEA": 800, "GOLDPETAL": 1500}
    state = {s: 0.0 for s in SPECS}
    rows = []
    for i, d in enumerate(days):
        for sym, spec in SPECS.items():
            state[sym] = 0.85 * state[sym] + rng.normal(0, noise_sd[sym])  # mean-reverting mispricing
            live = [e for e in exp[sym] if e >= d][:3]
            for k, e in enumerate(live):
                t = (e - d).days / 365
                fine = spot[i] * np.exp(carry * t + state[sym])
                quote = fine * spec.quote_g * spec.fine_factor
                close = round(quote, 0)
                vol = max(0, int(rng.lognormal(np.log(vol_base[sym] / (1 + 3 * k)), 0.6)))
                if rng.random() < (0.08 if sym in ("GOLDGUINEA", "GOLDPETAL") else 0.01):
                    vol = 0  # thin / no-trade days
                rows.append({"date": d.date(), "symbol": sym, "expiry": e.date(), "open": close, "high": close,
                             "low": close, "close": close, "volume": vol, "oi": vol * 3 + 10})
    return finalize(pd.DataFrame(rows))
