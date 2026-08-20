"""Phase 4 real-data detour — manual check script, not a pytest test.

Real statement PDFs are deliberately never committed to this repo (see
parse_boa_statement.py's docstring), so there's no fixture to assert
against — this is a script YOU run locally, pointing it at whatever real
PDF you currently have on disk, to see how the Phase 4 categorization
pipeline (rules.py -> llm_fallback.py) actually performs on real bank
data instead of the clean mock CSV.

Usage:
  1. Drop your statement PDF somewhere local (data/statements/ is
     gitignored — see .gitignore — so it's a safe place to keep it).
  2. Edit STATEMENT_PATH below to point at it.
  3. Run:  python3.11 scripts/check_boa_statement.py

What it does, in order, per transaction:
  1. Try categorize_by_rules() — cheap, deterministic, no network call.
  2. If that returns None, fall back to categorize_with_llm() — this is
     the JSON-schema-constrained call verified earlier (Ollama `format=`
     or Anthropic, depending on LLM_PROVIDER in .env).
  3. If BOTH return None, the row is flagged UNCATEGORIZED.

The summary at the end reports rule-hit rate vs LLM-fallback rate vs
still-uncategorized rate. A high LLM-fallback rate on merchants that keep
recurring is a signal to add a new pattern to rules.py instead of paying
for an LLM call every time you re-run this.
"""

from __future__ import annotations

from pathlib import Path

from src.categorization.llm_fallback import categorize_with_llm
from src.categorization.rules import categorize_by_rules
from src.ingestion.parse_boa_statement import parse_statement

# ---- Edit this to point at your real statement PDF ----
STATEMENT_PATH = Path("data/statements/your_statement.pdf")
# ---------------------------------------------------------


def run_checks(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"No statement found at {pdf_path} — edit STATEMENT_PATH at the "
            "top of this script to point at your real PDF."
        )

    df = parse_statement(pdf_path)
    total = len(df)
    print(f"Parsed {total} transactions from {pdf_path.name}\n")

    if total == 0:
        print("Nothing to check — parse_statement() found zero transaction lines.")
        return

    rule_hits = 0
    llm_hits = 0
    uncategorized = []

    for _, row in df.iterrows():
        category = categorize_by_rules(row["merchant_name"], row["raw_description"])
        source = "rule"

        if category is None:
            category = categorize_with_llm(row["merchant_name"], row["raw_description"])
            source = "llm"

        if category is None:
            uncategorized.append(row)
            print(f"  [UNCATEGORIZED] {row['date']}  {row['merchant_name']!r}  ${row['amount']:.2f}")
            continue

        if source == "rule":
            rule_hits += 1
        else:
            llm_hits += 1

        print(f"  [{source:4}] {row['date']}  {row['merchant_name']!r}  ${row['amount']:.2f}  -> {category}")

    print("\n--- Summary ---")
    print(f"Total transactions:      {total}")
    print(f"Matched by rules:        {rule_hits}  ({rule_hits / total:.0%})")
    print(f"Matched by LLM fallback: {llm_hits}  ({llm_hits / total:.0%})")
    print(f"Still uncategorized:     {len(uncategorized)}  ({len(uncategorized) / total:.0%})")

    if uncategorized:
        print(
            "\nUncategorized rows above are candidates for new rules.py "
            "patterns — if the same merchant keeps landing here across "
            "statements, it's cheaper to add a rule than keep paying for "
            "an LLM call every run."
        )


if __name__ == "__main__":
    run_checks(STATEMENT_PATH)
