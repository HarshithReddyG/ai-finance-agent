"""Phase 3 — Load mock_transactions.csv into the database.

Reads data/mock_transactions.csv (Phase 2's output) and inserts rows into
the accounts and transactions tables defined in src/storage/schema.py.
This is the script that actually connects Phase 2's CSV to Phase 3's
database — everything before this point only produced or defined things
on disk, nothing loaded data into the DB yet.

Idempotent: safe to re-run as many times as you want. Rows are matched
by primary key and updated in place (via SQLAlchemy's Session.merge())
rather than duplicated or erroring on a second run.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.storage.db import get_session, init_db
from src.storage.schema import Account, Transaction


def load_accounts(session, df: pd.DataFrame) -> int:
    accounts = df[["account_id", "account_type"]].drop_duplicates()
    count = 0
    for _, row in accounts.iterrows():
        account = Account(account_id=row["account_id"], account_type=row["account_type"])
        session.merge(account)
        count += 1
    return count


def load_transactions(session, df: pd.DataFrame) -> int:
    count = 0
    for _, row in df.iterrows():
        txn = Transaction(
            transaction_id=row["transaction_id"],
            account_id=row["account_id"],
            date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
            merchant_name=row["merchant_name"],
            raw_description=row.get("raw_description"),
            amount=float(row["amount"]),
            currency=row.get("currency", "USD"),
            pending=bool(row["pending"]),
            category=None,  # not assigned yet — that's Phase 4's job
        )
        session.merge(txn)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Load mock_transactions.csv into the database.")
    parser.add_argument("--csv-path", type=str, default="data/mock_transactions.csv")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found at {csv_path} — run Phase 2's generator first.")

    init_db()  # make sure the tables exist before we try to insert into them

    df = pd.read_csv(csv_path)

    with get_session() as session:
        n_accounts = load_accounts(session, df)
        n_transactions = load_transactions(session, df)
        session.commit()

    print(f"Loaded {n_accounts} accounts and {n_transactions} transactions from {csv_path}")


if __name__ == "__main__":
    main()