"""Phase 4 (real-data detour) — Parse an American Express credit card
statement PDF into our canonical transaction schema.

Bank-specific, same reasoning as parse_boa_statement.py: Amex's layout is
NOT BoA's layout, so it needs its own adapter rather than trying to force
one regex to fit two different statement formats. The differences that
matter for the parsing logic here:

  - Dates already carry the year (`06/05/26`), unlike BoA which needs the
    statement period text to infer the year separately.
  - Amounts are `$12.34` for a charge (spend) and `-$100.00` for a
    payment/credit — sign is on the amount itself, not a separate column.
    Mapped straight onto our Plaid-style convention (positive = spend,
    negative = payment/credit) with no extra translation needed.
  - There's no reference number at all. Uniqueness comes from hashing
    date + description + amount together instead (see the BoA parser's
    real collision bug for why hashing the description in particular
    matters — a bare reference-number-style field can't be trusted to be
    unique on its own).
  - Each transaction can spread across MULTIPLE lines: the first line has
    the date/description/amount, any following line(s) are pure noise
    (phone numbers, "RESTAURANT"/"DISCOUNT STORE" category tags, or for
    one travel purchase, several lines of flight detail) until the next
    line that starts with a date. The regex only ever matches a line
    STARTING with a date, so continuation lines are automatically
    ignored — no separate "is this a continuation line" check needed.

Output columns match parse_boa_statement.py's, so both feed the same
load_transactions.py without any special-casing.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

# Matches a transaction line like:
#   "06/05/26 AplPay ARCO#02134M & S ARCO AM SAN JOSE CA $33.15"
#   "06/06/26* MOBILE PAYMENT - THANK YOU -$100.00"
# The optional "*" marks a posting-date-only payment line (per the
# statement's own "*Indicates posting date" legend) — not meaningful
# for our schema, just consumed and discarded. "AplPay " is likewise
# optional (some charges are card-not-present / online, no Apple Pay
# prefix at all).
TRANSACTION_LINE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\*?\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<sign>-)?\$(?P<amount>[\d,]+\.\d{2})$"
)

ACCOUNT_ENDING = re.compile(r"Account Ending(\S+)")


def find_account_last4(full_text: str) -> str:
    match = ACCOUNT_ENDING.search(full_text)
    if not match:
        raise ValueError("Could not find 'Account Ending...' text to determine the account.")
    digits = re.sub(r"\D", "", match.group(1))
    return digits[-4:]


def parse_statement(pdf_path: Path) -> pd.DataFrame:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    last4 = find_account_last4(full_text)

    rows = []
    for line in full_text.splitlines():
        match = TRANSACTION_LINE.match(line.strip())
        if not match:
            continue  # section headers, totals, continuation lines — not a transaction

        tdate = datetime.strptime(match["date"], "%m/%d/%y").date()
        description = " ".join(match["desc"].split())
        amount = float(match["amount"].replace(",", ""))
        if match["sign"] == "-":
            amount = -amount

        # No reference number on Amex statements at all, unlike BoA — hash
        # date + description + amount together for a stable, unique ID.
        id_hash = hashlib.sha1(f"{tdate.isoformat()}|{description}|{amount}".encode()).hexdigest()[:12]

        rows.append({
            "transaction_id": f"amex_{last4}_{id_hash}",
            "account_id": f"amex_cc_{last4}",
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
    parser = argparse.ArgumentParser(description="Parse an Amex credit card statement PDF.")
    parser.add_argument("pdf_path", type=str)
    parser.add_argument("--out", type=str, default="data/real_transactions_amex.csv")
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
