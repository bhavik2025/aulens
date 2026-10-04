"""Copy downloaded MCX Bhavcopy CSVs into data/raw/ with the right names — no manual renaming.

Usage:  python scripts/import_downloads.py "C:/Users/<you>/Downloads"

For every CSV in the folder that looks like a Bhavcopy export, it reads the Date inside the file
and copies it to data/raw/YYYY-MM-DD.csv. A holiday download returns the previous day's data,
so it lands on an existing date and is skipped as a duplicate.
"""
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aulens.ingest import parse_response_date  # noqa: E402

RAW = ROOT / "data" / "raw"


def main(src: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    added = skipped = 0
    for f in sorted(Path(src).glob("*.csv")):
        try:
            head = pd.read_csv(f, nrows=5)
        except Exception:
            continue
        cols = {c.strip().lower() for c in head.columns}
        if not {"date", "symbol", "close"} <= cols or head.empty:
            continue
        d = parse_response_date(head.iloc[0][[c for c in head.columns if c.strip().lower() == "date"][0]])
        dest = RAW / f"{d.isoformat()}.csv"
        if dest.exists():
            skipped += 1
            print(f"skip  {f.name}: {d} already in data/raw (duplicate or holiday fallback)")
            continue
        shutil.copy2(f, dest)
        added += 1
        print(f"added {f.name} -> {dest.name}")
    print(f"\n{added} added, {skipped} skipped. Files in data/raw: {len(list(RAW.glob('*.csv')))}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "Downloads"))
