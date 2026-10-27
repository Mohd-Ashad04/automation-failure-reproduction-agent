# Requirements and Scope

## 1. MVP functional requirements

### FR-01 — Run artifact intake
Accept a Playwright JSON report and optional associated trace archive/log files. Validate file type and size before processing.

**Acceptance:** malformed input returns a clear validation error; valid sample input creates an investigation record.

### FR-02 — Evidence normalization
Extract available test title, file, status, error text, retry history, timestamps, and artifact references. Extract additional trace evidence only where a supported parser can do so reliably.

**Acceptance:** normalized evidence follows a documented schema and retains source references.

### FR-03 — Controlled scenario environment
Provide a local demo app and tests that deliberately introduce known failure modes.

**Acceptance:** every scenario has documented setup, injected cause, expected evidence, and reset instructions.

### FR-04 — Baseline rerun
Run only explicitly selected test targets using an allowlisted command/configuration and a bounded timeout/retry budget.

**Acceptance:** the runner rejects unapproved commands and stops when its budget is exhausted.

### FR-05 — Outcome comparison
Compare the original failure and a new run using structured signals such as failure category, normalized error, failing action, and relevant evidence.

**Acceptance:** output distinguishes:
- `REPRODUCED`: predefined matching criteria satisfied.
- `NOT_REPRODUCED`: test completed without matching the target failure.
- `INCONCLUSIVE`: evidence is insufficient, runs conflict, or a different failure occurred.

### FR-06 — Investigation report
Generate JSON and Markdown reports with input artifacts, observed evidence, experiments performed, outcomes, limitations, and next-step suggestions.

**Acceptance:** every factual claim in the report can be traced to an observation or is explicitly labeled as a hypothesis.

### FR-07 — Automated tests
Test parsers, validation, experiment budgets, outcome comparison, and end-to-end controlled scenarios.

**Acceptance:** CI can run the deterministic test suite without a paid service or external model.

## 2. Later requirements (not MVP blockers)

- Optional local LLM for hypothesis generation.
- Structured model output validated by application code.
- Approved tool-call schema for selecting experiments.
- Investigation history and basic UI.
- Benchmark summary and export.

## 3. Non-functional requirements

- **Safety:** default to local test environments; no arbitrary shell commands from model output.
- **Boundedness:** hard limits on duration, attempts, artifact size, and experiment types.
- **Auditability:** store what was run, which configuration was used, and what was observed.
- **Privacy:** avoid logging secrets; redact configured sensitive patterns.
- **Reproducibility:** document Python version, dependency setup, scenario setup, and benchmark procedure.
- **Resource use:** usable without GPU; local LLM is optional.
- **Maintainability:** typed data models, small modules, tests, and documented decisions.

## 4. Initial failure classes

1. Timing / synchronization.
2. Network / application response.
3. UI state / interaction.
4. Test data / state dependency.

These are initial benchmark categories, not an exhaustive taxonomy.

## 5. Out of scope

- Arbitrary websites and untrusted production environments.
- Automatic changes to source code.
- Self-healing locators.
- POM generation.
- Multi-agent orchestration.
- Claims that an AI diagnosis is a verified root cause without supporting experiments.
