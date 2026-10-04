"""Load and validate MCX Bhavcopy files.

Handles the data traps listed in PS 03:
  * the returned Date may differ from the requested date (holiday / bad date) -> rejected
  * request dates are DD/MM/YYYY, response Date is MM/DD/YYYY, ExpiryDate is like 04SEP2026
  * Symbol values may be space-padded
  * contracts are tracked by expiry date, never stitched into a continuous series
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .specs import GOLD_SYMBOLS

# Column aliases seen in MCX exports -> our canonical names.
ALIASES = {
    "symbol": "symbol", "date": "date", "expirydate": "expiry", "expiry": "expiry",
    "open": "open", "high": "high", "low": "low", "close": "close",
    "settlementprice": "settle", "settlement": "settle",
    "volume": "volume", "volume(lots)": "volume", "openinterest": "oi", "openinterest(lots)": "oi",
}
CANON = ["date", "symbol", "expiry", "open", "high", "low", "close", "volume", "oi"]


RESPONSE_DATE_FORMATS = ("%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d")
EXPIRY_FORMATS = ("%d%b%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d")


def _parse(s, formats) -> date:
    s = str(s).strip()
    for fmt in formats:
        try:
            return datetime.strptime(s.title() if "%b" in fmt else s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {s!r}")


def parse_response_date(s: str) -> date:
    """Response Date: MM/DD/YYYY per the PS; the website CSV export uses 01-Oct-26."""
    return _parse(s, RESPONSE_DATE_FORMATS)


def parse_expiry(s: str) -> date:
    """ExpiryDate: 04SEP2026 per the PS; the website CSV export uses 05-Oct-26."""
    return _parse(str(s).upper(), EXPIRY_FORMATS)


def format_request_date(d: date) -> str:
    """Bhavcopy requests use DD/MM/YYYY."""
    return d.strftime("%d/%m/%Y")


def _norm_col(c: str) -> str:
    return re.sub(r"[\s_]", "", str(c)).lower()


def clean_frame(raw: pd.DataFrame, requested: date | None = None, log: list | None = None) -> pd.DataFrame:
    """Standardise one day's Bhavcopy rows and keep only the gold contracts."""
    log = log if log is not None else []
    df = raw.rename(columns={c: ALIASES.get(_norm_col(c), _norm_col(c)) for c in raw.columns})
    if "close" not in df and "settle" in df:
        df["close"] = df["settle"]
    missing = [c for c in CANON if c not in df]
    if missing:
        raise ValueError(f"Bhavcopy file is missing columns: {missing}")
    if "instrumentname" in df:  # website export mixes futures, options and other segments
        df = df[df["instrumentname"].astype(str).str.strip().str.upper() == "FUTCOM"]
    df = df[CANON].copy()
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df = df[df["symbol"].isin(GOLD_SYMBOLS)]
    df["date"] = df["date"].map(parse_response_date)
    df["expiry"] = df["expiry"].map(parse_expiry)
    for c in ["open", "high", "low", "close", "volume", "oi"]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")

    if requested is not None:
        bad = df["date"] != requested
        if bad.any():
            got = sorted(set(df.loc[bad, "date"]))
            log.append(f"{requested}: file returned {got} instead -> rejected (holiday/invalid date)")
            df = df[~bad]
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    return df


def load_folder(folder: str | Path, log: list | None = None) -> pd.DataFrame:
    """Load every CSV in a folder. If a file is named YYYY-MM-DD.csv we treat that as the
    requested date and reject rows whose Date does not match it."""
    log = log if log is not None else []
    frames = []
    for path in sorted(Path(folder).glob("*.csv")):
        requested = None
        m = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
        m2 = re.search(r"BhavCopyDateWise_(\d{2})(\d{2})(\d{4})", path.stem, re.I)
        if m:
            requested = date.fromisoformat(m.group(1))
        elif m2:  # MCX's own download name: BhavCopyDateWise_DDMMYYYY.csv
            requested = date(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
        try:
            frames.append(clean_frame(pd.read_csv(path), requested, log))
        except Exception as e:  # keep going, but record it
            log.append(f"{path.name}: {e}")
    if not frames:
        return pd.DataFrame(columns=CANON)
    df = pd.concat(frames, ignore_index=True)
    before = len(df)
    df = df.drop_duplicates(subset=["date", "symbol", "expiry"], keep="last")
    if len(df) < before:
        log.append(f"dropped {before - len(df)} duplicate rows")
    return finalize(df)


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["expiry"] = pd.to_datetime(df["expiry"])
    df["dte"] = (df["expiry"] - df["date"]).dt.days
    df = df[df["dte"] >= 0]
    return df.sort_values(["date", "symbol", "expiry"]).reset_index(drop=True)
