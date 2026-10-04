"""Normalisation, implied carry, term structure and pair spreads."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .specs import SPECS, PAIRS


def add_fine_price(df: pd.DataFrame) -> pd.DataFrame:
    """Rupees per gram of fine (pure) gold: quote / grams-per-quote / (purity/1000)."""
    df = df.copy()
    q = df["symbol"].map(lambda s: SPECS[s].quote_g)
    f = df["symbol"].map(lambda s: SPECS[s].fine_factor)
    df["fine_px"] = df["close"] / q / f
    return df


def tradable(df: pd.DataFrame, min_volume: float = 1, min_oi: float = 1, tender_buffer_days: int = 6) -> pd.Series:
    """A row is usable only if it actually traded, has open interest and is safely
    before the tender/delivery period (approximated as `tender_buffer_days` before expiry)."""
    return (df["volume"] >= min_volume) & (df["oi"] >= min_oi) & (df["dte"] > tender_buffer_days)


def implied_carry(df: pd.DataFrame, symbol: str = "GOLDM", **filt) -> pd.Series:
    """Annualised carry implied by the two nearest usable expiries of one product:
    r = ln(F_far / F_near) / ((T_far - T_near) / 365). Uses only same-day prices."""
    d = df[(df["symbol"] == symbol) & tradable(df, **filt)].sort_values(["date", "expiry"])
    out = {}
    for dt, g in d.groupby("date"):
        if len(g) < 2:
            continue
        n, f = g.iloc[0], g.iloc[1]
        dt_years = (f["expiry"] - n["expiry"]).days / 365.0
        if dt_years <= 0:
            continue
        out[dt] = np.log(f["fine_px"] / n["fine_px"]) / dt_years
    s = pd.Series(out, name="carry").sort_index()
    # carry is a slow variable: smooth with a trailing median (past data only)
    return s.rolling(10, min_periods=1).median()


def term_structure(df: pd.DataFrame, on: pd.Timestamp) -> pd.DataFrame:
    """All contracts on one day, normalised, with annualised carry vs that product's nearest expiry."""
    d = df[df["date"] == on].sort_values(["symbol", "expiry"]).copy()
    rows = []
    for sym, g in d.groupby("symbol"):
        near = g.iloc[0]
        for _, r in g.iterrows():
            yrs = (r["expiry"] - near["expiry"]).days / 365.0
            rows.append({
                "symbol": sym, "expiry": r["expiry"].date(), "dte": r["dte"], "fine_px": r["fine_px"],
                "volume": r["volume"], "oi": r["oi"],
                "carry_vs_near_%": (np.log(r["fine_px"] / near["fine_px"]) / yrs * 100) if yrs > 0 else np.nan,
            })
    return pd.DataFrame(rows)


def front_contract(df: pd.DataFrame, symbol: str, **filt) -> pd.DataFrame:
    """For each date, the nearest-expiry usable contract of `symbol` (expiry kept, not stitched)."""
    d = df[(df["symbol"] == symbol) & tradable(df, **filt)].sort_values(["date", "expiry"])
    return d.groupby("date").head(1).set_index("date")


def pair_spread(df: pd.DataFrame, pair: str, carry: pd.Series, **filt) -> pd.DataFrame:
    """Carry-adjusted log spread between the front usable contracts of a pair.

    spread = ln(P_A) - ln(P_B) - r * (T_A - T_B)/365
    where P are fine-gold prices and r the market-implied carry. A positive spread
    means A is rich relative to B after adjusting for the different expiry dates."""
    a, b, _, _ = PAIRS[pair]
    fa, fb = front_contract(df, a, **filt), front_contract(df, b, **filt)
    j = fa[["expiry", "fine_px", "close", "volume", "oi", "dte"]].join(
        fb[["expiry", "fine_px", "close", "volume", "oi", "dte"]], lsuffix="_a", rsuffix="_b", how="inner")
    j = j.join(carry, how="left")
    j["carry"] = j["carry"].ffill()
    j = j.dropna(subset=["carry"])
    dt_years = (j["expiry_a"] - j["expiry_b"]).dt.days / 365.0
    j["raw_spread"] = np.log(j["fine_px_a"] / j["fine_px_b"])
    j["spread"] = j["raw_spread"] - j["carry"] * dt_years
    j["pair"] = pair
    return j
