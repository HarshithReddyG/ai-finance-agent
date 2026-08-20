"""Phase 5 — Recurring subscription / bill detection.

Second half of the analytics engine (totals.py did category/monthly
totals). This groups transactions by (merchant_name, account_id) and
flags a group as a recurring series when BOTH:
  1. Timing is regular — the median gap between consecutive occurrences
     falls inside a known cadence window (weekly/biweekly/monthly), and
     the gaps don't vary wildly (stdev capped).
  2. Amount is stable — the amounts across occurrences have low
     coefficient of variation (std / mean), so a merchant you happen to
     visit often but for wildly different amounts (e.g. a coffee shop)
     doesn't get mistaken for a bill.

Deliberately grouped by (merchant_name, account_id), not merchant alone —
the same merchant name showing up on two different accounts is two
separate real-world charges, not one series.

recurring_series (schema.py, Phase 3) is treated as a fully-derived,
recomputable table, not a source of truth: every run clears it and
reinserts the freshly detected set, rather than trying to diff/merge
against what was there before. That's a deliberate difference from
categorize_transactions.py's category column, which is precious
per-transaction data you never want to silently overwrite — a detected
recurring series is just a summary that's always safe to throw away and
recompute from the transactions table.

Validated against data/mock_transactions_eval.csv's is_recurring_truth
ground truth (see the bottom of this file's module docstring in
PROJECT_TRACKER.md notes, or run scripts/validate_recurring.py) —
current thresholds get all 7 monthly bills, the biweekly paycheck, and
the monthly transfer pair with no false positives on the mock data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Make `from src...` imports work whether this file is run directly or as
# a module — see categorize_transactions.py for the full explanation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.storage.db import engine, get_session
from src.storage.schema import RecurringSeries

MIN_OCCURRENCES = 3

# (min_days, max_days) gap between consecutive occurrences, inclusive.
CADENCE_WINDOWS = {
    "weekly": (6, 8),
    "biweekly": (12, 16),
    "monthly": (26, 32),
}

MAX_INTERVAL_STDEV_DAYS = 5.0
MAX_AMOUNT_COEF_VARIATION = 0.10  # amounts allowed to vary +/-10% (covers jitter)


def _load_transactions_df() -> pd.DataFrame:
    query = (
        "SELECT transaction_id, date, merchant_name, account_id, category, amount "
        "FROM transactions ORDER BY merchant_name, account_id, date"
    )
    return pd.read_sql(text(query), engine, parse_dates=["date"])


def _classify_cadence(median_interval_days: float) -> str | None:
    for name, (lo, hi) in CADENCE_WINDOWS.items():
        if lo <= median_interval_days <= hi:
            return name
    return None


def detect_recurring(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per detected recurring (merchant, account) series."""
    if df is None:
        df = _load_transactions_df()

    results = []
    for (merchant, account_id), group in df.groupby(["merchant_name", "account_id"]):
        if len(group) < MIN_OCCURRENCES:
            continue

        group = group.sort_values("date")
        intervals = group["date"].diff().dt.days.dropna()
        if intervals.empty:
            continue

        cadence = _classify_cadence(intervals.median())
        if cadence is None:
            continue
        if intervals.std(ddof=0) > MAX_INTERVAL_STDEV_DAYS:
            continue

        # abs(): a recurring series can be a bill (positive/spend) or
        # income like a paycheck (negative/money-in) — cadence and amount
        # stability matter here, not the sign.
        amounts = group["amount"].abs()
        mean_amount = amounts.mean()
        coef_variation = amounts.std(ddof=0) / mean_amount if mean_amount else float("inf")
        if coef_variation > MAX_AMOUNT_COEF_VARIATION:
            continue

        category = None
        known_categories = group["category"].dropna()
        if not known_categories.empty:
            category = known_categories.mode().iat[0]

        results.append({
            "merchant_name": merchant,
            "account_id": account_id,
            "category": category,
            "cadence": cadence,
            "expected_amount": round(mean_amount, 2),
            "occurrences": len(group),
            "transaction_ids": group["transaction_id"].tolist(),
        })

    return pd.DataFrame(results)


def save_recurring_series(session, detected: pd.DataFrame) -> int:
    """Clear and reinsert — see module docstring for why this is safe."""
    session.query(RecurringSeries).delete()
    count = 0
    for _, row in detected.iterrows():
        session.add(RecurringSeries(
            merchant_name=row["merchant_name"],
            category=row["category"],
            account_id=row["account_id"],
            cadence=row["cadence"],
            expected_amount=row["expected_amount"],
        ))
        count += 1
    return count


def main() -> None:
    detected = detect_recurring()

    print(f"Detected {len(detected)} recurring series:\n")
    if not detected.empty:
        display_cols = ["merchant_name", "account_id", "category", "cadence", "expected_amount", "occurrences"]
        print(detected[display_cols].to_string(index=False))

    with get_session() as session:
        n = save_recurring_series(session, detected)
        session.commit()

    print(f"\nSaved {n} recurring series to recurring_series table.")


if __name__ == "__main__":
    main()