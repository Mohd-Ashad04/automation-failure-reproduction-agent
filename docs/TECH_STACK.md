# Technology Choices

## Guiding approach

Prefer the smallest stack that can validate the central hypothesis. Avoid adding frameworks, databases, vector stores, and agent libraries before the workflow needs them.

| Area | Initial choice | Why | Reconsider when |
|---|---|---|---|
| Language | Python 3.12 | Good testing ecosystem; compatible with Playwright Python and data tooling | A demonstrated requirement needs another runtime |
| Browser automation | Playwright for Python | The project's first supported framework and source of run artifacts | Do not add other frameworks in MVP |
| Test runner | pytest | Familiar, extensible, and easy to use in CI | Not expected to change |
| CLI | Python module / argparse initially | Keeps the first milestone small | Add Typer only if CLI complexity warrants it |
| Data validation | dataclasses or Pydantic | Typed contracts and validation; avoid unvalidated model output | Choose based on API/schema needs |
| Backend | None initially; FastAPI later | Core logic should not depend on a server | Add when an API has a clear consumer |
| Metadata storage | JSON files + SQLite | Simple local persistence, no service to maintain | PostgreSQL only if concurrent/multi-user needs arise |
| LLM runtime | None for baseline; optional Ollama later | Zero-cost local inference can be tested after deterministic baseline | Model quality and laptop performance are measured |
| Embeddings / RAG | Not in MVP | The initial problem is structured run evidence, not document retrieval | Add only if a real evidence retrieval need is demonstrated |
| Frontend | Markdown/JSON reports initially | The result matters more than a dashboard | React + Vite after CLI usability is validated |
| Packaging | pyproject.toml | Standard Python project metadata | Revisit only for concrete packaging issues |
| CI | GitHub Actions | Repeatable tests on pushes/PRs | Add matrix jobs after supported configurations exist |
| Containers | Optional later | Containers may improve isolation but add resource overhead | Introduce when reproducibility needs it |

## Model policy

The MVP must run with no model installed. Later, evaluate a small quantized local model through Ollama for hypothesis generation and experiment selection. The laptop's 8 GB RAM makes memory use and inference speed constraints. Model choice must follow a measured experiment, not a marketing claim.

## Why not start with LangChain / CrewAI / a multi-agent system?

The hard problem is controlled experiment execution and reliable comparison, not coordinating many agents. A small explicit tool loop is easier to test, constrain, and explain. Add a framework only if it solves a demonstrated implementation problem.

## Why not start with a vector database?

The initial evidence is structured and attached to a single investigation. Use ordinary parsing and indexing first. Embeddings or RAG may be useful later for retrieving historical investigations, but are not prerequisites for reproducing a known failure.
