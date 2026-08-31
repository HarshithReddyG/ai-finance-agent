# AI Personal Finance Agent
 
An AI-powered agent that ingests credit card / bank transactions, stores
and categorizes them, detects anomalies and trends, and answers
natural-language questions about your spending — built as an incremental,
phase-by-phase learning project.

## Project status

Full architecture diagram, phase roadmap, and current status live in
[`PROJECT_TRACKER.md`](./PROJECT_TRACKER.md) — check there first.

## Repository structure

```
ai-finance-agent/
├── README.md                   ← you are here 
├── PROJECT_TRACKER.md          ← architecture diagram + phase roadmap + status
├── .env.example                ← template for local secrets (copy to .env)
├── requirements.txt            ← Python dependencies
├── data/                       ← mock (and later Plaid) transaction CSVs
├── db/                         ← local SQLite database file (git-ignored)
├── src/
│   ├── ingestion/              ← CSV / Plaid ingestion + normalization (Phase 2-3, 10)
│   ├── categorization/         ← rule-based + LLM categorization (Phase 4)
│   ├── analytics/              ← totals, trends, recurring detection (Phase 5)
│   ├── anomaly/                ← anomaly / outlier detection (Phase 6)
│   ├── agent/                  ← LLM agent + tool-calling layer (Phase 7)
│   └── interface/               ← CLI / Streamlit UI (Phase 8)
├── notebooks/                  ← Google Colab notebooks mirroring src/ (Phase 9)
├── tests/                      ← pytest test suite
└── docs/
    ├── architecture.md         ← design principles + deeper notes
    └── phase_notes/            ← one file per phase as it's built
```

## Setup (Phase 1)

Requires Python 3.10+.

```bash
# 1. Clone / enter the repo
cd ai-finance-agent

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        

# 3. Install
pip install -r requirements.txt

# 4. Copy the environment template (no real secrets needed yet)
cp .env.example .env

# 5. Verify the setup
python -c "import pandas, dotenv, sqlalchemy; print('Core deps OK')"
pytest
```

If both commands in step 5 succeed, Phase 1 is complete.

## Security

- No real bank credentials are ever requested or stored.
- `.env` is git-ignored; only `.env.example` (no real values) is committed.
- All data through Phase 9 is synthetic/mock. Phase 10 uses Plaid's
  **Sandbox** environment only, which uses fake institutions and fake
  account data — never real banking credentials.

## License

Personal learning project — add a license here if you plan to make the
repo public (MIT is a reasonable default).
