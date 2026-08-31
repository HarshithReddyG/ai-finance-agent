"""Diagnostic — why did the LLM fallback categorize "Global Overseas
Traders Ltd" as Travel instead of Shopping (its ground-truth category)?

Not a pipeline file — a one-off investigation script. Bypasses the
categorization cache entirely (categorize_with_llm() would just return
the already-cached wrong answer) and calls _call_llm() directly, several
times, so we can see:
  1. Which provider/model is actually configured (LLM_PROVIDER defaults
     to "ollama" if unset in .env — easy to be calling a different model
     than you think you are).
  2. The EXACT prompt text being sent — if it's ambiguous, that's a
     prompt problem, fixable for every future merchant, not just this one.
  3. Whether the answer is a consistent bias (same wrong answer every
     time -> the model genuinely associates this input with Travel) or
     flaky (different answers across calls -> temperature/sampling
     issue, or the category list itself is ambiguous for this merchant).

"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.categorization.llm_fallback import (
    ANTHROPIC_MODEL,
    LLM_PROVIDER,
    OLLAMA_MODEL,
    _build_prompt,
    _call_llm,
    _valid_categories,
)

MERCHANT_NAME = "Global Overseas Traders Ltd"
RAW_DESCRIPTION = "INTL PURCHASE GLOBAL OVERSEAS TRADERS"
N_REPEATS = 5


def main() -> None:
    print(f"LLM_PROVIDER = {LLM_PROVIDER!r}")
    if LLM_PROVIDER == "ollama":
        print(f"OLLAMA_MODEL = {OLLAMA_MODEL!r}")
    elif LLM_PROVIDER == "anthropic":
        print(f"ANTHROPIC_MODEL = {ANTHROPIC_MODEL!r}")

    categories = _valid_categories()
    prompt = _build_prompt(MERCHANT_NAME, RAW_DESCRIPTION, categories)

    print(f"\nCategory list has {len(categories)} entries: {categories}")
    print("\n--- Exact prompt sent to the model ---")
    print(prompt)
    print("--- end prompt ---\n")

    print(f"Calling the LLM {N_REPEATS} times directly (bypassing the cache)...\n")
    answers = []
    for i in range(1, N_REPEATS + 1):
        try:
            raw_answer = _call_llm(prompt, categories).strip()
        except Exception as exc:  # noqa: BLE001 - diagnostic script, show any failure as-is
            raw_answer = f"<ERROR: {exc!r}>"
        answers.append(raw_answer)
        print(f"  call {i}: {raw_answer!r}")

    unique = set(answers)
    print(f"\n{len(unique)} distinct answer(s) across {N_REPEATS} calls: {unique}")
    if len(unique) == 1 and "Travel" in unique:
        print(
            "\nConsistent, not flaky: the model reliably reads this specific "
            "prompt as Travel. That points at the prompt/category-list "
            "framing (or the model's general capability) rather than "
            "sampling randomness — a smaller/weaker model can genuinely "
            "misread 'INTL PURCHASE' as travel-related regardless of "
            "temperature=0, since there's no true randomness left to vary."
        )
    elif len(unique) > 1:
        print(
            "\nFlaky: different answers across calls despite temperature=0 "
            "in the Ollama options (or Anthropic having no explicit "
            "temperature override here) — worth checking whether "
            "temperature is actually being honored by the provider/model."
        )


if __name__ == "__main__":
    main()
