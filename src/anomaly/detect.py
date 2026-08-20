"""Phase 6 — Anomaly detection at the individual-transaction level.

Distinct from Phase 5's trends.py: that module asks "is this category's
MONTHLY TOTAL unusual," this one asks "is this ONE TRANSACTION unusual."
The two overlap on purpose in one case — an unusually large single
purchase can trip both a per-transaction amount check here AND push its
category's monthly total into trends.py's spike detector — and that's
expected, not double-counting a bug. They're independent checks looking
at the same data from different granularities.

Three checks, matching the architecture diagram's Phase 6 box:

1. detect_amount_outliers() — Z-score/IQR outliers. Uses the classic
   Tukey IQR rule (flag amount > Q3 + 1.5*IQR), computed PER CATEGORY,
   not globally. A global threshold would be dominated by naturally
   large categories like Housing/Travel and never flag a $2,450
   purchase in Shopping, where every other charge is under $100 — the
   whole point of "unusual" is unusual relative to that category's own
   normal range.

2. detect_duplicate_charges() — same merchant, same account, same
   amount, within a short number of days of each other. A real
   double-charge (POS retry, a subscription billed twice) shows up
   exactly this way; genuinely repeated recurring charges don't trip
   this because they're caught by the day-gap window, not the amount
   match alone — a $15.99 Netflix charge next month is 30 days away,
   not 2.

3. detect_rare_merchants() — a merchant appearing at or below
   `max_occurrences` times in the whole transaction history. This is
   informational, not inherently bad (everyone's first Amazon order was
   once a "rare merchant") — it's a flag worth a human glance, not an
   automatic red flag, which is why it's returned separately from the
   other two rather than folded into one generic "anomalies" list.

Validated against data/mock_transactions_eval.csv's is_anomaly_truth /
anomaly_type columns: at these default thresholds, all three checks
individually hit their corresponding injected case (large_one_off_purchase
-> Best Buy $2,450; duplicate_charge -> the cloned Trader Joe's charge;
new_rare_merchant -> Global Overseas Traders Ltd, the same merchant the
LLM fallback mis-categorized as Travel back in Phase 4) with zero false
positives on the mock dataset. The 6 category_spending_spike transactions
(the injected Restaurants spike) are correctly NOT caught by any of these
three — individually they're ordinary-sized, non-duplicate, non-rare
restaurant charges; only their combined monthly total is unusual, which
is exactly trends.py's job, not this file's.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Make `from src...` imports work whether this file is run directly or as
# a module — see categorize_transactions.py for the full explanation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.storage.db import engine

MIN_TXNS_FOR_OUTLIER_CHECK = 5
IQR_MULTIPLIER = 1.5

DUPLICATE_MAX_DAY_GAP = 2
DUPLICATE_AMOUNT_TOLERANCE = 0.01

RARE_MERCHANT_MAX_OCCURRENCES = 1


def _load_transactions_df() -> pd.DataFrame:
    query = (
        "SELECT transaction_id, date, merchant_name, account_id, category, amount "
        "FROM transactions"
    )
    return pd.read_sql(text(query), engine, parse_dates=["date"])


def detect_amount_outliers(iqr_multiplier: float = IQR_MULTIPLIER) -> pd.DataFrame:
    """Per-category Tukey IQR outliers among spend (amount > 0) transactions."""
    df = _load_transactions_df()
    spend = df[df["amount"] > 0]

    flagged = []
    for category, group in spend.groupby("category"):
        if len(group) < MIN_TXNS_FOR_OUTLIER_CHECK:
            continue

        q1, q3 = group["amount"].quantile(0.25), group["amount"].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        upper_fence = q3 + iqr_multiplier * iqr

        outliers = group[group["amount"] > upper_fence]
        for _, row in outliers.iterrows():
            flagged.append({
                "transaction_id": row["transaction_id"],
                "date": row["date"].date(),
                "merchant_name": row["merchant_name"],
                "category": category,
                "amount": row["amount"],
                "category_upper_fence": round(upper_fence, 2),
            })

    result = pd.DataFrame(flagged)
    if not result.empty:
        result = result.sort_values("amount", ascending=False).reset_index(drop=True)
    return result


def detect_duplicate_charges(
    max_day_gap: int = DUPLICATE_MAX_DAY_GAP,
    amount_tolerance: float = DUPLICATE_AMOUNT_TOLERANCE,
) -> pd.DataFrame:
    """Same merchant + account + amount, occurring within max_day_gap days."""
    df = _load_transactions_df().sort_values(["merchant_name", "account_id", "date"])

    flagged = []
    for (merchant, account_id), group in df.groupby(["merchant_name", "account_id"]):
        group = group.sort_values("date").reset_index(drop=True)
        for i in range(1, len(group)):
            prev_row, curr_row = group.iloc[i - 1], group.iloc[i]
            gap_days = (curr_row["date"] - prev_row["date"]).days
            amount_diff = abs(curr_row["amount"] - prev_row["amount"])

            if gap_days <= max_day_gap and amount_diff <= amount_tolerance:
                for row in (prev_row, curr_row):
                    flagged.append({
                        "transaction_id": row["transaction_id"],
                        "date": row["date"].date(),
                        "merchant_name": merchant,
                        "account_id": account_id,
                        "amount": row["amount"],
                    })

    result = pd.DataFrame(flagged)
    if not result.empty:
        result = result.drop_duplicates(subset="transaction_id").sort_values(
            ["merchant_name", "date"]
        ).reset_index(drop=True)
    return result


def detect_rare_merchants(max_occurrences: int = RARE_MERCHANT_MAX_OCCURRENCES) -> pd.DataFrame:
    """Merchants appearing at or below max_occurrences times, ever."""
    df = _load_transactions_df()
    counts = df.groupby("merchant_name").size()
    rare_merchants = counts[counts <= max_occurrences].index

    result = df[df["merchant_name"].isin(rare_merchants)][
        ["transaction_id", "date", "merchant_name", "category", "amount"]
    ].copy()
    if not result.empty:
        result["date"] = result["date"].dt.date
        result = result.sort_values("date").reset_index(drop=True)
    return result


def main() -> None:
    print("=== Amount outliers (per-category IQR) ===")
    outliers = detect_amount_outliers()
    print("None detected." if outliers.empty else outliers.to_string(index=False))

    print(f"\n=== Duplicate charges (within {DUPLICATE_MAX_DAY_GAP} days) ===")
    duplicates = detect_duplicate_charges()
    print("None detected." if duplicates.empty else duplicates.to_string(index=False))

    print(f"\n=== Rare merchants (<= {RARE_MERCHANT_MAX_OCCURRENCES} occurrence) ===")
    rare = detect_rare_merchants()
    print("None detected." if rare.empty else rare.to_string(index=False))


if __name__ == "__main__":
    main()