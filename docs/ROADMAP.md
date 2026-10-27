# Roadmap and Milestones

This is a six-month planning horizon, not a guarantee. Progress is determined by acceptance criteria, not by the calendar alone.

## Milestone 0 — Repository and problem definition
**Target:** Week 1, Day 1

- [x] Define project goal and non-goals.
- [x] Define initial technology direction.
- [x] Define architecture and safety boundaries.
- [x] Define a one-week proof-of-concept checkpoint.
- [ ] Create the remote GitHub repository and push this scaffold.
- [ ] Create a local development environment and verify Python/Playwright versions.

**Exit criteria:** the repo is version-controlled and a clean setup is documented.

## Milestone 1 — One-week proof of concept
**Target:** First 7 days

- [ ] Build a tiny local demo web app.
- [ ] Add one deliberately intermittent failure with a known cause.
- [ ] Run it repeatedly and collect Playwright reports/traces.
- [ ] Parse a report and identify the target failed test.
- [ ] Rerun the scenario under a strict timeout/attempt budget.
- [ ] Compare original and new outcomes.
- [ ] Document a successful reproduction and a non-matching failure.

**Exit criteria:** demonstrate the full loop without an LLM. If this does not work, pause and revise the experiment design.

## Milestone 2 — Reliable evidence pipeline
**Target:** Month 1

- [ ] Add schema-validated intake.
- [ ] Normalize report/error/retry metadata.
- [ ] Add evidence references and safe redaction.
- [ ] Add unit tests and fixture reports.
- [ ] Define failure signatures and outcome comparison rules.

**Exit criteria:** parsers and comparison logic pass tests against saved fixtures.

## Milestone 3 — Controlled experiments
**Target:** Month 2

- [ ] Define an allowlist of experiment types.
- [ ] Enforce execution timeout, run count, and output limits.
- [ ] Capture each run's artifacts and configuration.
- [ ] Add experiment history and reproducible run identifiers.
- [ ] Add more controlled failure scenarios.

**Exit criteria:** a bounded experiment can run without model involvement and cannot execute arbitrary commands.

## Milestone 4 — Diagnosis and bounded agent loop
**Target:** Months 2–3

- [ ] Implement deterministic failure categories.
- [ ] Represent hypotheses with supporting/contradicting evidence.
- [ ] Test a local model for structured hypothesis generation.
- [ ] Validate model output against strict schemas.
- [ ] Allow the model to select only approved experiments.
- [ ] Require application-side verification of every result.

**Exit criteria:** model failure does not break the deterministic workflow; unsupported claims are rejected or marked uncertain.

## Milestone 5 — Benchmark and evaluation
**Target:** Month 4

- [ ] Build a benchmark with known injected causes.
- [ ] Repeat scenarios enough to measure intermittency.
- [ ] Compare against repeated reruns and deterministic rules.
- [ ] Measure reproduction rate, diagnosis accuracy, false diagnosis rate, experiment count, and inconclusive rate.
- [ ] Publish methodology, limitations, and raw aggregate results.

**Exit criteria:** results can be reproduced from documented commands and the benchmark does not rely on cherry-picked successful examples.

## Milestone 6 — Usability and release
**Target:** Months 5–6

- [ ] Produce a concise Markdown/JSON report.
- [ ] Add a minimal UI only if useful.
- [ ] Add CI, linting, typing and documentation.
- [ ] Add setup instructions and a short recorded demo.
- [ ] Audit secrets, logs, artifact retention and unsafe execution paths.
- [ ] Tag a versioned MVP release.

**Exit criteria:** another developer can clone, install, run the benchmark, inspect results and understand limitations.

## Scope gate

Do not add a UI, vector database, multi-agent framework, production integrations, or additional automation frameworks before Milestone 1 succeeds.
