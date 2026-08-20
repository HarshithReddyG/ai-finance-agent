"""Phase 4 (real-data detour) — Parse a Bank of America credit card
statement PDF into our canonical transaction schema.

This is deliberately bank-specific, not a general "any bank PDF" parser —
Bank of America's statement layout (column order, section headers like
"Payments and Other Credits" / "Purchases and Adjustments") is what the
regex below is built against. A different bank's PDF will need its own
version of this file; that's expected, not a bug — every real-world data
source needs its own small adapter, same as load_transactions.py is
specific to the mock CSV's columns.

Output columns intentionally match src/ingestion/load_transactions.py's
expected input EXCEPT:
  - account_id is a masked identifier (last 4 digits only), never the
    real card number.
  - merchant_name is identical to raw_description, because a raw
    statement (unlike Plaid, and unlike our mock CSV) doesn't give you a
    separate clean merchant name — that's a real limitation worth
    understanding, not something to fake.

This script does NOT load into db/finance.db. It only writes a CSV, kept
deliberately separate from the mock pipeline so it doesn't interfere with
Phase 5/6 validation against the mock ground-truth eval file.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

# Matches a transaction line like:
#   "04/27 04/28 UA_178_KANSAS CITY Kansas City KS 2223 0873 -41.52"
# Greedy `.+` for the description is deliberate: it consumes as much as
# possible, so stray digits embedded mid-description (e.g. "DE 0") don't
# get mistaken for the reference/account number — only the true trailing
# ref (4 digits), account (4 digits), and amount get peeled off the end.
TRANSACTION_LINE = re.compile(
    r"^(?P<tdate>\d{2}/\d{2})\s+(?P<pdate>\d{2}/\d{2})\s+(?P<desc>.+)\s+"
    r"(?P<ref>\d{4})\s+(?P<acct>\d{4})\s+(?P<amount>-?[\d,]+\.\d{2})$"
)

STATEMENT_PERIOD = re.compile(
    r"[A-Za-z]+ \d{1,2} - [A-Za-z]+ \d{1,2}, (\d{4})"
)


def find_statement_year(full_text: str) -> int:
    """Pull the statement year out of a line like 'April 28 - May 27, 2026'.

    Known limitation: a statement whose period crosses a calendar year
    (e.g. "Dec 28, 2025 - Jan 27, 2026") isn't handled — every transaction
    would get the same year. Not needed for a single monthly statement
    that stays within one year, which covers 11 of 12 months.
    """
    match = STATEMENT_PERIOD.search(full_text)
    if not match:
        raise ValueError("Could not find statement period text to determine the year.")
    return int(match.group(1))


def parse_statement(pdf_path: Path) -> pd.DataFrame:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    year = find_statement_year(full_text)

    rows = []
    for line in full_text.splitlines():
        match = TRANSACTION_LINE.match(line.strip())
        if not match:
            continue  # section headers, totals, page furniture — not a transaction

        tdate = datetime.strptime(f"{match['tdate']}/{year}", "%m/%d/%Y").date()
        description = " ".join(match["desc"].split())  # collapse extra whitespace
        amount = float(match["amount"].replace(",", ""))
        last4 = match["acct"]

        rows.append({
            # Includes last4 so IDs stay unique across DIFFERENT accounts —
            # date + ref alone can collide if you ever parse statements
            # from more than one account (e.g. two BoA cards) that happen
            # to share a reference number on the same date. Without this,
            # load_transactions.py's upsert-by-transaction_id would
            # silently merge two real, different transactions into one.
            "transaction_id": f"boa_{last4}_{tdate.isoformat()}_{match['ref']}",
            "account_id": f"boa_cc_{last4}",
            "account_type": "credit_card",
            "date": tdate.isoformat(),
            "merchant_name": description,   # no separate clean field available
            "raw_description": description,
            "amount": amount,
            "currency": "USD",
            "pending": False,
        })

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a BoA credit card statement PDF.")
    parser.add_argument("pdf_path", type=str)
    parser.add_argument("--out", type=str, default="data/real_transactions_boa.csv")
    args = parser.parse_args()

    df = parse_statement(Path(args.pdf_path))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    print(f"Parsed {len(df)} transactions -> {out_path}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Spend (positive amounts): ${df[df['amount'] > 0]['amount'].sum():,.2f}")
    print(f"Payments/credits (negative amounts): ${df[df['amount'] < 0]['amount'].sum():,.2f}")


if __name__ == "__main__":
    main()
