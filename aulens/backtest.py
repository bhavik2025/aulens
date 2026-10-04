"""Walk-forward backtest of cross-contract spread trades.

Rules that keep it honest:
  * decisions use data up to day t only; fills happen at day t+1 prices
  * the contracts actually entered are held to exit (no switching to a new front month)
  * positions are closed before the tender period
  * costs + slippage are charged on every leg
  * parameters are chosen on past data only (walk-forward); a final holdout is never used to choose them
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product

import numpy as np
import pandas as pd

from .costs import CostModel
from .specs import SPECS, PAIRS


@dataclass
class Params:
    lookback: int = 40        # days of spread history for mean / std
    entry_z: float = 2.0
    exit_z: float = 0.5
    max_hold: int = 10        # trading days
    tender_buffer: int = 6    # calendar days before expiry treated as no-go
    hurdle_mult: float = 1.5  # gap must exceed hurdle_mult x expected round-trip cost


def add_zscore(sp: pd.DataFrame, lookback: int) -> pd.DataFrame:
    sp = sp.copy()
    past = sp["spread"].shift(1)  # strictly past data
    sp["mu"] = past.rolling(lookback, min_periods=max(10, lookback // 2)).mean()
    sp["sd"] = past.rolling(lookback, min_periods=max(10, lookback // 2)).std()
    sp["z"] = (sp["spread"] - sp["mu"]) / sp["sd"]
    return sp


def _price(df_idx, d, sym, exp):
    try:
        return float(df_idx.loc[(d, sym, exp), "close"])
    except KeyError:
        return None


def expected_cost_frac(pair: str, ref_px: dict, cm: CostModel) -> float:
    """Round-trip cost of the pair trade as a fraction of one leg's notional."""
    a, b, la, lb = PAIRS[pair]
    na = ref_px[a] * SPECS[a].lot_multiplier() * la
    nb = ref_px[b] * SPECS[b].lot_multiplier() * lb
    c = sum(cm.side_cost(na, s, a) for s in ("buy", "sell"))
    c += sum(cm.side_cost(nb, s, b) for s in ("buy", "sell"))
    # brokerage is per order; with several lots it is still one order per leg per side
    return c / ((na + nb) / 2)


def run(sp: pd.DataFrame, df: pd.DataFrame, pair: str, p: Params, cm: CostModel,
        start=None, end=None) -> tuple[pd.DataFrame, pd.Series]:
    """Simulate one parameter set. Entries are allowed only when the decision date is in [start, end)."""
    a, b, la, lb = PAIRS[pair]
    ma, mb = SPECS[a].lot_multiplier() * la, SPECS[b].lot_multiplier() * lb
    sp = add_zscore(sp, p.lookback)
    dates = list(sp.index)
    df_idx = df.set_index(["date", "symbol", "expiry"]).sort_index()
    trades, daily = [], pd.Series(0.0, index=sp.index)
    pos = None
    for i, t in enumerate(dates[:-1]):
        nxt = dates[i + 1]
        row = sp.loc[t]
        if pos is not None:
            pa, pb = _price(df_idx, t, a, pos["exp_a"]), _price(df_idx, t, b, pos["exp_b"])
            if pa is not None and pb is not None:
                daily[t] += pos["side"] * ((pa - pos["last_a"]) * ma - (pb - pos["last_b"]) * mb)
                pos["last_a"], pos["last_b"] = pa, pb
            held = i - pos["i"]
            dte = min((pos["exp_a"] - t).days, (pos["exp_b"] - t).days)
            z_now = np.nan
            if pa is not None and pb is not None and not np.isnan(row["mu"]):
                fa = pa / SPECS[a].quote_g / SPECS[a].fine_factor
                fb = pb / SPECS[b].quote_g / SPECS[b].fine_factor
                s_now = np.log(fa / fb) - row["carry"] * (pos["exp_a"] - pos["exp_b"]).days / 365
                z_now = (s_now - row["mu"]) / row["sd"]
            reason = None
            if dte <= p.tender_buffer + 3:
                reason = "tender"
            elif held >= p.max_hold:
                reason = "time"
            elif not np.isnan(z_now) and abs(z_now) <= p.exit_z:
                reason = "converged"
            if reason:
                xa, xb = _price(df_idx, nxt, a, pos["exp_a"]), _price(df_idx, nxt, b, pos["exp_b"])
                if xa is None or xb is None:
                    continue  # cannot exit without a price; try again next day
                gross = pos["side"] * ((xa - pos["ea"]) * ma - (xb - pos["eb"]) * mb)
                daily[nxt] += pos["side"] * ((xa - pos["last_a"]) * ma - (xb - pos["last_b"]) * mb)
                na_x, nb_x = xa * ma, xb * mb
                cost = pos["entry_cost"] + cm.side_cost(na_x, "sell" if pos["side"] > 0 else "buy", a) \
                    + cm.side_cost(nb_x, "buy" if pos["side"] > 0 else "sell", b)
                daily[nxt] -= cost - pos["entry_cost"]
                trades.append({**{k: pos[k] for k in ("entry_date", "side", "exp_a", "exp_b", "ea", "eb", "z_entry")},
                               "exit_date": nxt, "xa": xa, "xb": xb, "gross": gross, "costs": cost,
                               "net": gross - cost, "days": held + 1, "exit_reason": reason})
                pos = None
            continue

        # flat: look for an entry
        if start is not None and t < start or end is not None and t >= end:
            continue
        if np.isnan(row.get("z", np.nan)):
            continue
        if min(row["dte_a"], row["dte_b"]) <= p.tender_buffer + p.max_hold + 3:
            continue
        cost_frac = expected_cost_frac(pair, {a: row["close_a"], b: row["close_b"]}, cm)
        gap = abs(row["spread"] - row["mu"])
        if abs(row["z"]) < p.entry_z or gap < p.hurdle_mult * cost_frac:
            continue
        ea, eb = _price(df_idx, nxt, a, row["expiry_a"]), _price(df_idx, nxt, b, row["expiry_b"])
        if ea is None or eb is None:
            continue
        side = -1 if row["z"] > 0 else 1  # A rich -> short A / long B
        entry_cost = cm.side_cost(ea * ma, "buy" if side > 0 else "sell", a) + \
            cm.side_cost(eb * mb, "sell" if side > 0 else "buy", b)
        daily[nxt] -= entry_cost
        pos = {"entry_date": nxt, "i": i + 1, "side": side, "exp_a": row["expiry_a"], "exp_b": row["expiry_b"],
               "ea": ea, "eb": eb, "last_a": ea, "last_b": eb, "entry_cost": entry_cost, "z_entry": row["z"]}
    return pd.DataFrame(trades), daily


GRID = {"lookback": [20, 40, 60], "entry_z": [1.5, 2.0, 2.5]}


def walk_forward(sp, df, pair, cm: CostModel, base: Params = Params(), train_months=12, test_months=3,
                 holdout_months=6, min_trades=3):
    """Pick params on each training window, trade the next test window with them.
    The last `holdout_months` are only traded once, with params chosen on all earlier data."""
    idx = sp.index
    first, last = idx.min(), idx.max()
    holdout_start = last - pd.DateOffset(months=holdout_months)
    folds, oos_trades, oos_daily = [], [], []

    def choose(train_start, train_end):
        best, best_net = None, -np.inf
        for lb, ez in product(GRID["lookback"], GRID["entry_z"]):
            p = Params(**{**asdict(base), "lookback": lb, "entry_z": ez})
            tr, _ = run(sp, df, pair, p, cm, train_start, train_end)
            net = tr["net"].sum() if len(tr) >= min_trades else -np.inf
            if net > best_net:
                best, best_net = p, net
        return best or base, best_net

    test_start = first + pd.DateOffset(months=train_months)
    busy_until = first  # one position at a time: a fold may not open a trade while the last one is still open
    while test_start < holdout_start:
        test_end = min(test_start + pd.DateOffset(months=test_months), holdout_start)
        p, train_net = choose(test_start - pd.DateOffset(months=train_months), test_start)
        tr, daily = run(sp, df, pair, p, cm, max(test_start, busy_until), test_end)
        if len(tr):
            busy_until = tr["exit_date"].max() + pd.Timedelta(days=1)
        folds.append({"test_start": test_start.date(), "test_end": test_end.date(), "lookback": p.lookback,
                      "entry_z": p.entry_z, "train_net": train_net, "test_trades": len(tr),
                      "test_net": tr["net"].sum() if len(tr) else 0.0})
        oos_trades.append(tr.assign(segment="walk-forward"))
        oos_daily.append(daily[(daily.index >= test_start) & (daily.index < test_end + pd.Timedelta(days=30))])
        test_start = test_end

    p_h, _ = choose(first, holdout_start)
    tr_h, daily_h = run(sp, df, pair, p_h, cm, max(holdout_start, busy_until), None)
    hold = {"holdout_start": holdout_start.date(), "lookback": p_h.lookback, "entry_z": p_h.entry_z,
            "trades": len(tr_h), "net": tr_h["net"].sum() if len(tr_h) else 0.0}
    trades = pd.concat([t for t in oos_trades + [tr_h.assign(segment="holdout")] if len(t)], ignore_index=True) \
        if any(len(t) for t in oos_trades + [tr_h]) else pd.DataFrame()
    return pd.DataFrame(folds), trades, hold


def gold_attribution(daily_pnl: pd.Series, gold_fine_px: pd.Series, grams: float) -> dict:
    """Regress daily strategy P&L on the P&L of simply holding `grams` of gold.
    beta ~ 0 means the result is not just gold moving."""
    g = gold_fine_px.reindex(daily_pnl.index).ffill().diff() * grams
    d = pd.concat([daily_pnl, g], axis=1, keys=["pnl", "gold"]).dropna()
    d = d[(d["pnl"] != 0) | (d["gold"] != 0)]
    if len(d) < 10 or d["gold"].var() == 0:
        return {"beta": np.nan, "t_beta": np.nan, "alpha_per_day": np.nan, "n": len(d)}
    X = np.column_stack([np.ones(len(d)), d["gold"].values])
    coef, res, *_ = np.linalg.lstsq(X, d["pnl"].values, rcond=None)
    resid = d["pnl"].values - X @ coef
    s2 = resid @ resid / max(len(d) - 2, 1)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return {"beta": coef[1], "t_beta": coef[1] / se[1] if se[1] else np.nan, "alpha_per_day": coef[0], "n": len(d)}


MIN_TRADES_FOR_VERDICT = 10


def summary(trades: pd.DataFrame) -> dict:
    if trades is None or not len(trades):
        return {"trades": 0, "verdict": "No trades passed the cost and liquidity gates."}
    net = trades["net"]
    out = {"trades": len(trades), "gross_rs": trades["gross"].sum(), "costs_rs": trades["costs"].sum(),
           "net_rs": net.sum(), "hit_rate": (net > 0).mean(), "avg_net_rs": net.mean(),
           "t_stat_net": net.mean() / (net.std(ddof=1) / np.sqrt(len(net))) if len(net) > 1 and net.std() > 0 else np.nan}
    t = out["t_stat_net"]
    if len(net) < MIN_TRADES_FOR_VERDICT:
        out["verdict"] = (f"Too few trades to judge ({len(net)} < {MIN_TRADES_FOR_VERDICT}); "
                          "net is " + ("positive" if out["net_rs"] > 0 else "not positive") + " but proves nothing yet.")
    elif out["net_rs"] <= 0:
        out["verdict"] = "No edge after costs: gross gains are consumed by fees and slippage."
    elif np.isnan(t) or t < 2:
        out["verdict"] = "Positive but not statistically reliable (t < 2): treat as no proven edge."
    else:
        out["verdict"] = "Positive and statistically meaningful out-of-sample edge after costs."
    return out
