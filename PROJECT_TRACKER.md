# AI Personal Finance Agent — Project Tracker

This file is the single source of truth for project state across sessions.
Keep it in your repo root (or wherever you keep this project) and re-upload
it at the start of any future session so your mentor can pick up exactly
where you left off. Update the "Status" column and the Session Log as you go.

Last updated: 2026-08-20

---

## 1. Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                              │
│   Mock CSV (Phase 2)  ─────────────────►  Plaid Sandbox API (Phase 10) │
└───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 INGESTION & NORMALIZATION LAYER (Phase 2/10)           │
│  - CSV parser / Plaid client wrapper                                   │
│  - Schema normalization (date, merchant, amount, account, currency)    │
│  - Deduplication + validation                                          │
└───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER (Phase 3)                           │
│   SQLite (local, default)  ──upgrade path──►  Postgres (cloud)         │
│   Tables: accounts · transactions · categories · recurring · anomalies │
└───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│               CATEGORIZATION ENGINE (Phase 4)                          │
│  Rule-based merchant/regex matcher  →  LLM fallback for unmatched rows │
│  (open-source LLM: Llama / Mistral / Phi, via Ollama or HF Inference)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
              ┌──────────────────────┴───────────────────────┐
              ▼                                               ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│   ANALYTICS ENGINE (Phase 5)   │             │  ANOMALY DETECTION (Phase 6)  │
│  - Monthly / category totals   │             │  - Z-score / IQR outliers     │
│  - Trend & spike detection     │             │  - New / unusual merchants    │
│  - Recurring subscription find │             │  - Duplicate charge detection │
└───────────────┬─────────────────┘             └────────────────┬───────────────┘
                └──────────────────────┬──────────────────────---┘
                                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     AI AGENT LAYER (Phase 7)                           │
│   LLM orchestrator with tool-calling, e.g.:                            │
│     tools = [ query_db, get_category_totals, get_anomalies,            │
│               get_recurring_charges, compare_periods ]                 │
│   → produces natural-language, explainable financial answers           │
└───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      INTERFACE LAYER (Phase 8)                         │
│         CLI (Typer / argparse)   ◄── or ──►   Streamlit Web UI         │
└────────────────────────────────────────────────────────────────────────┘

  Cross-cutting concerns (apply to every layer):
   • Cloud Integration — Google Colab notebooks mirror local scripts (Phase 9)
   • Security — .env for secrets, mock data only, never store real credentials
   • Documentation — README + architecture notes updated every phase
```

---

## 2. Phase Roadmap

| # | Phase | Goal | Key Tools | Status |
|---|-------|------|-----------|--------|
| 1 | Repository Setup | Scaffold repo structure, virtualenv, config, README skeleton | GitHub, Python, `venv`/`poetry` | Done |
| 2 | Mock Transaction Data | Generate realistic mock CSV transactions (multiple accounts, merchants, categories, recurring charges, a few anomalies) | Python, `faker`, `pandas` | Done |
| 3 | Database Schema + Storage | Design SQLite schema, build ingestion script CSV → DB | `sqlite3`, SQLAlchemy | Done |
| 4 | Categorization Engine | Rule-based categorizer + LLM fallback for unmatched merchants | regex, open-source LLM (Ollama) / Anthropic API | Done — see notes below on the Ollama → Anthropic switch |
| 5 | Analytics | Monthly totals, category trends, recurring subscription detection | `pandas`, SQL queries | Done |
| 6 | Anomaly Detection | Statistical outlier detection, new-merchant flags, duplicate-charge checks | `pandas`, `scipy`/`numpy`-style IQR logic | Done |
| 7 | AI Agent Layer | LLM agent with tool-calling over the analytics/anomaly functions, explainable answers | Anthropic API tool-calling (Claude Haiku 4.5) | In Progress — core loop working, validated live |
| 8 | Interface | CLI or Streamlit UI for natural-language Q&A | Typer or Streamlit | Not Started |
| 9 | Cloud Integration | Port pipeline into Google Colab notebooks for heavy compute / demoing | Google Colab | Not Started |
| 10 | Plaid Sandbox Integration (optional) | Swap mock CSV for live Plaid Sandbox transactions | Plaid Sandbox API | Not Started |
| 11 | Final Demo + Docs + Resume Packaging | Polish README, architecture doc, demo script/video, resume bullet points | Markdown, screen recording | Not Started |

Status values to use: `Not Started` → `In Progress` → `Blocked` → `Done`.

---

## 3. Current State

- **Active phase:** Phase 7 — AI Agent Layer. Core tool-calling loop is built and has been validated with a live run against the real Anthropic API and the real (mock) database — see Session Log below for the exact question/answer tested.
- **CODING WORKFLOW (important, read every session):** Learning project — explain the design decision first, then give the code for one file, then let the user run/verify it before moving to the next file. This stayed the working pattern through Phases 4-7; each analytics/anomaly/agent file was explained, delivered, and verified (either against `data/mock_transactions_eval.csv` ground truth, or with a mocked-client test of the real code path) before moving to the next.
- **NO per-phase docs/phase_notes files** — `docs/architecture.md` and this tracker are enough.
- **Database engine decision:** SQLite, unchanged. Schema lives in `src/storage/schema.py` (accounts, transactions, recurring_series, anomalies tables) via SQLAlchemy ORM.
- **LLM provider decision — changed this session, important:** `.env`'s `LLM_PROVIDER` originally defaulted to `ollama` (`phi3:mini` locally). Diagnosed a real failure: the Phase 4 LLM fallback consistently (5/5 calls) mis-categorized an unfamiliar merchant ("Global Overseas Traders Ltd," an international goods importer) — first as `Travel`, then as `Income` after a prompt fix — always confidently, never flaky. Conclusion: not a prompt problem, `phi3:mini` (3.8B params) is genuinely too weak for judgment calls on merchants it has no training knowledge of. Also ruled out fixing this by installing a bigger local Ollama model — the user's MacBook Air only has ~10GB free disk, not enough headroom to comfortably run/download a bigger model. **Decision: switched to the Anthropic API (`claude-haiku-4-5`) for both the Phase 4 LLM fallback and the Phase 7 agent.** Cost checked and is a non-issue: ~$1/M input, $5/M output tokens, so a $5 balance covers 1,000+ Phase 7 questions with wide margin. `_call_anthropic()` in `llm_fallback.py` was upgraded to use forced tool-use (not plain free text) for the same reliability reason the Ollama path already used a JSON schema. A Groq API key also exists in `.env` as a free-tier backup/alternative but is not currently used by any code path.
  - **Known limitation carried forward, not yet re-tested:** the one real miscategorized transaction (Global Overseas Traders Ltd) was corrected directly in the DB with a manual `UPDATE` (`category = 'Shopping'`) rather than by re-running the LLM fallback end-to-end with the new Anthropic path — worth a real re-run through `categorize_transactions.py` later to confirm Anthropic gets it right from scratch, not just to trust the manual patch.
  - **Security note:** an Anthropic API key was accidentally pasted into chat during this session (inside a `curl` command) and was flagged for immediate rotation. Treat this as resolved once confirmed rotated — don't re-surface it as a live concern in future sessions, but the general lesson (never paste real keys into chat, use `.env` + shell env vars only) is worth remembering.
- **Workflow decision:** Colab still deferred, never ended up needed — Ollama/Anthropic API calls run fine locally on the Mac.
- **Next action:** decide whether to keep extending Phase 7 (multi-turn conversation memory beyond a single question, more robust error messages, maybe a `get_transaction_detail` tool for drilling into a specific flagged transaction) or move on to Phase 8 (CLI/Streamlit interface) with the current single-question `orchestrator.py` as-is. Either way: **all work since the Phase 1 scaffold commit is still uncommitted in git** (`git log` only shows the one initial commit) — worth committing Phases 2-7 before going further, and there are no automated tests yet for storage/categorization/analytics/anomaly/agent (only `test_setup.py` and `test_mock_data_generator.py` exist).
- **Open questions / blockers:** none blocking — see "Next action" above for the two real housekeeping items (git commits, test coverage) worth addressing soon.

---

## 4. Session Log

Add one entry per working session so future sessions have context.

| Date | Session Summary | Phase Touched | Next Step |
|------|------------------|----------------|-----------|
| 2026-08-19 | Kickoff: architecture diagram + phase roadmap created, tracker file established | — | Choose starting phase |
| 2026-08-19 | Phase 1 scaffold generated: full folder structure, `.gitignore`, `.env.example`, `requirements.txt`, `README.md`, `docs/architecture.md`, `tests/test_setup.py` | Phase 1 | Run setup commands locally, verify `pytest` passes, commit to git |
| 2026-08-19 | Decided local/cloud split (Mac = git source of truth + light edits + UI later; Colab = heavy compute, LLM calls, analytics); created `notebooks/colab_pipeline.ipynb` (clone/pull → install → test → commit/push helper) | Phase 9 groundwork | Push Phase 1 scaffold to GitHub from the Mac terminal, then open the notebook in Colab and run Steps 0-5 |
| 2026-08-19 | User pushed Phase 1 to GitHub from Mac. Decided to defer Colab entirely until a phase genuinely needs heavy compute (Phase 4/7) — Phase 2 proceeds as a plain local Python script instead | Phase 2 | Build + run the mock data generator locally |
| 2026-08-19 | Phase 2 built and validated: `generate_mock_transactions.py` (527 txns, 13 months, 3 accounts, Plaid sign convention, recurring series, 4 anomaly types, checking→savings transfers), 8 new tests (12/12 passing), `docs/phase_notes/phase2.md` written | Phase 2 | User to run locally, commit, push; then start Phase 3 |
| 2026-08-19 | Course-corrected: this is a learning project, mentor was writing too much finished code. Switched to spec-first workflow (see CODING WORKFLOW note above). User is redoing Phase 2 themselves from a spec; mentor's version kept only as optional reference | Phase 2 | User writes the generator; ask for targeted help when stuck on a specific piece |
| 2026-08-20 | Phase 3/4 discovered already built (schema.py, db.py, rules.py, llm_fallback.py) but never connected — `finance.db` had 527 loaded transactions with `category` still NULL. Built `categorize_transactions.py` to close that gap (idempotent, only processes `category IS NULL` rows); found and fixed a real bug where direct-path script invocation (`python script.py` vs `python -m ...`) failed to import `src...` — added a `sys.path` bootstrap, now standard in every new script | Phase 4 | Run categorize_transactions.py for real, then build Phase 5 |
| 2026-08-20 | Built all of Phase 5: `totals.py` (category/monthly totals), `recurring.py` (recurring bill/subscription detection — validated 100% precision/recall against `mock_transactions_eval.csv`'s `is_recurring_truth`), `trends.py` (leave-one-out z-score spike detection + 3-month trend comparison — validated against the injected `category_spending_spike` case) | Phase 5 | Build Phase 6 |
| 2026-08-20 | Built Phase 6: `src/anomaly/detect.py` — per-category IQR amount outliers, duplicate-charge detection, rare-merchant flags. All three validated clean against the 3 remaining labeled anomaly types in the eval file (`large_one_off_purchase`, `duplicate_charge`, `new_rare_merchant`), zero false positives | Phase 6 | Build Phase 7 |
| 2026-08-20 | Diagnosed and fixed the Ollama `phi3:mini` reliability problem (see "LLM provider decision" in Current State above) — switched Phase 4 fallback + Phase 7 agent to Anthropic `claude-haiku-4-5`, upgraded `_call_anthropic()` to forced tool-use. Manually corrected the one known-bad DB row. Caught and flagged a pasted-API-key security issue mid-session | Phase 4 / security | Rotate the key, confirm done |
| 2026-08-20 | Built Phase 7 core: `src/agent/tools.py` (6 tool functions wrapping Phases 5/6, JSON-serializable), `scripts/test_tool_calling.py` (1-tool proof of concept), `src/agent/orchestrator.py` (full loop, all 6 tools, handles multi-tool rounds / tool errors / a runaway-loop safety cap). **Live-tested successfully** against the real Anthropic API and real DB: asked "Compare my spending trend and flag anything weird," got back a correct, well-structured answer citing the exact validated numbers (Shopping z-score 20.78, Best Buy $2,450, the Trader Joe's duplicate, etc.) | Phase 7 | Decide: extend Phase 7 (multi-turn memory, more tools) or move to Phase 8 (interface). Also: commit everything to git — still only 1 commit total |

---

## 4a. Forward-looking notes (not yet built, don't jump ahead)

- **Real account connection ("Rocket Money"-style), discussed 2026-08-19:**
  Achievable, maps onto phases already planned — Phase 10 (Plaid, upgraded
  from Sandbox to Production) handles real account linking + ongoing sync
  (via `/transactions/sync`, polled on a schedule rather than webhooks, to
  avoid needing a public HTTPS endpoint for a personal project). Phase 4
  (categorization) and Phase 6 (anomaly detection) don't change — they just
  run against real data instead of mock data once it's flowing in. Phase 7
  (agent layer) could be implemented as an MCP server (tools like
  `get_category_totals`, `get_anomalies` exposed via the Model Context
  Protocol) instead of a hand-rolled tool-calling loop — that would let
  Claude Desktop/Cowork talk to the finance DB directly, potentially
  replacing/supplementing Phase 8's custom UI. MCP is an agent-tool
  interface, not a data-sync mechanism — it doesn't solve "how do new
  transactions arrive," Plaid sync still does that. Real accounts also mean
  real security stakes (Plaid access tokens, encrypting the DB) — not just
  mock-data hygiene anymore. Decision: keep building Phases 4-9 against mock
  data first; revisit this design when actually starting Phase 10.
- **Two-agent verification, discussed 2026-08-20:** user asked whether two
  agents (the custom Phase 7 tool-calling agent + a second independent LLM
  call, e.g. Claude API) could cross-check each other's reasoning against
  the actual tool/query output before a response is shown to the user —
  a real, known pattern ("LLM-as-judge" / verifier pass), valuable for a
  finance agent specifically because wrong numbers erode trust fast.
  Decision: don't build this yet. Build the single-agent tool-calling loop
  in Phase 7 first (matches the original plan), validate it against the
  Phase 2 eval ground-truth files, and only add a verifier pass later if
  the single agent is observed making mistakes worth catching that way.
  Cheaper first line of defense to consider before a second LLM call at
  all: deterministic Python-level checks (e.g. independently recompute an
  aggregate the agent claims, compare) — catches the most common failure
  (agent misreading its own tool output) without any added LLM cost.
- **Local-model capability ceiling, discovered 2026-08-20:** `phi3:mini`
  via Ollama consistently (not flakily) gave wrong, confident answers on
  an unfamiliar merchant — a prompt rewrite just swapped one wrong answer
  for a different wrong answer, which is the signature of a model too
  small for the judgment call, not an ambiguous prompt. Relevant again at
  Phase 10 (real Plaid data): real statements will have far more unfamiliar
  merchants than the mock data's one intentional edge case, so whatever
  LLM handles the fallback tier needs to be more capable than `phi3:mini`
  — currently solved by using the Anthropic API instead (cheap enough per
  the cost math done this session), not by a bigger local model, since the
  user's Mac only has ~10GB free disk. If disk space ever opens up,
  Ollama models with real tool/function-calling support (`llama3.1`,
  `qwen2.5`) would be the free/local alternative worth revisiting.

## 5. Repo Structure (actual, as of 2026-08-20)

```
ai-finance-agent/
├── README.md
├── PROJECT_TRACKER.md          ← this file
├── .env.example
├── .gitignore                  # now also excludes data/statements/, real_transactions*.csv, *.pdf
├── requirements.txt
├── data/
│   ├── mock_transactions.csv
│   ├── mock_transactions_eval.csv   # ground truth: category/recurring/anomaly labels
│   └── statements/              # gitignored — local real PDFs live here, never committed
├── db/
│   └── finance.db
├── scripts/                     # one-off manual check/diagnostic scripts, not pytest tests
│   ├── check_boa_statement.py
│   ├── diagnose_llm_miscategorization.py
│   └── test_tool_calling.py     # Phase 7 single-tool proof of concept
├── src/
│   ├── ingestion/
│   │   ├── generate_mock_transactions.py
│   │   ├── load_transactions.py
│   │   └── parse_boa_statement.py     # real BoA PDF -> CSV, kept separate from mock pipeline
│   ├── categorization/
│   │   ├── rules.py                   # tier 1: deterministic merchant matching
│   │   ├── llm_fallback.py            # tier 2: LLM (Anthropic, forced tool-use)
│   │   └── categorize_transactions.py # writes categories into the DB, idempotent
│   ├── analytics/
│   │   ├── totals.py       # category/monthly totals
│   │   ├── recurring.py    # recurring bill/subscription detection -> recurring_series table
│   │   └── trends.py       # leave-one-out z-score spikes + 3-month trend comparison
│   ├── anomaly/
│   │   └── detect.py       # per-category IQR outliers, duplicate charges, rare merchants
│   ├── agent/
│   │   ├── tools.py         # 6 tool functions, no LLM code, JSON-serializable
│   │   └── orchestrator.py  # Phase 7 tool-calling loop (Anthropic, all 6 tools)
│   ├── storage/
│   │   ├── schema.py   # accounts, transactions, recurring_series, anomalies
│   │   └── db.py
│   └── interface/       # empty, Phase 8
├── notebooks/
│   └── colab_pipeline.ipynb   # unused, Colab never ended up needed
├── tests/
│   ├── test_setup.py
│   └── test_mock_data_generator.py
│   # no automated tests yet for storage/categorization/analytics/anomaly/agent
└── docs/
    └── architecture.md
```

---

## How to use this file with your mentor

At the start of a new session, upload this file (or paste its contents) and say
"continue the AI Personal Finance Agent project" — that gives full context on
what's done, what's in progress, and what's next without re-explaining anything.
