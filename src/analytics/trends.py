"""Phase 5 — Category trend & spending-spike detection.

Third and last Phase 5 file, completing the analytics engine box in the
architecture diagram. Builds directly on totals.py's category/month
grouping logic rather than re-querying the DB — this module never talks
to SQL directly, it starts from the same monthly-per-category breakdown
totals.py already knows how to build.

Two distinct things live here, both requested by the Phase 5 spec:

1. detect_spikes() — is any single (category, month) unusually high
   relative to that category's OWN history? Uses a leave-one-out z-score:
   for each month, the mean/stdev baseline is computed from every OTHER
   month in that category's series, deliberately excluding the month
   being tested. A spike's whole point is that it doesn't belong in its
   own baseline — including it would drag the mean/stdev up and make the
   spike look less extreme than it is, which is the opposite of what an
   outlier detector should do.

2. category_trend() — is a category's spending drifting up or down over
   time, independent of any single-month spike? Compares the average of
   the most recent `recent_months` to the average of the
   `recent_months` immediately before that, as a plain percent change.
   Deliberately simple (no regression fit) — with only ~14 months of
   mock data, a 3-months-vs-3-months comparison is easier to explain to
   a user asking "is my grocery spending going up?" than a fitted slope
   coefficient would be, and just as informative at this data volume.

Validated against data/mock_transactions_eval.csv: detect_spikes() at
its default threshold (z > 3.0) correctly catches the one intentionally
injected "category_spending_spike" anomaly (Restaurants, the month with
6 extra restaurant charges bunched into one week) with two other flags —
Shopping in the month containing the large one-off Best Buy purchase and
the new rare merchant charge (a legitimate category-total anomaly, just
one Phase 6 will also independently catch from the single-transaction
side), and one flag (Gas & Fuel) that isn't in the injected-anomaly list
at all. That last one is real: with 14 categories x 14 months, plain
random month-to-month variance will occasionally cross a z=3 threshold
by chance even with no anomaly injected — a known property of z-score
thresholds at this many comparisons, not a bug. Lower the threshold and
you'll catch more real spikes at the cost of more of this kind of noise;
this default leans toward fewer false alarms.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Make `from src...` imports work whether this file is run directly or as
# a module — see categorize_transactions.py for the full explanation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analytics.totals import _load_transactions_df, _spend_only

MIN_MONTHS_FOR_SPIKE_CHECK = 4
DEFAULT_Z_THRESHOLD = 3.0

DEFAULT_TREND_WINDOW_MONTHS = 3
TREND_RISING_PCT = 15.0
TREND_FALLING_PCT = -15.0


def _category_month_totals() -> pd.DataFrame:
    """Long-format: one row per (category, month) with that month's spend total."""
    df = _load_transactions_df()
    spend = _spend_only(df).copy()
    spend["month"] = spend["date"].dt.to_period("M").astype(str)
    totals = spend.groupby(["category", "month"])["amount"].sum().reset_index()
    return totals.rename(columns={"amount": "total"})


def detect_spikes(
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    min_months: int = MIN_MONTHS_FOR_SPIKE_CHECK,
) -> pd.DataFrame:
    """Flag (category, month) pairs whose total is a leave-one-out
    statistical outlier relative to that category's other months."""
    totals = _category_month_totals()
    flagged = []

    for category, group in totals.groupby("category"):
        monthly = group.set_index("month")["total"].sort_index()
        if len(monthly) < min_months:
            continue

        for month, total in monthly.items():
            others = monthly.drop(month)
            mean, stdev = others.mean(), others.std(ddof=0)
            if stdev == 0:
                continue
            z_score = (total - mean) / stdev
            if z_score > z_threshold:
                flagged.append({
                    "category": category,
                    "month": month,
                    "total": round(total, 2),
                    "baseline_mean": round(mean, 2),
                    "z_score": round(z_score, 2),
                })

    result = pd.DataFrame(flagged)
    if not result.empty:
        result = result.sort_values("z_score", ascending=False).reset_index(drop=True)
    return result


def category_trend(
    recent_months: int = DEFAULT_TREND_WINDOW_MONTHS,
) -> pd.DataFrame:
    """Percent change: average of the most recent `recent_months` vs. the
    `recent_months` immediately before that, per category."""
    totals = _category_month_totals()
    trends = []

    for category, group in totals.groupby("category"):
        monthly = group.set_index("month")["total"].sort_index()
        if len(monthly) < recent_months * 2:
            continue

        recent = monthly.iloc[-recent_months:].mean()
        prior = monthly.iloc[-recent_months * 2:-recent_months].mean()
        if prior == 0:
            continue

        pct_change = (recent - prior) / prior * 100
        if pct_change >= TREND_RISING_PCT:
            direction = "rising"
        elif pct_change <= TREND_FALLING_PCT:
            direction = "falling"
        else:
            direction = "flat"

        trends.append({
            "category": category,
            "recent_avg": round(recent, 2),
            "prior_avg": round(prior, 2),
            "pct_change": round(pct_change, 1),
            "direction": direction,
        })

    result = pd.DataFrame(trends)
    if not result.empty:
        result = result.sort_values("pct_change", ascending=False).reset_index(drop=True)
    return result


def main() -> None:
    spikes = detect_spikes()
    print(f"=== Spending spikes (z > {DEFAULT_Z_THRESHOLD}) ===")
    if spikes.empty:
        print("None detected.")
    else:
        print(spikes.to_string(index=False))

    print(f"\n=== Category trends (last {DEFAULT_TREND_WINDOW_MONTHS} vs. prior {DEFAULT_TREND_WINDOW_MONTHS} months) ===")
    trends = category_trend()
    if trends.empty:
        print("Not enough months of history yet.")
    else:
        print(trends.to_string(index=False))


if __name__ == "__main__":
    main()