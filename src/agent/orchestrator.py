"""Phase 7 — the agent orchestration loop.

Generalizes scripts/test_tool_calling.py's one-tool proof of concept
into the real thing: all six tools.py functions available, and a
genuine LOOP instead of a hardcoded two-round script — Claude might
answer directly, request one tool, request several tools in the same
turn (e.g. "compare my spending trend and flag anything weird" needs
both get_category_trends and get_anomalies), or chain multiple rounds
of tool calls before it has enough to answer. The loop keeps going,
executing whatever real functions are requested and feeding real
results back, until a response comes back with no tool_use blocks at
all — that's the final answer.

TOOL_REGISTRY is the single source of truth mapping a tool NAME (what
Claude sees and calls by) to both its schema (what Claude sees) and the
real Python function (what actually runs) — one dict entry, not two
separate lists that could drift out of sync, same principle as
CATEGORY_RULES being the one place category names are defined.

MAX_TOOL_ROUNDS is a safety cap, not a tuning knob to raise casually —
if a question genuinely needs more than 5 rounds of tool calls, that's
more likely a sign of a confused model looping than a legitimately
complex question.

Every tool failure is caught and reported back to Claude as a tool
result (an {"error": ...} dict), not raised — an unhandled exception
would crash the whole conversation over one bad tool call; handing the
error back lets Claude explain the failure to the user, or try a
different approach, instead.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from anthropic import Anthropic

from src.agent import tools as tool_functions

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
MAX_TOOL_ROUNDS = 5

TOOL_REGISTRY = {
    "get_category_totals": {
        "function": tool_functions.get_category_totals,
        "schema": {
            "name": "get_category_totals",
            "description": "Total spend per category, highest first. Optionally scoped to a date range.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Start date YYYY-MM-DD, inclusive. Omit for no lower bound."},
                    "end": {"type": "string", "description": "End date YYYY-MM-DD, inclusive. Omit for no upper bound."},
                },
                "required": [],
            },
        },
    },
    "get_monthly_totals": {
        "function": tool_functions.get_monthly_totals,
        "schema": {
            "name": "get_monthly_totals",
            "description": "Total spend per calendar month, chronological. Optionally scoped to a date range.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Start date YYYY-MM-DD, inclusive. Omit for no lower bound."},
                    "end": {"type": "string", "description": "End date YYYY-MM-DD, inclusive. Omit for no upper bound."},
                },
                "required": [],
            },
        },
    },
    "get_category_trends": {
        "function": tool_functions.get_category_trends,
        "schema": {
            "name": "get_category_trends",
            "description": "Which spending categories are trending up or down recently (average of the last 3 months vs. the 3 months before that).",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    },
    "get_recurring_charges": {
        "function": tool_functions.get_recurring_charges,
        "schema": {
            "name": "get_recurring_charges",
            "description": "Known recurring bills, subscriptions, and income (rent, streaming, paycheck, etc.), as of the last time the recurring-charge detector was run.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    },
    "get_anomalies": {
        "function": tool_functions.get_anomalies,
        "schema": {
            "name": "get_anomalies",
            "description": "Everything currently flagged as unusual: category spending spikes, large one-off purchases, duplicate charges, and rare/new merchants.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    },
    "compare_periods": {
        "function": tool_functions.compare_periods,
        "schema": {
            "name": "compare_periods",
            "description": "Category-by-category spend comparison between two date ranges.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "period1_start": {"type": "string", "description": "First period start date, YYYY-MM-DD."},
                    "period1_end": {"type": "string", "description": "First period end date, YYYY-MM-DD."},
                    "period2_start": {"type": "string", "description": "Second period start date, YYYY-MM-DD."},
                    "period2_end": {"type": "string", "description": "Second period end date, YYYY-MM-DD."},
                },
                "required": ["period1_start", "period1_end", "period2_start", "period2_end"],
            },
        },
    },
}

SCHEMAS = [entry["schema"] for entry in TOOL_REGISTRY.values()]


def _system_prompt() -> str:
    return (
        "You are a personal finance assistant. Answer the user's question "
        "using the provided tools to look up real data from their "
        "transaction database — never guess or estimate a number "
        f"yourself. Today's date is {date.today().isoformat()}; use it to "
        "resolve relative date references like 'last month' or 'this "
        "year' into actual YYYY-MM-DD dates when calling tools."
    )


def ask(question: str, verbose: bool = True) -> str:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages = [{"role": "user", "content": question}]

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_system_prompt(),
            messages=messages,
            tools=SCHEMAS,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return "\n".join(text_blocks)

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            entry = TOOL_REGISTRY.get(block.name)
            if entry is None:
                result = {"error": f"Unknown tool: {block.name}"}
            else:
                if verbose:
                    print(f"  [round {round_num}] calling {block.name}({block.input})")
                try:
                    result = entry["function"](**block.input)
                except Exception as exc:  # noqa: BLE001 - report the failure to Claude, don't crash the loop
                    result = {"error": str(exc)}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return (
        f"Gave up after {MAX_TOOL_ROUNDS} tool-calling rounds without a "
        "final answer — something's likely looping. Check the printed "
        "tool calls above."
    )


def main() -> None:
    question = " ".join(sys.argv[1:]) or input("Ask a question about your finances: ")
    answer = ask(question)
    print(f"\n{answer}")


if __name__ == "__main__":
    main()