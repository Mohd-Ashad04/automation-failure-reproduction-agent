# ADR-001: Initial Technical Direction

- **Status:** Accepted for MVP; subject to evidence-based revision.
- **Date:** 2026-10-27

## Context

The project needs to prove a narrow capability: ingest a failed Playwright run, run controlled experiments, and verify whether a subsequent run reproduces the target failure. The developer's environment is a Windows laptop with 8 GB RAM and integrated graphics, so a large local model or complex infrastructure is not a safe starting assumption.

## Decision

1. Support Playwright with Python only in the MVP.
2. Start with a local controlled demo application.
3. Build the deterministic evidence, execution, and verification path before adding an LLM.
4. Use a small Python package/CLI before adding FastAPI or a frontend.
5. Use files and SQLite before considering PostgreSQL or vector storage.
6. Make local LLM inference optional and evaluate it through Ollama only after the baseline works.
7. Use an explicit allowlist of experiments and hard execution budgets.
8. Treat `REPRODUCED`, `NOT_REPRODUCED`, and `INCONCLUSIVE` as separate outcomes.

## Consequences

### Positive
- Small initial scope.
- Easier debugging and testing.
- Can be developed without paid APIs.
- LLM failure does not block core behavior.
- Clear separation between model suggestions and verified observations.

### Negative
- The first version is not a general-purpose product.
- The CLI may be less visually impressive than a dashboard.
- Local model quality and speed may be limited.
- More sophisticated real-world scenarios require additional research and engineering.

## Revisit when

- The first end-to-end proof of concept works.
- Benchmark evidence demonstrates a need for persistent storage, embeddings, an API, or a UI.
- The selected local model demonstrably improves a measured outcome.
