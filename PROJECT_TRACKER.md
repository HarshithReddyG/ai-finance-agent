# AI Personal Finance Agent — Project Tracker

This file is the single source of truth for project state across sessions.
Keep it in your repo root (or wherever you keep this project) and re-upload
it at the start of any future session so your mentor can pick up exactly
where you left off. Update the "Status" column and the Session Log as you go.

Last updated: 2026-08-19

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
| 1 | Repository Setup | Scaffold repo structure, virtualenv, config, README skeleton | GitHub, Python, `venv`/`poetry` | In Progress |
| 2 | Mock Transaction Data | Generate realistic mock CSV transactions (multiple accounts, merchants, categories, recurring charges, a few anomalies) | Python, `faker`, `pandas` | Not Started |
| 3 | Database Schema + Storage | Design SQLite schema, build ingestion script CSV → DB | `sqlite3`, SQLAlchemy | Not Started |
| 4 | Categorization Engine | Rule-based categorizer + LLM fallback for unmatched merchants | regex, open-source LLM (Ollama: Llama/Mistral/Phi) | Not Started |
| 5 | Analytics | Monthly totals, category trends, recurring subscription detection | `pandas`, SQL queries | Not Started |
| 6 | Anomaly Detection | Statistical outlier detection, new-merchant flags, duplicate-charge checks | `pandas`, `scipy`/`numpy` | Not Started |
| 7 | AI Agent Layer | LLM agent with tool-calling over the analytics/anomaly functions, explainable answers | LLM tool-calling (Ollama / Anthropic API / HF) | Not Started |
| 8 | Interface | CLI or Streamlit UI for natural-language Q&A | Typer or Streamlit | Not Started |
| 9 | Cloud Integration | Port pipeline into Google Colab notebooks for heavy compute / demoing | Google Colab | Not Started |
| 10 | Plaid Sandbox Integration (optional) | Swap mock CSV for live Plaid Sandbox transactions | Plaid Sandbox API | Not Started |
| 11 | Final Demo + Docs + Resume Packaging | Polish README, architecture doc, demo script/video, resume bullet points | Markdown, screen recording | Not Started |

Status values to use: `Not Started` → `In Progress` → `Blocked` → `Done`.

---

## 3. Current State

- **Active phase:** Phase 1 — Repository Setup
- **Next action:** Run the Phase 1 setup commands locally (venv, `pip install -r requirements.txt`, `pytest`), confirm both checks pass, then commit and push to GitHub. Once confirmed, move to Phase 2 (Mock Transaction Data).
- **Open questions / blockers:** none yet

---

## 4. Session Log

Add one entry per working session so future sessions have context.

| Date | Session Summary | Phase Touched | Next Step |
|------|------------------|----------------|-----------|
| 2026-08-19 | Kickoff: architecture diagram + phase roadmap created, tracker file established | — | Choose starting phase |
| 2026-08-19 | Phase 1 scaffold generated: full folder structure, `.gitignore`, `.env.example`, `requirements.txt`, `README.md`, `docs/architecture.md`, `tests/test_setup.py` | Phase 1 | Run setup commands locally, verify `pytest` passes, commit to git |

---

## 5. Repo Structure (target, built out incrementally starting Phase 1)

```
ai-finance-agent/
├── README.md
├── PROJECT_TRACKER.md          ← this file
├── .env.example
├── requirements.txt
├── data/
│   └── mock_transactions.csv
├── db/
│   └── finance.db
├── src/
│   ├── ingestion/
│   ├── categorization/
│   ├── analytics/
│   ├── anomaly/
│   ├── agent/
│   └── interface/
├── notebooks/
│   └── colab_pipeline.ipynb
├── tests/
└── docs/
    ├── architecture.md
    └── phase_notes/
```

---

## How to use this file with your mentor

At the start of a new session, upload this file (or paste its contents) and say
"continue the AI Personal Finance Agent project" — that gives full context on
what's done, what's in progress, and what's next without re-explaining anything.
