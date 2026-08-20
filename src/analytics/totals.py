"""Phase 5 — Category and monthly spending totals.

The first, most foundational piece of the analytics engine: everything
else in Phase 5 (trend/spike detection, recurring-subscription finding)
and eventually Phase 7's tool-calling agent (get_category_totals) will
build on the same pattern used here — query the DB directly with
pandas.read_sql(), never load the whole transactions table into a
prompt. That's the same reasoning behind the earlier SQLite-over-raw-CSV
decision: the agent should call a tool that runs a scoped query and
returns a small aggregate, not receive a dump of every row.

Sign convention (inherited from Plaid, which the mock data generator
matches — see PROJECT_TRACKER.md Phase 2 session log): a POSITIVE amount
is money leaving the account (a purchase/spend), a NEGATIVE amount is
money coming in (income, refund, a payment/credit). "Totals" here means
spend only — positive amounts — with two categories deliberately
excluded from spend:
  - "Transfers": moving your own money between your own accounts
    (checking -> savings, credit card payment) isn't spending.
  - Rows with category IS NULL: rather than silently dropping these
    (which would understate totals with no visible sign anything's
    missing), they're grouped into an explicit "Uncategorized" bucket so
    a gap in Phase 4 coverage stays visible in Phase 5's output instead
    of quietly disappearing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Make `from src...` imports work whether this file is run directly
# (`python3.11 src/analytics/totals.py`) or as a module
# (`python3.11 -m src.analytics.totals`) — see categorize_transactions.py
# for the full explanation of why this is needed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.storage.db import engine

EXCLUDED_FROM_SPEND = {"Transfers"}


def _load_transactions_df(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    query = "SELECT date, merchant_name, category, amount FROM transactions"
    conditions = []
    params: dict[str, str] = {}

    if start:
        conditions.append("date >= :start")
        params["start"] = start
    if end:
        conditions.append("date <= :end")
        params["end"] = end
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    df = pd.read_sql(text(query), engine, params=params, parse_dates=["date"])
    df["category"] = df["category"].fillna("Uncategorized")
    return df


def _spend_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["amount"] > 0) & (~df["category"].isin(EXCLUDED_FROM_SPEND))]


def category_totals(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Total spend per category, highest first. Optional start/end are
    'YYYY-MM-DD' strings, inclusive, matching the DB's stored date format."""
    df = _load_transactions_df(start, end)
    spend = _spend_only(df)
    totals = spend.groupby("category")["amount"].sum().sort_values(ascending=False)
    return totals.reset_index().rename(columns={"amount": "total"})


def monthly_totals(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Total spend per calendar month, chronological."""
    df = _load_transactions_df(start, end)
    spend = _spend_only(df).copy()
    spend["month"] = spend["date"].dt.to_period("M").astype(str)
    totals = spend.groupby("month")["amount"].sum().sort_index()
    return totals.reset_index().rename(columns={"amount": "total"})


def main() -> None:
    print("=== Category totals ===")
    print(category_totals().to_string(index=False))
    print("\n=== Monthly totals ===")
    print(monthly_totals().to_string(index=False))


if __name__ == "__main__":
    main()