# AuLens methodology

## 1. Data

Daily MCX Bhavcopy: Symbol, Date, ExpiryDate, Open, High, Low, Close, Volume, OpenInterest. Every contract is tracked by `(symbol, expiry)`; there is no stitched near-month series.

Validation rules:

- A file is kept only when the returned `Date` equals the requested date (MCX can return the last trading day for a holiday or bad date).
- Response `Date` is parsed as MM/DD/YYYY, `ExpiryDate` as `%d%b%Y` (`04SEP2026`), and symbols are stripped of padding.
- Rows with no close, zero volume or zero open interest are not used for signals.

## 2. Normalisation

```
fine_px (₹ per g of pure gold) = close / grams_per_quote / (purity / 1000)
```

| Contract | Lot | Quoted per | Purity |
|---|---|---|---|
| GOLDM | 100 g | 10 g | 995 |
| GOLDTEN | 10 g | 10 g | 999 |
| GOLDGUINEA | 8 g | 8 g | 999 |
| GOLDPETAL | 1 g | 1 g | 999 |

## 3. Carry and term structure

A futures price sits above spot by the cost of carry: F = S·e^(r·T). Two expiries of the same product give the carry the market implies:

```
r = ln(F_far / F_near) / ((T_far − T_near) / 365)
```

AuLens computes r each day from the two nearest usable GOLDM expiries, then smooths it with a 10-day trailing median.

Roll-down: with r fixed, a contract's price drifts toward spot as expiry approaches. A daily change in ln F splits into a spot move, a change in r (a real curve change), and −r·Δt (mechanical roll-down).

## 4. Spread

For pair (A, B), using each product's nearest usable contract:

```
spread = ln(fine_px_A) − ln(fine_px_B) − r · (T_A − T_B) / 365
```

A positive spread means A is rich against B once the different expiry dates are accounted for.

## 5. Signal

- z = (spread − mean) / std, where mean and std use the previous `lookback` days only (today excluded).
- Enter when |z| ≥ entry_z **and** |spread − mean| ≥ hurdle_mult × expected round-trip cost **and** both legs have more than tender_buffer + max_hold + 3 days to expiry.
- Direction: A rich → short A, long B, in equal grams.
- Exit when |z| ≤ exit_z, after max_hold days, or before the tender period, at the next day's price.

## 6. Costs

| Levy | Rate |
|---|---|
| Exchange transaction charge | 0.0021% each side |
| CTT | 0.01% sell side |
| Stamp duty | 0.002% buy side |
| SEBI fee | ₹10 per crore |
| GST | 18% on exchange charge + SEBI fee + brokerage |
| Brokerage | ₹20 per order (configurable) |
| Slippage | 0.5–3 bps per side, higher for GUINEA and PETAL |

Statutory cost per leg round trip is about 1.72 bps, so about 3.4 bps for a two-leg pair trade, before brokerage and slippage.

## 7. Validation

- Walk-forward: choose (lookback, entry_z) on the previous 12 months, trade the next 3 months, roll.
- Holdout: the last 6 months are traded once, with parameters chosen on all earlier data.
- Attribution: regress daily P&L on the P&L of holding the same grams of gold. β ≈ 0 means the result comes from the spread.
- Verdict: net ≤ 0 → no edge; net > 0 with t < 2 → not proven; t ≥ 2 → meaningful edge.

## 8. Known limits

- Settlement-based daily data cannot see intraday spreads or depth.
- The tender period is approximated as a fixed number of days before expiry. Replace it with exact MCX calendar dates when available.
- GOLDTEN's history starts in April 2025, so its results have fewer trades.
- The equal-gram GOLDM hedge leaves about 0.4% gold exposure because of the 995 vs 999 purity difference.
