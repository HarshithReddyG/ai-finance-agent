"""Phase 7 — Tool functions for the AI agent layer.

Every capability the agent will eventually be able to call lives here,
as plain Python functions with clear docstrings — nothing in this file
talks to an LLM at all. That split is deliberate: this module is the
"hands," and the next Phase 7 file (the orchestration loop) is what
gives an LLM the ability to choose from and call these hands. Keeping
them separate also means these are independently testable and reusable
outside the agent entirely — a Phase 8 Streamlit page could call
get_category_totals() directly for a static chart with no LLM involved.

Every function returns plain JSON-serializable Python (list[dict] /
dict) — never a pandas DataFrame or a SQLAlchemy ORM object, since
neither serializes into a tool-call result an LLM API can consume. This
also keeps faith with the earlier storage-layer decision: the agent
gets back a small, targeted result from a scoped query, never a dump of
raw transaction rows.

get_recurring_charges() reads from the recurring_series TABLE (written
by recurring.py) rather than calling detect_recurring() live — that
table is the intended, refreshable cache for exactly this purpose (see
recurring.py's module docstring). In practice that means recurring.py
needs to be re-run periodically (same idea as categorize_transactions.py)
for this tool's answer to stay current as new transactions arrive.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `from src...` imports work whether this file is run directly or as
# a module — see categorize_transactions.py for the full explanation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analytics.totals import category_totals, monthly_totals
from src.analytics.trends import category_trend, detect_spikes
from src.anomaly.detect import (
    detect_amount_outliers,
    detect_duplicate_charges,
    detect_rare_merchants,
)
from src.storage.db import get_session
from src.storage.schema import RecurringSeries


def get_category_totals(start: str | None = None, end: str | None = None) -> list[dict]:
    """Total spend per category, highest first. start/end are optional
    'YYYY-MM-DD' strings, inclusive."""
    return category_totals(start, end).to_dict(orient="records")


def get_monthly_totals(start: str | None = None, end: str | None = None) -> list[dict]:
    """Total spend per calendar month, chronological. start/end are
    optional 'YYYY-MM-DD' strings, inclusive."""
    return monthly_totals(start, end).to_dict(orient="records")


def get_category_trends() -> list[dict]:
    """Which categories are trending up/down recently (last 3 months vs.
    the 3 months before that), independent of any single-month spike."""
    return category_trend().to_dict(orient="records")


def get_recurring_charges() -> list[dict]:
    """Currently known recurring bills/subscriptions/income, as of the
    last time recurring.py's detector was run."""
    with get_session() as session:
        rows = session.query(RecurringSeries).all()
        return [
            {
                "merchant_name": r.merchant_name,
                "category": r.category,
                "account_id": r.account_id,
                "cadence": r.cadence,
                "expected_amount": float(r.expected_amount),
            }
            for r in rows
        ]


def get_anomalies() -> list[dict]:
    """Every anomaly Phase 5/6 currently know how to detect, combined into
    one list and tagged by anomaly_type — the shape an agent can reason
    over without needing to know which specific detector to call."""
    anomalies: list[dict] = []

    for _, row in detect_spikes().iterrows():
        anomalies.append({
            "anomaly_type": "category_spending_spike",
            "category": row["category"],
            "month": row["month"],
            "total": float(row["total"]),
            "detail": f"z-score {row['z_score']} vs. baseline {row['baseline_mean']}",
        })

    for _, row in detect_amount_outliers().iterrows():
        anomalies.append({
            "anomaly_type": "large_amount_outlier",
            "transaction_id": row["transaction_id"],
            "date": str(row["date"]),
            "merchant_name": row["merchant_name"],
            "category": row["category"],
            "amount": float(row["amount"]),
        })

    for _, row in detect_duplicate_charges().iterrows():
        anomalies.append({
            "anomaly_type": "duplicate_charge",
            "transaction_id": row["transaction_id"],
            "date": str(row["date"]),
            "merchant_name": row["merchant_name"],
            "amount": float(row["amount"]),
        })

    for _, row in detect_rare_merchants().iterrows():
        anomalies.append({
            "anomaly_type": "new_rare_merchant",
            "transaction_id": row["transaction_id"],
            "date": str(row["date"]),
            "merchant_name": row["merchant_name"],
            "category": row["category"],
            "amount": float(row["amount"]),
        })

    return anomalies


def compare_periods(
    period1_start: str, period1_end: str, period2_start: str, period2_end: str
) -> list[dict]:
    """Category-by-category spend comparison between two date ranges."""
    p1 = category_totals(period1_start, period1_end).set_index("category")["total"]
    p2 = category_totals(period2_start, period2_end).set_index("category")["total"]

    all_categories = sorted(set(p1.index) | set(p2.index))
    comparison = []
    for category in all_categories:
        v1 = float(p1.get(category, 0.0))
        v2 = float(p2.get(category, 0.0))
        comparison.append({
            "category": category,
            "period1_total": round(v1, 2),
            "period2_total": round(v2, 2),
            "change": round(v2 - v1, 2),
        })
    return comparison


if __name__ == "__main__":
    import json

    print("=== get_category_totals() ===")
    print(json.dumps(get_category_totals(), indent=2))

    print("\n=== get_category_trends() ===")
    print(json.dumps(get_category_trends(), indent=2))

    print("\n=== get_recurring_charges() ===")
    print(json.dumps(get_recurring_charges(), indent=2))

    print("\n=== get_anomalies() ===")
    print(json.dumps(get_anomalies(), indent=2))