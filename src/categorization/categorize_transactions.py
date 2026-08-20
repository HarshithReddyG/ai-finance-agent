"""Phase 4 — Apply categorization to transactions already in the database.

load_transactions.py (Phase 3) intentionally inserts every row with
category=None — categorization wasn't built yet at that point. rules.py
and llm_fallback.py (this phase) exist and are verified working, but
nothing has connected them to the DB rows until now.

Idempotent by design: only selects transactions where category IS NULL,
so re-running this after new transactions arrive (a fresh mock CSV load,
or later a Phase 10 Plaid sync) only categorizes what's new — it never
redoes or overwrites rows already categorized.

A transaction that neither tier can resolve (rules miss AND the LLM's
answer doesn't match a known category) is left as category=None on
purpose, not guessed at — same "never silently accept an unrecognized
answer" principle as categorize_with_llm() itself. Those rows show up in
the "still uncategorized" bucket of the summary so they can be reviewed
and turned into new rules.py patterns.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `from src...` imports work whether this file is run directly
# (`python3.11 src/categorization/categorize_transactions.py`) or as a
# module (`python3.11 -m src.categorization.categorize_transactions`).
# Direct invocation only puts this file's own folder on sys.path, not the
# repo root, so `import src` fails with ModuleNotFoundError unless the
# repo root is added here first.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.categorization.llm_fallback import categorize_with_llm
from src.categorization.rules import categorize_by_rules
from src.storage.db import get_session
from src.storage.schema import Transaction


def categorize_pending(session) -> dict[str, int]:
    pending = session.query(Transaction).filter(Transaction.category.is_(None)).all()

    rule_hits = 0
    llm_hits = 0
    still_uncategorized = []

    for txn in pending:
        category = categorize_by_rules(txn.merchant_name, txn.raw_description or "")
        source = "rule"

        if category is None:
            category = categorize_with_llm(txn.merchant_name, txn.raw_description or "")
            source = "llm"

        if category is None:
            still_uncategorized.append(txn)
            continue

        txn.category = category
        if source == "rule":
            rule_hits += 1
        else:
            llm_hits += 1

    return {
        "pending": len(pending),
        "rule_hits": rule_hits,
        "llm_hits": llm_hits,
        "uncategorized": still_uncategorized,
    }


def main() -> None:
    with get_session() as session:
        stats = categorize_pending(session)
        session.commit()

    pending = stats["pending"]
    if pending == 0:
        print("Nothing to categorize — every transaction already has a category.")
        return

    rule_hits = stats["rule_hits"]
    llm_hits = stats["llm_hits"]
    uncategorized = stats["uncategorized"]

    print(f"Processed {pending} uncategorized transactions")
    print(f"  Matched by rules:        {rule_hits}  ({rule_hits / pending:.0%})")
    print(f"  Matched by LLM fallback: {llm_hits}  ({llm_hits / pending:.0%})")
    print(f"  Still uncategorized:     {len(uncategorized)}  ({len(uncategorized) / pending:.0%})")

    if uncategorized:
        print("\nStill uncategorized (candidates for new rules.py patterns):")
        for txn in uncategorized:
            print(f"  {txn.date}  {txn.merchant_name!r}  ${txn.amount}")


if __name__ == "__main__":
    main()