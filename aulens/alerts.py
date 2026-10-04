"""Quiet alerts: speak only when a gap is large, liquid, inside the calendar and beats costs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import Params, add_zscore, expected_cost_frac
from .costs import CostModel
from .specs import PAIRS


def latest_alerts(spreads: dict[str, pd.DataFrame], params: Params, cm: CostModel) -> pd.DataFrame:
    rows = []
    for pair, sp in spreads.items():
        if len(sp) < params.lookback:
            continue
        a, b, _, _ = PAIRS[pair]
        r = add_zscore(sp, params.lookback).iloc[-1]
        cost = expected_cost_frac(pair, {a: r["close_a"], b: r["close_b"]}, cm)
        gap = abs(r["spread"] - r["mu"]) if not np.isnan(r["mu"]) else np.nan
        checks = {
            "big_enough": abs(r["z"]) >= params.entry_z if not np.isnan(r["z"]) else False,
            "beats_costs": gap >= params.hurdle_mult * cost if not np.isnan(gap) else False,
            "in_calendar": min(r["dte_a"], r["dte_b"]) > params.tender_buffer + params.max_hold + 3,
        }
        fire = all(checks.values())
        rows.append({"pair": pair, "date": sp.index[-1].date(), "z": round(r["z"], 2),
                     "gap_bps": round(gap * 1e4, 1), "cost_bps": round(cost * 1e4, 1), **checks,
                     "alert": (f"{a} rich vs {b}" if r["z"] > 0 else f"{a} cheap vs {b}") if fire else "quiet"})
    return pd.DataFrame(rows)
