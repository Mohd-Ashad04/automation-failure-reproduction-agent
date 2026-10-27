# Automation Failure Reproduction Agent

A local-first engineering project that investigates failed Playwright runs, runs bounded diagnostic experiments, and checks whether a new run reproduces the original failure.

> **Project status:** Planning / repository bootstrap. The core agent is not implemented yet.
>
> **Initial scope:** Python + Playwright, controlled local demo application, evidence-backed diagnosis, bounded experiments, and explicit reproduction verification.

## Why this project exists

A failed browser test can be intermittent: it fails in one run and passes in another. Test reports and traces provide evidence, but engineers still need to inspect the evidence, form hypotheses, rerun the test under controlled conditions, and decide whether the original failure was actually reproduced.

This project explores whether that workflow can be made more repeatable and auditable.

It is not intended to be a universal autonomous debugger. The first milestone targets deliberately injected failure scenarios in a local demo application.

## Core workflow

1. Import a Playwright test report and available artifacts.
2. Normalize the failure evidence.
3. Classify the failure into a limited category.
4. Generate evidence-backed hypotheses.
5. Select from a small allowlist of diagnostic experiments.
6. Rerun the test in a controlled environment.
7. Compare the new result with the original failure.
8. Produce a report: **reproduced**, **not reproduced**, or **inconclusive**.

An LLM explanation alone does not count as reproduction. The system must cite observed execution evidence.

## Planned scope

### MVP
- Playwright JSON report ingestion.
- Failure and artifact metadata extraction.
- A local demo app with known, injected failure scenarios.
- Deterministic baseline runner.
- Structured experiment configuration and run limits.
- Comparison of original and new failures.
- Evidence-backed Markdown/JSON investigation report.
- Automated tests and a reproducible benchmark.

### Later, only if the MVP works
- Optional local LLM via Ollama.
- Evidence-grounded hypothesis ranking.
- Bounded agent loop that chooses approved experiments.
- Simple investigation UI.
- Additional controlled failure classes.

### Explicitly out of scope for the first version
- Arbitrary production websites.
- Automatic production fixes or code commits.
- POM generation or self-healing locators.
- Multi-framework support.
- Unrestricted browser/computer control.
- Paid model/API dependencies.
- Claims of universal diagnosis or guaranteed root-cause identification.

## Documentation

- [Project charter](docs/PROJECT_CHARTER.md)
- [Requirements and scope](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Technology choices](docs/TECH_STACK.md)
- [Roadmap](docs/ROADMAP.md)
- [Evaluation plan](docs/EVALUATION_PLAN.md)
- [Security and safety](docs/SECURITY.md)
- [Decision record ADR-001](docs/adr/ADR-001-initial-technical-direction.md)
- [Contributing and workflow](CONTRIBUTING.md)

## Proposed stack

- Python 3.12
- Playwright for Python
- pytest
- FastAPI (after the core library works)
- SQLite initially
- Optional Ollama local model after the deterministic baseline
- React + Vite only if a UI is justified
- GitHub Actions for automated tests

See [Technology choices](docs/TECH_STACK.md) for why each choice is staged.

## First milestone: one-week proof of concept

The project must demonstrate all of the following before expanding:

1. A local test scenario fails intermittently for a known, injected reason.
2. A Playwright report and trace can be collected and inspected by the tool.
3. The tool can rerun the scenario under a bounded experiment configuration.
4. It can distinguish a matching failure from an unrelated failure and a passing run.
5. Results can be reproduced by another person using documented commands.

If this checkpoint fails, investigate the experiment design and evidence model before adding an LLM or UI.

## Local development

Prerequisites: Python 3.12 and Git. Install a Playwright browser after the implementation adds the relevant dependencies.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

The initial scaffold may not yet contain runnable application tests; the implementation milestones will make these commands meaningful. Do not treat a successful empty test run as proof of functionality.

## Principles

- Evidence before explanation.
- Reproduction is a measured outcome, not an LLM claim.
- Prefer deterministic baselines before adding AI.
- Bounded tools and explicit budgets.
- “Inconclusive” is a valid result.
- Measure results before making performance claims.
- Keep the initial project small enough to finish.
