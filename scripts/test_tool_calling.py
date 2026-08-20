"""Phase 7 proof-of-concept — does tool calling actually work before we
build the full agent loop around it?

Deliberately minimal: ONE tool (get_category_totals, already built and
tested in tools.py), ONE question, and every step of the round trip
printed so you can SEE the mechanism instead of trusting a black box:

  1. We send the model a question plus a description of one function it
     can call (name, purpose, parameter schema — no code, just a
     description).
  2. If the model decides it needs real data, its response contains a
     tool_use content block instead of (or alongside) plain text — a
     structured "please run this function with these arguments"
     request, not a text guess at the answer.
  3. WE run the real Python function (not the model) and get a real
     number back from the database.
  4. We hand that real result back to the model as a new message, and
     ask it to continue — this second response is the actual answer,
     now grounded in a real number instead of the model's guess.

This is the smallest possible test of that mechanism. If this works,
the full agent loop (all 6 tools, multi-turn, Phase 7's next file) is
just this same pattern repeated in a loop. If it doesn't work here,
there's no point building the bigger loop around it yet.

Using Anthropic here (not Groq/Ollama) — no local install cost either
way (the `anthropic` package is a ~2MB HTTP client, same category as
`groq` or `requests`, not a downloaded model), and this reuses the same
forced-tool-call mechanism already built and tested for Phase 4's
llm_fallback.py, just via messages.create() instead of a bare text ask.

Setup before running:
  1. Add ANTHROPIC_API_KEY=<your key> to .env.
  2. ./venv/bin/pip install anthropic   (if not already installed)

Run: ./venv/bin/python3.11 scripts/test_tool_calling.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from anthropic import Anthropic

from src.agent.tools import get_category_totals

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

# Same idea as Ollama's `format=` JSON schema and Anthropic's forced
# tool_choice from Phase 4 — every provider's "structured output"
# mechanism boils down to the same thing: describe the exact shape you
# want back, don't just ask nicely in plain English.
TOOLS = [
    {
        "name": "get_category_totals",
        "description": "Get total spend per category, optionally scoped to a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Start date, inclusive, as YYYY-MM-DD. Omit for no lower bound.",
                },
                "end": {
                    "type": "string",
                    "description": "End date, inclusive, as YYYY-MM-DD. Omit for no upper bound.",
                },
            },
            "required": [],
        },
    }
]

QUESTION = "How much have I spent on Restaurants in total?"


def main() -> None:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    messages = [{"role": "user", "content": QUESTION}]

    print(f"Model: {MODEL}")
    print(f"Question: {QUESTION!r}\n")

    # --- Round 1: give the model the question + the one tool it can use ---
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=messages,
        tools=TOOLS,
    )

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use_block is None:
        text_block = next((b for b in response.content if b.type == "text"), None)
        print("Model answered directly, without asking for the tool:")
        print(text_block.text if text_block else "(no text either)")
        print(
            "\n(That's a bad sign for this question specifically — it has "
            "no way to know your real spending without calling the tool, "
            "so a direct answer here means it guessed.)"
        )
        return

    arguments = tool_use_block.input  # already a parsed dict, not a JSON string
    print(f"Model requested a tool call: {tool_use_block.name}({arguments})")

    # --- We run the REAL function — the model never touches the database ---
    result = get_category_totals(**arguments)
    restaurants = next((row for row in result if row["category"] == "Restaurants"), None)
    print(f"Real result from the database: {restaurants}\n")

    # --- Round 2: hand the real result back, ask the model to finish ---
    messages.append({"role": "assistant", "content": response.content})
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_block.id,
                "content": json.dumps(result),
            }
        ],
    })

    final_response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=messages,
        tools=TOOLS,
    )
    final_text_block = next((b for b in final_response.content if b.type == "text"), None)
    print(f"Model's final answer, grounded in the real data:\n{final_text_block.text}")


if __name__ == "__main__":
    main()
