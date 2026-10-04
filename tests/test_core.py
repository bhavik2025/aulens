from datetime import date

import numpy as np
import pandas as pd
import pytest

from aulens import ingest, analytics as an, backtest as bt, synthetic
from aulens.costs import CostModel


def test_date_formats():
    assert ingest.parse_response_date("09/04/2026") == date(2026, 9, 4)       # MM/DD/YYYY
    assert ingest.parse_expiry("04SEP2026") == date(2026, 9, 4)
    assert ingest.format_request_date(date(2026, 9, 4)) == "04/09/2026"       # DD/MM/YYYY


def _raw(day="09/04/2026"):
    return pd.DataFrame({
        "Symbol": ["  GOLDM ", "GOLDPETAL", "CRUDEOIL"], "Date": [day] * 3,
        "ExpiryDate": ["05OCT2026", "30SEP2026", "19SEP2026"],
        "Open": [1, 1, 1], "High": [1, 1, 1], "Low": [1, 1, 1], "Close": [100000, 10050, 5000],
        "Volume": [10, 5, 1], "OpenInterest": [100, 50, 10]})


def test_clean_keeps_gold_and_trims_symbols():
    df = ingest.clean_frame(_raw(), requested=date(2026, 9, 4))
    assert sorted(df["symbol"]) == ["GOLDM", "GOLDPETAL"]


def test_holiday_fallback_is_rejected():
    log = []
    df = ingest.clean_frame(_raw("09/03/2026"), requested=date(2026, 9, 4), log=log)
    assert df.empty and "rejected" in log[0]


def test_fine_price_normalisation():
    df = ingest.finalize(ingest.clean_frame(_raw()))
    df = an.add_fine_price(df).set_index("symbol")
    assert df.loc["GOLDM", "fine_px"] == pytest.approx(100000 / 10 / 0.995)
    assert df.loc["GOLDPETAL", "fine_px"] == pytest.approx(10050 / 1 / 0.999)


def test_statutory_cost_per_leg():
    # 2x0.0021% + 0.01% + 0.002% + 2x0.0001% + 18% GST on (exchange + SEBI) = 1.719 bps
    assert CostModel().round_trip_statutory_bps() == pytest.approx(1.7192, abs=1e-3)


def test_zscore_has_no_lookahead():
    idx = pd.bdate_range("2025-01-01", periods=120)
    sp = pd.DataFrame({"spread": np.random.default_rng(0).normal(0, 1e-3, 120)}, index=idx)
    z1 = bt.add_zscore(sp, 40)["z"]
    sp2 = sp.copy()
    sp2.iloc[80:, 0] += 0.05  # change the future
    z2 = bt.add_zscore(sp2, 40)["z"]
    pd.testing.assert_series_equal(z1.iloc[:80], z2.iloc[:80])


def test_backtest_runs_and_closes_before_tender():
    df = an.add_fine_price(synthetic.make(start="2024-01-01", end="2024-12-31"))
    sp = an.pair_spread(df, "GOLDM/GOLDTEN", an.implied_carry(df))
    trades, _ = bt.run(sp, df, "GOLDM/GOLDTEN", bt.Params(lookback=20), CostModel())
    if len(trades):
        days_left = np.minimum((trades["exp_a"] - trades["exit_date"]).dt.days,
                               (trades["exp_b"] - trades["exit_date"]).dt.days)
        assert (days_left > 0).all()
        assert (trades["costs"] > 0).all()
