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


@st.cache_data(show_spinner="Loading Bhavcopy data…")
def load(source: str):
    log = []
    if source == "Bhavcopy files (data/raw)":
        df = ingest.load_folder(RAW, log)
    else:
        df = synthetic.make()
        log.append("SYNTHETIC demo data — for testing the pipeline only. Results say nothing about real MCX prices.")
    return an.add_fine_price(df), log


@st.cache_data(show_spinner="Running walk-forward backtest…")
def walk(pair, source, hurdle_mult, tender_buffer):
    df, _ = load(source)
    sp = an.pair_spread(df, pair, an.implied_carry(df), tender_buffer_days=tender_buffer)
    base = bt.Params(hurdle_mult=hurdle_mult, tender_buffer=tender_buffer)
    return bt.walk_forward(sp, df, pair, CostModel(), base)


st.title("AuLens — MCX gold relative-value intelligence")
st.caption("Hack in Hills '26 · PS 03 · TeamAlpha")

with st.sidebar:
    have_raw = any(RAW.glob("*.csv"))
    source = st.radio("Data source", ["Bhavcopy files (data/raw)", "Synthetic demo"], index=0 if have_raw else 1)
    pair = st.selectbox("Pair", list(PAIRS))
    hurdle = st.slider("Cost hurdle multiple", 1.0, 3.0, 1.5, 0.25,
                       help="A gap must exceed this multiple of the expected round-trip cost")
    tender = st.slider("Days before expiry treated as no-go", 3, 10, 6)
    st.markdown(f"Statutory cost per leg round trip: **{CostModel().round_trip_statutory_bps():.2f} bps** "
                "(before brokerage and slippage)")

df, log = load(source)
if source == "Synthetic demo":
    st.warning(log[0])
if df.empty:
    st.error("No data. Put daily Bhavcopy CSVs in data/raw/ (see README) or switch to the synthetic demo.")
    st.stop()

carry = an.implied_carry(df, tender_buffer_days=tender)
spreads = {p: an.pair_spread(df, p, carry, tender_buffer_days=tender) for p in PAIRS}

t1, t2, t3, t4, t5 = st.tabs(["Today", "Normalised prices", "Term structure", "Backtest", "Data quality"])

with t1:
    st.subheader("Alerts — quiet unless every gate passes")
    al = latest_alerts(spreads, bt.Params(hurdle_mult=hurdle, tender_buffer=tender), CostModel())
    fired = al[al["alert"] != "quiet"]
    if fired.empty:
        st.success("No meaningful signal today. Every gap is either small, inside costs, or too close to tender.")
    else:
        for _, r in fired.iterrows():
            st.error(f"**{r['pair']}**: {r['alert']} · z = {r['z']} · gap {r['gap_bps']} bps vs cost {r['cost_bps']} bps")
    st.dataframe(al, hide_index=True, width="stretch")

    sp = bt.add_zscore(spreads[pair], 40)
    fig = go.Figure()
    fig.add_scatter(x=sp.index, y=sp["raw_spread"] * 1e4, name="raw spread", line=dict(color="#B0B7C0"))
    fig.add_scatter(x=sp.index, y=sp["spread"] * 1e4, name="carry-adjusted spread", line=dict(color="#B8860B"))
    fig.update_layout(title=f"{pair}: spread in basis points (A vs B, fine-gold terms)", yaxis_title="bps",
                      height=380, margin=dict(t=50, b=20))
    st.plotly_chart(fig, width="stretch")

with t2:
    st.subheader("Rupees per gram of fine gold, front usable contract of each product")
    fr = pd.concat({s: an.front_contract(df, s, tender_buffer_days=tender)["fine_px"] for s in SPECS}, axis=1)
    st.plotly_chart(px.line(fr, labels={"value": "₹ per g fine", "date": ""}, height=420), width="stretch")
    st.caption("fine price = quote ÷ grams per quote ÷ (purity ÷ 1000). Each line follows real contracts by expiry; "
               "when the front contract rolls, the line moves to the next expiry rather than being stitched.")

with t3:
    st.subheader("Implied carry and today's curve")
    st.plotly_chart(px.line(carry * 100, labels={"value": "annualised carry, %", "index": ""},
                            title="Carry implied by the two nearest GOLDM expiries", height=320),
                    width="stretch")
    on = st.select_slider("Curve date", options=list(df["date"].drop_duplicates().sort_values()), value=df["date"].max())
    ts = an.term_structure(df, on)
    st.plotly_chart(px.line(ts, x="dte", y="fine_px", color="symbol", markers=True,
                            labels={"dte": "days to expiry", "fine_px": "₹ per g fine"}, height=360),
                    width="stretch")
    st.dataframe(ts, hide_index=True, width="stretch")

with t4:
    st.subheader(f"Walk-forward backtest · {pair}")
    st.caption("Params chosen on the previous 12 months only, traded on the next 3. "
               "The last 6 months are a holdout traded once. Fills at next-day prices, full costs and slippage.")
    folds, trades, hold = walk(pair, source, hurdle, tender)
    s = bt.summary(trades)
    st.info(s["verdict"])
    if s["trades"]:
        c = st.columns(5)
        c[0].metric("Trades", s["trades"])
        c[1].metric("Gross ₹", f"{s['gross_rs']:,.0f}")
        c[2].metric("Costs ₹", f"{s['costs_rs']:,.0f}")
        c[3].metric("Net ₹", f"{s['net_rs']:,.0f}")
        c[4].metric("t-stat (net)", f"{s['t_stat_net']:.2f}")
        eq = trades.sort_values("exit_date").assign(cum=lambda x: x["net"].cumsum())
        st.plotly_chart(px.line(eq, x="exit_date", y="cum", color="segment", markers=True,
                                labels={"cum": "cumulative net ₹", "exit_date": ""}, height=340),
                        width="stretch")
        a, b, la, lb = PAIRS[pair]
        grams = la * SPECS[a].lot_g
        _, daily = bt.run(spreads[pair], df, pair, bt.Params(hurdle_mult=hurdle, tender_buffer=tender), CostModel())
        gold = an.front_contract(df, "GOLDM", tender_buffer_days=tender)["fine_px"]
        attr = bt.gold_attribution(daily, gold, grams)
        st.markdown(f"**Gold exposure check:** β = {attr['beta']:.3f} (t = {attr['t_beta']:.2f}) against holding "
                    f"{grams:g} g of gold. β near 0 means the P&L is the spread, not gold's price move.")
        st.dataframe(trades, hide_index=True, width="stretch")
    st.markdown("**Walk-forward folds**")
    st.dataframe(folds, hide_index=True, width="stretch")
    st.markdown(f"**Holdout:** {hold}")

with t5:
    st.subheader("Validation log")
    st.write(log or ["No issues found."])
    st.dataframe(df.groupby("symbol").agg(rows=("close", "size"), first=("date", "min"), last=("date", "max"),
                                         zero_volume_days=("volume", lambda v: int((v == 0).sum()))),
                 width="stretch")
