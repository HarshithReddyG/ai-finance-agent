# Phase 2 — Mock Transaction Data

## Goal
Produce a realistic, reproducible synthetic transaction history to build
every later phase against, without needing Plaid yet.

## What was built
`src/ingestion/generate_mock_transactions.py` generates ~13 months of
transactions across three accounts (checking, credit card, savings) and
writes:
- `data/mock_transactions.csv` — the raw ingest file (no category column).
- `data/mock_transactions_eval.csv` — ground truth (category, recurring,
  anomaly) used only to score later phases, never fed into them.

## Key design decisions
- Plaid sign convention: positive = money out, negative = money in.
- `--seed` makes runs reproducible.
- Recurring charges (rent, subscriptions, gym, phone, internet, insurance,
  biweekly paycheck, monthly checking->savings transfer) run on real
  schedules, not just flags, so Phase 5 has real signal to detect.
- Four anomaly types are injected: duplicate_charge,
  large_one_off_purchase, new_rare_merchant, category_spending_spike.
- Transfers get their own category and net to $0.00 across both legs.

## Validation (fill in from your own run)
Result: `[N]` transactions generated, `[N]` recurring, `[N]` anomalies,
`[N]/[N]` tests passing.

## Known simplifications
- One fictitious user, one set of three accounts.
- Everyday spending frequency/amounts are hand-picked, not statistically
  modeled.