# Architecture

## 1. Architectural rule

The deterministic execution and verification path must work without an LLM. AI is an optional reasoning component that proposes hypotheses and approved experiments; application code validates every proposal and computes the outcome.

## 2. High-level flow

```text
Playwright report + optional artifacts
                |
                v
       Intake / validation
                |
                v
       Evidence normalization
                |
                v
       Failure signature builder
                |
                v
   Hypotheses (rules first; LLM later)
                |
                v
      Bounded experiment planner
                |
                v
     Allowlisted Playwright runner
                |
                v
       New run + collected evidence
                |
                v
        Outcome comparison
                |
                v
  JSON / Markdown investigation report
```

## 3. Proposed modules

```text
src/afra/
  __init__.py
  models.py                 # typed data contracts
  intake/
    report_loader.py        # validate and load report input
  evidence/
    normalize.py            # normalize report evidence
    trace_reader.py         # supported trace evidence extraction
  diagnosis/
    rules.py                # deterministic initial classifications
    hypotheses.py           # hypothesis data structure / ranking
  experiments/
    schema.py               # allowlisted experiment configuration
    runner.py               # bounded test execution
    budget.py               # time / attempt limits
  verification/
    signatures.py           # normalized failure signature
    compare.py              # reproduced / not reproduced / inconclusive
  reporting/
    markdown.py
    json_report.py
```

The exact module boundaries can change when implementation evidence justifies it. Do not create empty layers solely to make the architecture look sophisticated.

## 4. Core data objects

### Investigation
- investigation ID
- created time
- input artifact references
- status
- experiment budget
- experiment history
- final outcome

### Evidence item
- evidence type
- source artifact
- timestamp or event index, if available
- normalized content
- redaction status

### Hypothesis
- category
- description
- supporting evidence references
- contradicting evidence references
- confidence / ranking with documented semantics
- proposed approved experiment

### Experiment
- experiment ID
- configuration
- start/end time
- exit status
- captured artifacts
- budget consumed
- outcome

### Reproduction outcome
- `REPRODUCED`
- `NOT_REPRODUCED`
- `INCONCLUSIVE`

The result must include the comparison rule and evidence used. Do not use a single LLM-generated confidence number as the verdict.

## 5. Execution boundaries

- The model cannot supply arbitrary shell commands.
- The runner accepts only registered experiment types and validated parameters.
- Each experiment has a timeout and maximum attempt count.
- The first version only runs tests against the local demo app.
- Each scenario uses disposable or resettable test data.
- External side effects are disabled by default.
- A different error is not automatically treated as reproduction.

## 6. Storage plan

Start with file-based artifacts and SQLite metadata. Do not introduce PostgreSQL, vector search, or a message queue until a real requirement emerges. Store artifact metadata separately from potentially large trace files.

## 7. API and UI plan

Do not begin with an API/UI. First prove the workflow as a Python CLI and library. Add FastAPI only after the core input/experiment/report contracts stabilize. Add React only if the CLI/report workflow demonstrates a user need that a UI solves.

## 8. Failure handling

Every stage must fail explicitly and preserve available evidence. If a trace is malformed, a rerun times out, or the comparison lacks enough signals, the investigation should report an error or `INCONCLUSIVE` rather than invent a diagnosis.
