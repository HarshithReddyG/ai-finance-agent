"""Phase 2 — Mock transaction data generator.

Generates a synthetic but realistic transaction history for one fictitious
user across three accounts (checking, credit card, savings) and writes two
CSV files:

  data/mock_transactions.csv
      The "raw ingest" file — this is what Phase 3's ingestion script will
      read, and what a real Plaid `transactions/get` response would roughly
      correspond to. Deliberately has NO category column: building the
      categorizer is Phase 4's job, not this script's.

  data/mock_transactions_eval.csv
      A ground-truth companion file (same transaction_ids) used ONLY to
      score later phases: true category, whether a transaction is part of
      a recurring series, and whether it's one of the intentionally
      injected anomalies. Never feed this into the categorization or
      anomaly-detection code itself — that would be cheating. It exists so
      Phase 4/5/6 can report "N/M correct" against a known answer key.

Design notes (see docs/phase_notes/phase2.md for the full writeup):
  - Amounts follow the Plaid sign convention: positive = money OUT of the
    account (an expense/debit), negative = money IN (income/credit/refund).
    Matching this now avoids a sign-flip headache in Phase 10.
  - A fixed --seed makes runs reproducible, which matters for a tutorial:
    everyone following along gets the same numbers to compare against.
  - A handful of recurring charges (rent, streaming, gym, phone, insurance,
    paycheck) are injected on a fixed cadence so Phase 5's recurring-payment
    detector has real signal to find.
  - A handful of anomalies (duplicate charge, one-off large purchase, a
    brand-new rare merchant, a spending-category spike) are injected so
    Phase 6's anomaly detector has real signal to find.

Usage:
    python -m src.ingestion.generate_mock_transactions
    python -m src.ingestion.generate_mock_transactions --months 13 --seed 42
"""

from __future__ import annotations

import argparse
import random
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# Reference data: merchants grouped by their true category.
# ---------------------------------------------------------------------------

MERCHANT_CATEGORIES: dict[str, list[str]] = {
    "Groceries": ["Whole Foods Market", "Trader Joe's", "Safeway", "Kroger"],
    "Restaurants": ["Chipotle", "McDonald's", "Olive Garden", "Local Diner", "Panera Bread"],
    "Coffee Shops": ["Starbucks", "Peet's Coffee", "Local Coffee Co"],
    "Gas & Fuel": ["Shell", "Chevron", "ExxonMobil"],
    "Transportation": ["Uber", "Lyft", "City Metro Transit"],
    "Shopping": ["Amazon", "Target", "Best Buy", "Nike"],
    "Entertainment": ["AMC Theatres", "Steam Games", "Local Bowling Alley"],
    "Subscriptions": ["Netflix", "Spotify", "Adobe Creative Cloud", "NYT Digital"],
    "Utilities": ["City Water Utility", "Pacific Power & Light", "Comcast Xfinity", "Verizon Wireless"],
    "Housing": ["Parkview Apartments Management"],
    "Insurance": ["State Farm Insurance", "Blue Cross Blue Shield"],
    "Healthcare": ["CVS Pharmacy", "Walgreens", "City Medical Clinic"],
    "Travel": ["Delta Air Lines", "Marriott Hotels", "Airbnb"],
    "Fitness": ["Planet Fitness"],
    "Income": ["Acme Corp Payroll"],
    "Fees": ["Bank Monthly Maintenance Fee", "Out-of-Network ATM Fee"],
    "Transfers": ["Transfer to Savings", "Transfer from Checking"],
}

RAW_DESCRIPTION_TEMPLATES = [
    "{merchant}",
    "SQ *{merchant_upper}",
    "{merchant_upper} #{store_no} {city} {state}",
    "POS DEBIT {merchant_upper}",
    "{merchant_upper} WEB PYMT",
]

ACCOUNTS = [
    {"account_id": "chk_0001", "account_type": "checking"},
    {"account_id": "cc_0001", "account_type": "credit_card"},
    {"account_id": "sav_0001", "account_type": "savings"},
]

# Recurring series: (merchant, category, account_id, day_of_month, amount, jitter)
RECURRING_SERIES = [
    ("Parkview Apartments Management", "Housing", "chk_0001", 1, 1450.00, 0.0),
    ("Netflix", "Subscriptions", "cc_0001", 3, 15.99, 0.0),
    ("Spotify", "Subscriptions", "cc_0001", 5, 10.99, 0.0),
    ("Planet Fitness", "Fitness", "cc_0001", 7, 39.99, 0.0),
    ("Verizon Wireless", "Utilities", "chk_0001", 12, 85.00, 3.00),
    ("Comcast Xfinity", "Utilities", "chk_0001", 14, 70.00, 2.00),
    ("State Farm Insurance", "Insurance", "chk_0001", 18, 120.00, 0.0),
]

# Biweekly paycheck: negative amount (money IN), Plaid sign convention.
PAYCHECK = {"merchant": "Acme Corp Payroll", "category": "Income", "account_id": "chk_0001", "amount": 2100.00}

# Monthly transfer pair, checking -> savings. Modeled as two linked
# transactions (one per account) so the analytics layer has a realistic
# case for "exclude transfers between my own accounts from spend totals."
MONTHLY_TRANSFER_AMOUNT = 300.00
MONTHLY_TRANSFER_DAY = 2


@dataclass
class Transaction:
    transaction_id: str
    account_id: str
    account_type: str
    date: date
    merchant_name: str
    raw_description: str
    amount: float
    currency: str
    pending: bool
    category_truth: str
    is_recurring_truth: bool
    is_anomaly_truth: bool
    anomaly_type: str | None


def make_raw_description(fake: Faker, rng: random.Random, merchant: str) -> str:
    template = rng.choice(RAW_DESCRIPTION_TEMPLATES)
    return template.format(
        merchant=merchant,
        merchant_upper=merchant.upper().replace("'", ""),
        store_no=rng.randint(1000, 9999),
        city=fake.city().upper(),
        state=fake.state_abbr(),
    )


def daterange_months_back(months: int, end: date) -> tuple[date, date]:
    start = (end.replace(day=1) - timedelta(days=1))
    for _ in range(months - 1):
        start = (start.replace(day=1) - timedelta(days=1))
    start = start.replace(day=1)
    return start, end


def generate_recurring(fake: Faker, rng: random.Random, start: date, end: date) -> list[Transaction]:
    txns: list[Transaction] = []
    account_type_by_id = {a["account_id"]: a["account_type"] for a in ACCOUNTS}

    # Recurring bills.
    for merchant, category, account_id, day, base_amount, jitter in RECURRING_SERIES:
        current = date(start.year, start.month, 1)
        while current <= end:
            try:
                txn_date = current.replace(day=day)
            except ValueError:
                txn_date = current.replace(day=28)  # short months
            if start <= txn_date <= end:
                amount = round(base_amount + rng.uniform(-jitter, jitter), 2) if jitter else base_amount
                txns.append(Transaction(
                    transaction_id=str(uuid.uuid4()),
                    account_id=account_id,
                    account_type=account_type_by_id[account_id],
                    date=txn_date,
                    merchant_name=merchant,
                    raw_description=make_raw_description(fake, rng, merchant),
                    amount=amount,
                    currency="USD",
                    pending=False,
                    category_truth=category,
                    is_recurring_truth=True,
                    is_anomaly_truth=False,
                    anomaly_type=None,
                ))
            # advance one month
            year = current.year + (current.month // 12)
            month = current.month % 12 + 1
            current = date(year, month, 1)

    # Biweekly paycheck.
    current = start
    # align to a Friday-ish cadence starting from the first Friday on/after start
    while current.weekday() != 4:
        current += timedelta(days=1)
    while current <= end:
        txns.append(Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id=PAYCHECK["account_id"],
            account_type=account_type_by_id[PAYCHECK["account_id"]],
            date=current,
            merchant_name=PAYCHECK["merchant"],
            raw_description=make_raw_description(fake, rng, PAYCHECK["merchant"]),
            amount=-PAYCHECK["amount"],  # negative = money in
            currency="USD",
            pending=False,
            category_truth=PAYCHECK["category"],
            is_recurring_truth=True,
            is_anomaly_truth=False,
            anomaly_type=None,
        ))
        current += timedelta(days=14)

    # Monthly checking -> savings transfer (a paired transaction, not a
    # single merchant charge). Kept in its own category ("Transfers") so
    # Phase 5 can choose to filter transfers out of spend totals.
    current = date(start.year, start.month, 1)
    while current <= end:
        try:
            txn_date = current.replace(day=MONTHLY_TRANSFER_DAY)
        except ValueError:
            txn_date = current.replace(day=28)
        if start <= txn_date <= end:
            txns.append(Transaction(
                transaction_id=str(uuid.uuid4()),
                account_id="chk_0001",
                account_type=account_type_by_id["chk_0001"],
                date=txn_date,
                merchant_name="Transfer to Savings",
                raw_description="ONLINE TRANSFER TO SAVINGS xxxx0001",
                amount=MONTHLY_TRANSFER_AMOUNT,
                currency="USD",
                pending=False,
                category_truth="Transfers",
                is_recurring_truth=True,
                is_anomaly_truth=False,
                anomaly_type=None,
            ))
            txns.append(Transaction(
                transaction_id=str(uuid.uuid4()),
                account_id="sav_0001",
                account_type=account_type_by_id["sav_0001"],
                date=txn_date,
                merchant_name="Transfer from Checking",
                raw_description="ONLINE TRANSFER FROM CHECKING xxxx0001",
                amount=-MONTHLY_TRANSFER_AMOUNT,
                currency="USD",
                pending=False,
                category_truth="Transfers",
                is_recurring_truth=True,
                is_anomaly_truth=False,
                anomaly_type=None,
            ))
        year = current.year + (current.month // 12)
        month = current.month % 12 + 1
        current = date(year, month, 1)

    return txns


def generate_everyday_spending(fake: Faker, rng: random.Random, start: date, end: date, per_week: int) -> list[Transaction]:
    txns: list[Transaction] = []
    account_type_by_id = {a["account_id"]: a["account_type"] for a in ACCOUNTS}
    spendable_categories = {
        k: v for k, v in MERCHANT_CATEGORIES.items()
        if k not in ("Income", "Housing", "Subscriptions", "Insurance", "Fitness", "Utilities", "Fees", "Transfers")
    }
    amount_ranges = {
        "Groceries": (25, 140),
        "Restaurants": (12, 65),
        "Coffee Shops": (4, 9),
        "Gas & Fuel": (30, 70),
        "Transportation": (8, 35),
        "Shopping": (15, 220),
        "Entertainment": (10, 60),
        "Travel": (150, 900),
        "Healthcare": (15, 120),
    }

    current = start
    while current <= end:
        n_this_week = rng.randint(max(0, per_week - 3), per_week + 3)
        for _ in range(n_this_week):
            offset = rng.randint(0, 6)
            txn_date = current + timedelta(days=offset)
            if txn_date > end:
                continue
            category = rng.choice(list(spendable_categories.keys()))
            merchant = rng.choice(spendable_categories[category])
            low, high = amount_ranges[category]
            amount = round(rng.uniform(low, high), 2)
            account_id = "cc_0001" if rng.random() < 0.7 else "chk_0001"
            txns.append(Transaction(
                transaction_id=str(uuid.uuid4()),
                account_id=account_id,
                account_type=account_type_by_id[account_id],
                date=txn_date,
                merchant_name=merchant,
                raw_description=make_raw_description(fake, rng, merchant),
                amount=amount,
                currency="USD",
                pending=(end - txn_date).days <= 2 and rng.random() < 0.4,
                category_truth=category,
                is_recurring_truth=False,
                is_anomaly_truth=False,
                anomaly_type=None,
            ))
        current += timedelta(days=7)

    return txns


def inject_anomalies(fake: Faker, rng: random.Random, txns: list[Transaction], end: date) -> list[Transaction]:
    account_type_by_id = {a["account_id"]: a["account_type"] for a in ACCOUNTS}
    anomalies: list[Transaction] = []

    # 1. Duplicate charge: pick an existing grocery/restaurant txn near the end
    #    of the period and clone it a day later with the same amount.
    candidates = [t for t in txns if t.category_truth in ("Groceries", "Restaurants") and t.date <= end - timedelta(days=10)]
    if candidates:
        original = rng.choice(candidates)
        dup = Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id=original.account_id,
            account_type=original.account_type,
            date=original.date,
            merchant_name=original.merchant_name,
            raw_description=original.raw_description,
            amount=original.amount,
            currency="USD",
            pending=False,
            category_truth=original.category_truth,
            is_recurring_truth=False,
            is_anomaly_truth=True,
            anomaly_type="duplicate_charge",
        )
        anomalies.append(dup)

    # 2. Unusually large one-off purchase.
    large_date = end - timedelta(days=rng.randint(5, 25))
    anomalies.append(Transaction(
        transaction_id=str(uuid.uuid4()),
        account_id="cc_0001",
        account_type=account_type_by_id["cc_0001"],
        date=large_date,
        merchant_name="Best Buy",
        raw_description=make_raw_description(fake, rng, "Best Buy"),
        amount=2450.00,
        currency="USD",
        pending=False,
        category_truth="Shopping",
        is_recurring_truth=False,
        is_anomaly_truth=True,
        anomaly_type="large_one_off_purchase",
    ))

    # 3. Brand-new / rare merchant appearing exactly once.
    rare_date = end - timedelta(days=rng.randint(1, 15))
    anomalies.append(Transaction(
        transaction_id=str(uuid.uuid4()),
        account_id="cc_0001",
        account_type=account_type_by_id["cc_0001"],
        date=rare_date,
        merchant_name="Global Overseas Traders Ltd",
        raw_description="INTL PURCHASE GLOBAL OVERSEAS TRADERS",
        amount=312.40,
        currency="USD",
        pending=False,
        category_truth="Shopping",
        is_recurring_truth=False,
        is_anomaly_truth=True,
        anomaly_type="new_rare_merchant",
    ))

    # 4. Spending spike: add several extra restaurant charges concentrated
    #    in a single week to simulate a "vacation month" spike.
    spike_week_start = end - timedelta(days=rng.randint(30, 45))
    for i in range(6):
        spike_date = spike_week_start + timedelta(days=i)
        if spike_date > end:
            continue
        merchant = rng.choice(MERCHANT_CATEGORIES["Restaurants"])
        anomalies.append(Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="cc_0001",
            account_type=account_type_by_id["cc_0001"],
            date=spike_date,
            merchant_name=merchant,
            raw_description=make_raw_description(fake, rng, merchant),
            amount=round(rng.uniform(40, 95), 2),
            currency="USD",
            pending=False,
            category_truth="Restaurants",
            is_recurring_truth=False,
            is_anomaly_truth=True,
            anomaly_type="category_spending_spike",
        ))

    return anomalies


def generate(months: int, seed: int, end: date | None = None) -> pd.DataFrame:
    end = end or date.today()
    start, end = daterange_months_back(months, end)

    fake = Faker()
    Faker.seed(seed)
    rng = random.Random(seed)

    txns: list[Transaction] = []
    txns += generate_recurring(fake, rng, start, end)
    txns += generate_everyday_spending(fake, rng, start, end, per_week=6)
    txns += inject_anomalies(fake, rng, txns, end)

    rows = [t.__dict__ for t in txns]
    df = pd.DataFrame(rows).sort_values(["date", "account_id"]).reset_index(drop=True)
    return df


def write_outputs(df: pd.DataFrame, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    ingest_columns = [
        "transaction_id", "account_id", "account_type", "date",
        "merchant_name", "raw_description", "amount", "currency", "pending",
    ]
    eval_columns = [
        "transaction_id", "category_truth", "is_recurring_truth",
        "is_anomaly_truth", "anomaly_type",
    ]

    ingest_path = out_dir / "mock_transactions.csv"
    eval_path = out_dir / "mock_transactions_eval.csv"

    df[ingest_columns].to_csv(ingest_path, index=False)
    df[eval_columns].to_csv(eval_path, index=False)
    return ingest_path, eval_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock transaction data (Phase 2).")
    parser.add_argument("--months", type=int, default=13, help="How many months of history to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument("--out-dir", type=str, default="data", help="Output directory for the CSV files.")
    args = parser.parse_args()

    df = generate(months=args.months, seed=args.seed)
    ingest_path, eval_path = write_outputs(df, Path(args.out_dir))

    n_anomalies = int(df["is_anomaly_truth"].sum())
    n_recurring = int(df["is_recurring_truth"].sum())
    print(f"Generated {len(df)} transactions from {df['date'].min()} to {df['date'].max()}")
    print(f"  recurring: {n_recurring}, anomalies: {n_anomalies}")
    print(f"Wrote: {ingest_path}")
    print(f"Wrote: {eval_path} (ground truth — do not feed into the categorizer/detectors)")


if __name__ == "__main__":
    main()