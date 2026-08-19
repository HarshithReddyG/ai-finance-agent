# Architecture

See `PROJECT_TRACKER.md` in the repo root for the full diagram and phase
roadmap. This file will accumulate deeper design notes as each phase is
built (schema decisions, prompt designs, tool-calling contracts, etc.).

## Design principles

1. **Mock data first.** Every layer is built and validated against mock
   CSV data before Plaid Sandbox is introduced in Phase 10. This keeps
   the early phases fast to iterate on and free of API rate limits or
   credential setup.
2. **Cloud-friendly, not cloud-dependent.** Every script that runs in a
   Google Colab notebook (Phase 9) must also run as a plain local Python
   script. Colab is for heavy compute and shareable demos, not a hard
   dependency.
3. **Open-source LLMs by default.** The categorization fallback (Phase 4)
   and the agent layer (Phase 7) are designed against an open-source model
   (Llama / Mistral / Phi, served locally via Ollama) so the project runs
   without a paid API key. A hosted model (e.g. Claude via the Anthropic
   API) is a drop-in alternative — the code is written against a small
   provider-agnostic interface so swapping providers doesn't touch the
   business logic.
4. **Security by default.** No real credentials are ever requested or
   stored. `.env` holds all secrets and is git-ignored. `.env.example`
   documents the shape without real values.

## Phase notes

Detailed design notes for each phase go in `docs/phase_notes/phaseN.md`
as that phase is worked on.
