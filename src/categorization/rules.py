"""Phase 4 — Rule-based categorization (tried before any LLM call).

Rules below were expanded after testing against a real Bank of America
statement (not committed to this repo — real data stays out of git).
Real coverage went from 36% to a much higher number after this pass; see
the categories below for what was added and why.
"""

from __future__ import annotations

import re

CATEGORY_RULES: dict[str, list[str]] = {
    "Groceries": [
        "whole foods", "trader joe", "safeway", "kroger", "walmart",
        "costco", "aldi", "publix",
        "sun fresh", "midtown market", "sprouts farmers", "wholefds",
        "fresh market", "nob hill", "lucky #",
    ],
    "Restaurants": [
        "chipotle", "mcdonald", "olive garden", "panera", "subway",
        "chick-fil-a", "taco bell", "wendy", "doordash", "uber eats",
        "grubhub", "diner",
        "tst*",              # Toast POS — a restaurant-specific system,
                              # so this prefix alone is a strong signal
                              # (unlike "SQ *", which Square POS puts on
                              # every kind of small business, not just food).
        "grill", "smokehouse", "coldstone", "yogurtini", "nathans famous",
        "minsky's", "sultan mediterranean", "san antonio market",
        "charminar",
    ],
    "Coffee Shops": [
        "starbucks", "peet's", "peets", "dunkin", "coffee",
    ],
    "Gas & Fuel": [
        "shell", "chevron", "exxon", "bp", "76", "arco", "qt",
        "phillips 66",
        # NOT "mobil" on its own — real false positive found on real data:
        # "MOBILE PAYMENT - THANK YOU" (an Amex bill payment, nothing to
        # do with gas) contains "mobil" as a substring of "mobile", and at
        # 5 characters it clears MIN_LOOSE_MATCH_LENGTH, so it was loose-
        # matching here. "exxon" alone still catches ExxonMobil-branded
        # stations without the collision risk.
    ],
    "Convenience Store": [
        # Real travel-stop/convenience chains — distinct enough from a
        # pure gas station (no fuel-only branding) or a grocery store
        # (much smaller, quick-purchase focused) to warrant their own
        # category rather than being forced into either.
        "7-eleven", "circle k", "maverik", "love's", "gas stop",
        "travel stop",
    ],
    "Transportation": [
        "uber", "lyft", "metro transit", "parking", "toll",
        "car wash", "carwash",  # real statement text varies on the space
        "laz pkg", "city of santa monica",
    ],
    "Shopping": [
        "amazon", "target", "best buy", "nike", "ebay", "etsy",
        "home depot", "ikea",
        "ae retail", "hugo boss", "express #", "legends outlet",
        "wal-mart", "ups store", "liquor", "totalwine", "total wine",
        "back market", "backmarket",
        "boss m outlet", "hollywood tshirt", "jockey outlet", "groupon",
        "ua_178", "printwithme", "sports basement",
    ],
    "Entertainment": [
        "amc", "steam games", "bowling", "lucky strike", "bowlero",
    ],
    "Subscriptions": [
        "netflix", "spotify", "adobe", "nyt", "hulu", "disney+", "hbo max",
        "anthropic", "claude.ai", "jobright", "apple.com",
    ],
    "Utilities": [
        "water utility", "power & light", "comcast", "xfinity",
        "verizon", "at&t", "att* bill", "t-mobile", "visible",
        "boost mobile",
        # "at&t" (the brand rule above) never matches a real BoA statement's
        # own text for this — it prints "ATT* BILL PAYMENT", no ampersand.
    ],
    "Housing": [
        "apartments", "mortgage", "ysi*bellerive",
    ],
    "Insurance": [
        "state farm", "blue cross", "geico", "allstate", "progressive",
    ],
    "Healthcare": [
        "cvs", "walgreens", "medical clinic", "pharmacy",
    ],
    "Travel": [
        "delta air", "marriott", "airbnb", "united airlines", "hilton",
        "southwest",
        "national park", "state parks", "zion", "booking.c", "luxor",
        "inca inn", "arches national",
    ],
    "Personal Care": [
        "great clips", "supercuts", "salon",
    ],
    "Fitness": [
        "planet fitness", "la fitness", "equinox", "gym",
    ],
    "Income": [
        "payroll", "direct deposit",
        "cash rewards",  # credit card cashback credits — money coming back to you
    ],
    "Fees": [
        "maintenance fee", "atm fee", "overdraft fee", "motor vehicle dept",
    ],
    "Transfers": [
        "transfer to savings", "transfer from checking", "venmo", "zelle",
        # A real credit card statement's "payment" lines are you paying
        # your own card from your own checking account — that's a
        # transfer, not spending, same concept as the mock data's
        # checking->savings transfer.
        "atm payment", "payment from chk",
        "mobile payment",  # Amex's own wording for the same concept
    ],
}

_NOISE_PATTERNS = [
    r"^SQ \*",
    r"^POS DEBIT\s*",
    r"\s*WEB PYMT$",
    r"#\d{3,5}",
    r"\b[A-Z]{2}\b$",
]

# Patterns shorter than this are too easy to accidentally match inside an
# unrelated word (e.g. "bp" inside some random string), so they always
# require a word-boundary match, even in the merchant_name tier. Longer
# patterns are allowed a loose substring match there, since merchant_name
# is a controlled field and loose matching is what correctly catches
# compound brand names like "exxon" inside "exxonmobil".
MIN_LOOSE_MATCH_LENGTH = 4


def normalize_description(text: str) -> str:
    cleaned = text
    for pattern in _NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned.strip().lower()


def _matches(pattern: str, candidate: str, *, allow_loose: bool) -> bool:
    if allow_loose and len(pattern) >= MIN_LOOSE_MATCH_LENGTH:
        return pattern in candidate
    return re.search(rf"\b{re.escape(pattern)}\b", candidate) is not None


def categorize_by_rules(merchant_name: str, raw_description: str = "") -> str | None:
    """Return a category if a known merchant pattern matches, else None.

    Two-tier strategy, checked in this order:
      1. merchant_name, across every category. Patterns of at least
         MIN_LOOSE_MATCH_LENGTH characters get a loose substring match
         (correctly catches "exxon" inside "exxonmobil"); shorter
         patterns still require a word-boundary match even here, since a
         short pattern is too likely to collide with something unrelated.
      2. Only if step 1 finds nothing: fall back to normalized
         raw_description, always with a word-boundary match — that field
         can contain uncontrolled text (e.g. a random city name), where
         even a "long enough" pattern can coincidentally appear inside an
         unrelated word (the "wendy" inside "Wendyville" failure mode).

    Note: for data sources that don't provide a separate clean merchant
    field (e.g. a parsed real bank statement, where merchant_name and
    raw_description end up identical), tier 1 is effectively the only
    tier that ever runs — which is exactly why short patterns need the
    word-boundary safety net in both tiers, not just tier 2.
    """
    merchant_candidate = merchant_name.lower()

    for category, patterns in CATEGORY_RULES.items():
        for pattern in patterns:
            if _matches(pattern, merchant_candidate, allow_loose=True):
                return category

    description_candidate = normalize_description(raw_description)
    for category, patterns in CATEGORY_RULES.items():
        for pattern in patterns:
            if _matches(pattern, description_candidate, allow_loose=False):
                return category

    return None
