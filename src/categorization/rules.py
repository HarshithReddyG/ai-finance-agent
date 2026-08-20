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
        "fresh market",
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
        "shell", "chevron", "exxon", "mobil", "bp", "76", "arco", "qt",
    ],
    "Convenience Store": [
        "7-eleven", "circle k", "maverik", "love's", "gas stop",
        "travel stop",
    ],
    "Transportation": [
        "uber", "lyft", "metro transit", "parking", "toll",
        "car wash", "laz pkg", "city of santa monica",
    ],
    "Shopping": [
        "amazon", "target", "best buy", "nike", "ebay", "etsy",
        "home depot", "ikea",
        "ae retail", "hugo boss", "express #", "legends outlet",
        "wal-mart", "ups store", "liquor", "totalwine", "back market",
        "backmarket",
        "boss m outlet", "hollywood tshirt", "jockey outlet", "groupon",
        "ua_178", "printwithme",
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
        "verizon", "at&t", "t-mobile", "visible",
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
    ],
    "Fees": [
        "maintenance fee", "atm fee", "overdraft fee", "motor vehicle dept",
    ],
    "Transfers": [
        "transfer to savings", "transfer from checking", "venmo", "zelle",
        "atm payment", "payment from chk",
    ],
}

_NOISE_PATTERNS = [
    r"^SQ \*",
    r"^POS DEBIT\s*",
    r"\s*WEB PYMT$",
    r"#\d{3,5}",
    r"\b[A-Z]{2}\b$",
]

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
    """Return a category if a known merchant pattern matches, else None."""
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