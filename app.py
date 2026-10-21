"""AuLens dashboard — run with:  streamlit run app.py"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aulens import analytics as an, backtest as bt, ingest, synthetic
from aulens.alerts import latest_alerts
from aulens.costs import CostModel
from aulens.specs import PAIRS, SPECS

st.set_page_config(page_title="AuLens · MCX Gold", layout="wide")
RAW = Path(__file__).parent / "data" / "raw"
PACKED = Path(__file__).parent / "data" / "gold_futures_2025-10_2026-10.csv"


@st.cache_data(show_spinner="Loading Bhavcopy data…")
def load(source: str):
    log = []
    if source == "Bhavcopy files (data/raw)":
        df = ingest.load_folder(RAW, log)
        if df.empty and PACKED.exists():  # no raw files (e.g. on Streamlit Cloud): use the packed gold-only extract
            df = ingest.finalize(pd.read_csv(PACKED, parse_dates=["date", "expiry"]))
            log.append(f"Loaded {PACKED.name} (gold futures rows extracted from MCX Bhavcopy).")
    else:
        df = synthetic.make()
        log.append("SYNTHETIC demo data — for testing the pipeline only. Results say nothing about real MCX prices.")
    return an.add_fine_price(df), log


@st.cache_data(show_spinner="Running walk-forward backtest…")
def walk(pair, source, hurdle_mult, tender_buffer):
    df, _ = load(source)
    base = bt.Params(hurdle_mult=hurdle_mult, tender_buffer=tender_buffer)
    sp = an.pair_spread(df, pair, an.implied_carry(df), tender_buffer_days=tender_buffer + base.max_hold + 3)
    return bt.walk_forward(sp, df, pair, CostModel(), base, train_months=3, test_months=1, holdout_months=3, min_trades=1)


RUPEE_COLS = {"gross", "costs", "net", "train_net", "test_net"}
PRICE_COLS = {"fine_px", "ea", "eb", "xa", "xb"}


def show_table(d: pd.DataFrame, **kw):
    """Dataframe for display: dates without 00:00:00, ₹ to whole rupees, other floats to 2 dp, blanks for missing."""
    d = d.copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.date
    fmt = {c: ("{:,.0f}" if c in RUPEE_COLS else "{:,.2f}" if c in PRICE_COLS else "{:.2f}")
           for c in d.columns if pd.api.types.is_float_dtype(d[c])}
    for c, f in list(fmt.items()):  # Streamlit shows NaN as "None" even with na_rep, so pre-format those columns
        if d[c].isna().any():
            d[c] = d[c].map(lambda v, f=f: "" if pd.isna(v) else f.format(v))
            del fmt[c]
    st.dataframe(d.style.format(fmt), hide_index=True, width="stretch", **kw)


st.title("AuLens — MCX gold relative-value intelligence")
st.caption("Hack in Hills '26 · PS 03 · TeamAlpha")

with st.sidebar:
    have_raw = any(RAW.glob("*.csv")) or PACKED.exists()
    source = st.radio("Data source", ["Bhavcopy files (data/raw)", "Synthetic demo"], index=0 if have_raw else 1)
    pair = st.selectbox("Pair", list(PAIRS))
    hurdle = st.slider("Cost hurdle multiple", 1.0, 3.0, 1.5, 0.25,
                       help="A gap must exceed this multiple of the expected round-trip cost")
    tender = st.slider("Days before expiry treated as no-go", 3, 10, 6)
    st.markdown(f"Statutory cost per leg round trip: **{CostModel().round_trip_statutory_bps():.2f} bps** "
                "(before brokerage and slippage)")

df, log = load(source)
banner = st.container()  # always present, so the tabs below keep their place (and selection) when the source changes
if source == "Synthetic demo":
    banner.warning(log[0])
if df.empty:
    st.error("No data. Put daily Bhavcopy CSVs in data/raw/ (see README) or switch to the synthetic demo.")
    st.stop()

carry = an.implied_carry(df, tender_buffer_days=tender)
spreads = {p: an.pair_spread(df, p, carry, tender_buffer_days=tender) for p in PAIRS}

t1, t2, t3, t4, t5 = st.tabs(["Today", "Normalised prices", "Term structure", "Backtest", "Data quality"], key="main_tabs")

with t1:
    st.subheader("Alerts — quiet unless every gate passes")
    al = latest_alerts(spreads, bt.Params(hurdle_mult=hurdle, tender_buffer=tender), CostModel())
    fired = al[al["alert"] != "quiet"]
    if fired.empty:
        st.success("No meaningful signal today. Every gap is either small, inside costs, or too close to tender.")
    else:
        for _, r in fired.iterrows():
            st.error(f"**{r['pair']}**: {r['alert']} · z = {r['z']} · gap {r['gap_bps']} bps vs cost {r['cost_bps']} bps")
    show_table(al)

    sp = bt.add_zscore(spreads[pair], 40)
    fig = go.Figure()
    fig.add_scatter(x=sp.index, y=sp["raw_spread"] * 1e4, name="raw spread", line=dict(color="#B0B7C0"))
    fig.add_scatter(x=sp.index, y=sp["spread"] * 1e4, name="carry-adjusted spread", line=dict(color="#B8860B"))
    fig.update_layout(title=f"{pair}: spread in basis points (A vs B, fine-gold terms)", yaxis_title="bps",
                      height=380, margin=dict(t=50, b=20), legend_title_text="series")
    st.plotly_chart(fig, width="stretch")

with t2:
    st.subheader("Rupees per gram of fine gold, front usable contract of each product")
    fr = pd.concat({s: an.front_contract(df, s, tender_buffer_days=tender)["fine_px"] for s in SPECS}, axis=1)
    st.plotly_chart(px.line(fr, labels={"value": "₹ per g fine", "date": "", "variable": "product"}, height=420), width="stretch")
    st.caption("fine price = quote ÷ grams per quote ÷ (purity ÷ 1000). Each line follows real contracts by expiry; "
               "when the front contract rolls, the line moves to the next expiry rather than being stitched.")

with t3:
    st.subheader("Implied carry and today's curve")
    cfig = px.line(carry * 100, labels={"value": "annualised carry, %", "index": "", "date": ""},
                   title="Carry implied by the two nearest GOLDM expiries", height=320)
    cfig.update_layout(showlegend=False)
    st.plotly_chart(cfig, width="stretch")
    on = st.select_slider("Curve date", options=list(df["date"].drop_duplicates().sort_values()), value=df["date"].max(),
                          format_func=lambda d: d.strftime("%d %b %Y"))
    ts = an.term_structure(df, on)
    st.plotly_chart(px.line(ts, x="dte", y="fine_px", color="symbol", markers=True,
                            labels={"dte": "days to expiry", "fine_px": "₹ per g fine", "symbol": "product"}, height=360),
                    width="stretch")
    show_table(ts)

with t4:
    st.subheader(f"Walk-forward backtest · {pair}")
    st.caption("Params chosen on the previous 3 months only, traded on the next month. "
               "The last 3 months are a holdout traded once. Fills at next-day prices, full costs and slippage.")
    folds, trades, hold = walk(pair, source, hurdle, tender)
    s = bt.summary(trades)
    days = df["date"].nunique()
    head = (f"**{days} trading days** of {'synthetic' if source == 'Synthetic demo' else 'MCX Bhavcopy'} data "
            f"({df['date'].min():%d %b %Y} – {df['date'].max():%d %b %Y}). ")
    if s["trades"]:
        head += f"Out of sample, {pair} took **{s['trades']} trades** for **₹{s['net_rs']:,.0f} net after costs**. "
    head += f"Verdict: {s['verdict']}"
    meaningful = s["trades"] and s["verdict"].startswith("Positive and statistically meaningful")
    (st.success if meaningful else st.info)(head)
    if s["trades"]:
        c = st.columns(5)
        c[0].metric("Trades", s["trades"])
        c[1].metric("Gross ₹", f"{s['gross_rs']:,.0f}")
        c[2].metric("Costs ₹", f"{s['costs_rs']:,.0f}")
        c[3].metric("Net ₹", f"{s['net_rs']:,.0f}")
        c[4].metric("t-stat (net)", f"{s['t_stat_net']:.2f}")
        eq = trades.sort_values("exit_date").assign(cum=lambda x: x["net"].cumsum())
        st.plotly_chart(px.line(eq, x="exit_date", y="cum", color="segment", markers=True,
                                labels={"cum": "cumulative net ₹", "exit_date": "", "segment": "sample"}, height=340),
                        width="stretch")
        a, b, la, lb = PAIRS[pair]
        grams = la * SPECS[a].lot_g
        _, daily = bt.run(spreads[pair], df, pair, bt.Params(hurdle_mult=hurdle, tender_buffer=tender), CostModel())
        gold = an.front_contract(df, "GOLDM", tender_buffer_days=tender)["fine_px"]
        attr = bt.gold_attribution(daily, gold, grams)
        st.markdown(f"**Gold exposure check:** β = {attr['beta']:.3f} (t = {attr['t_beta']:.2f}) against holding "
                    f"{grams:g} g of gold. β near 0 means the P&L is the spread, not gold's price move.")
        show_table(trades)
    st.markdown("**Walk-forward folds**")
    show_table(folds)
    st.markdown(f"**Holdout** — last 3 months from {hold['holdout_start']:%d %b %Y}, traded once with settings "
                "chosen on everything before")
    h = st.columns(4)
    h[0].metric("Lookback (days)", hold["lookback"])
    h[1].metric("Entry z", f"{hold['entry_z']:g}")
    h[2].metric("Trades", hold["trades"])
    h[3].metric("Net ₹", f"{hold['net']:,.0f}")

with t5:
    st.subheader("Validation log")
    st.markdown("\n".join(f"- {m}" for m in (log or ["No issues found."])))
    st.markdown(f"**{df['date'].nunique()} trading days**, {df['date'].min():%d %b %Y} – {df['date'].max():%d %b %Y}")
    show_table(df.groupby("symbol").agg(rows=("close", "size"), first=("date", "min"), last=("date", "max"),
                                        zero_volume_days=("volume", lambda v: int((v == 0).sum()))).reset_index())
