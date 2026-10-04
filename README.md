# AuLens — MCX Gold Relative-Value Intelligence

**Hack in Hills '26 · PS 03 Commodity Derivatives Intelligence · TeamAlpha**

MCX lists four small gold futures: GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL. They are all gold, so after adjusting for size, quote unit, purity and expiry date their prices should almost match. AuLens measures the gaps between them, tests on unseen history whether trading those gaps pays after costs, and says so plainly if it does not.

## What it does

| Module | File | What it handles |
|---|---|---|
| Ingest & validate | `aulens/ingest.py` | Date-mismatch rejection (holiday fallback), DD/MM vs MM/DD formats, `04SEP2026` expiries, padded symbols, de-dupe, per-expiry tracking |
| Normalise | `aulens/analytics.py` | ₹ per gram of fine gold = quote ÷ grams per quote ÷ (purity ÷ 1000) |
| Carry & term structure | `aulens/analytics.py` | Carry implied by the two nearest GOLDM expiries; spreads adjusted for different expiry dates |
| Signal | `aulens/backtest.py`, `aulens/alerts.py` | Rolling z-score on past data only; fires only if the gap beats expected costs, both legs are liquid and the trade fits before tender |
| Backtest | `aulens/backtest.py` | Walk-forward (12-month train → 3-month test), final 6-month holdout, next-day fills, held contracts kept to exit, close before tender |
| Costs | `aulens/costs.py` | Exchange charge, CTT, stamp duty, SEBI fee, GST, brokerage, liquidity-scaled slippage |
| Attribution | `aulens/backtest.py` | Daily P&L regressed on holding the same grams of gold → β near 0 = spread return, not gold's move |
| Dashboard | `app.py` | Today's alerts (quiet by default), normalised prices, term structure, backtest, data-quality log |

## Pairs and equal-gram hedges

| Pair | Hedge |
|---|---|
| GOLDM / GOLDTEN | 1 : 10 (100 g each side) |
| GOLDM / GOLDPETAL | 1 : 100 |
| GOLDTEN / GOLDGUINEA | 4 : 5 (40 g) |
| GOLDTEN / GOLDPETAL | 1 : 10 |
| GOLDGUINEA / GOLDPETAL | 1 : 8 |
| GOLDM / GOLDGUINEA | 2 : 25 (200 g) |

GOLDM is 995 purity and the rest are 999, so an equal-gram hedge leaves about 0.4% of gold exposure. The attribution step measures it.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                 # 7 tests: formats, holiday rejection, normalisation, costs, no look-ahead, tender exit
streamlit run app.py
```

With no files in `data/raw/`, the app runs on **synthetic demo data**. That data only tests the pipeline and is labelled as such everywhere. It says nothing about real MCX prices.

## Getting real data

1. Open the MCX Bhavcopy page: https://www.mcxindia.com/market-data/bhavcopy
2. Pick a date and download the day's file as CSV.
3. Save it as `data/raw/YYYY-MM-DD.csv` using the date you **requested**. The loader rejects any rows whose `Date` differs from the requested date, which catches the holiday fallback.
4. Repeat for the history you need. Track GOLDTEN only from its April 2025 listing.

To automate it, open the page with your browser's developer tools, watch the network request made when you pick a date, and put that call in a small `fetch.py` that writes the same `YYYY-MM-DD.csv` files. Keep it polite: one request per date, with a pause between requests.

Column names are matched loosely (`Symbol`, `Date`, `ExpiryDate`, `Open`, `High`, `Low`, `Close`, `Volume`, `OpenInterest`). If the export uses different headers, add them to `ALIASES` in `aulens/ingest.py`.

## Honest-result rules

- A positive net P&L with t < 2 is reported as **no proven edge**.
- Settlement prices are not fill prices, so entries and exits use the next day's price plus slippage.
- Volume is not depth: zero-volume and zero-OI days are skipped.
- Costs are statutory rates as published by brokers (2025–26). Re-check them before final numbers.

## Structure

```
aulens/        core package (specs, ingest, analytics, costs, backtest, alerts, synthetic)
app.py         Streamlit dashboard
tests/         pytest suite
docs/          methodology and submission checklist
data/raw/      put Bhavcopy CSVs here (git-ignored)
```
