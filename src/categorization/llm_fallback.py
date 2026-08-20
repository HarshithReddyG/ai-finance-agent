"""Phase 4 — LLM fallback categorization.

Handles whatever categorize_by_rules() in rules.py couldn't confidently
resolve. Deliberately the LAST resort, not the first: rules are cheaper,
faster, and fully deterministic — this only runs on the leftover long
tail (ambiguous merchants, regional names not worth a hardcoded rule,
novel merchants the rule dictionary has never seen).

Provider-agnostic, matching LLM_PROVIDER in .env from Phase 1:
  LLM_PROVIDER=ollama    -> local open-source model via Ollama (default,
                             matches the project's "prefer open-source
                             LLMs" goal — free, runs entirely on your Mac)
  LLM_PROVIDER=anthropic -> Claude API (needs ANTHROPIC_API_KEY)

The category list is pulled directly from rules.py's CATEGORY_RULES,
never duplicated here — add a category to rules.py and the LLM prompt
picks it up automatically, so the two can't drift out of sync.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.categorization.rules import CATEGORY_RULES

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

_CACHE_PATH = Path(".cache/llm_categorization_cache.json")


def _load_cache() -> dict[str, str]:
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _valid_categories() -> list[str]:
    return list(CATEGORY_RULES.keys())


# Discovered 2026-08-20: tested against a real (mock-data) edge case —
# "Global Overseas Traders Ltd" / "INTL PURCHASE GLOBAL OVERSEAS TRADERS"
# — an unfamiliar import/goods merchant, ground truth Shopping. The model
# consistently (5/5 calls, temperature=0) answered Travel instead, purely
# off the words "international"/"overseas"/"global" in the merchant name
# and description — a surface-level keyword association, not a reasoned
# judgment about what was actually purchased. This note targets that
# general failure mode (any unfamiliar "international-sounding" merchant),
# not just this one company name, since the same bias would misfire on
# any future rare foreign merchant selling ordinary goods.
_DISAMBIGUATION_NOTES = (
    "Notes to avoid a common mistake: the words \"international\", "
    "\"overseas\", \"global\", or \"foreign\" appearing in a merchant name "
    "or description are NOT by themselves evidence of Travel. Travel means "
    "an actual transportation, lodging, or travel-booking merchant (e.g. "
    "an airline, hotel, car rental company, or travel agency). An "
    "unfamiliar international-sounding merchant that appears to sell "
    "goods should be categorized based on what was purchased (e.g. "
    "Shopping), not assumed to be Travel just because its name sounds "
    "foreign."
)


def _build_prompt(merchant_name: str, raw_description: str, categories: list[str]) -> str:
    category_list = "\n".join(f"- {c}" for c in categories)
    return (
        "You are categorizing a single bank transaction for a personal "
        "finance app. Pick exactly ONE category from this list — respond "
        "with ONLY the category name, nothing else, no punctuation, no "
        "explanation:\n\n"
        f"{category_list}\n\n"
        f"{_DISAMBIGUATION_NOTES}\n\n"
        f"Merchant name: {merchant_name}\n"
        f"Raw statement description: {raw_description}\n\n"
        "Category:"
    )


def _call_ollama(prompt: str, categories: list[str]) -> str:
    """Call Ollama with a JSON schema constraint, not a plain-text ask.

    A smaller model like phi3:mini will often ignore a "respond with only
    the category name" instruction and add an explanation anyway — asking
    more firmly doesn't fix that. Ollama's `format` parameter constrains
    the model's output at the decoding level to only ever produce JSON
    matching this schema, so it's structurally unable to ramble; there's
    nowhere in a `{"category": "..."}` response for extra prose to go.
    """
    import ollama

    schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": categories},
        },
        "required": ["category"],
    }

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=schema,
        options={"temperature": 0},  # deterministic-ish; less room to wander
    )
    parsed = json.loads(response["message"]["content"])
    return parsed["category"]


def _call_anthropic(prompt: str, categories: list[str]) -> str:
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_llm(prompt: str, categories: list[str]) -> str:
    if LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt, categories)
    if LLM_PROVIDER == "ollama":
        return _call_ollama(prompt, categories)
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r} (expected 'ollama' or 'anthropic')")


def categorize_with_llm(merchant_name: str, raw_description: str = "") -> str | None:
    """Ask the configured LLM to pick a category.

    Returns None if the model's answer isn't an exact match against a
    known category — an unrecognized answer is treated as a failure to
    categorize, never silently accepted as a new, uncontrolled category.
    """
    cache_key = f"{merchant_name}|{raw_description}".lower().strip()
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    categories = _valid_categories()
    prompt = _build_prompt(merchant_name, raw_description, categories)

    raw_answer = _call_llm(prompt, categories).strip()

    match = next((c for c in categories if c.lower() == raw_answer.lower()), None)

    if match is not None:
        cache[cache_key] = match
        _save_cache(cache)

    return match