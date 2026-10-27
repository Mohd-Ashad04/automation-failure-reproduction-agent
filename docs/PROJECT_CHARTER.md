# Project Charter

## 1. Working title

Automation Failure Reproduction Agent (AFRA)

## 2. Problem statement

Intermittent browser-automation failures are expensive to investigate because an engineer may need to inspect test output, logs, DOM snapshots, screenshots, network events, and execution traces, then manually rerun the test under different conditions. A later passing run does not explain the original failure, and a similar-looking error does not necessarily prove the same cause.

## 3. Goal

Build a local-first tool that uses available Playwright evidence and bounded diagnostic experiments to determine whether a known browser-test failure can be reproduced, and to report the supporting evidence and uncertainty.

## 4. Intended user

A software test / automation engineer who works with Playwright and needs help triaging intermittent failures in a test environment they are authorized to run.

## 5. Primary user outcome

Reduce repetitive evidence collection and make failure investigation more structured, repeatable, and measurable.

## 6. Non-goals

- Guaranteeing root-cause identification.
- Replacing a human test engineer.
- Automatically changing application code.
- Running experiments against arbitrary production systems.
- Supporting every browser automation framework in the MVP.
- Treating generated text as proof.

## 7. Success definition

The first meaningful success is a repeatable demonstration on a controlled local app: the system imports a failed run, extracts evidence, executes a bounded experiment, and correctly labels the outcome as reproduced, not reproduced, or inconclusive.

Longer-term success requires a published benchmark with known failure causes, repeated runs, baseline comparison, and transparent metrics.

## 8. Constraints

- No required paid API or cloud service.
- Must run on a typical Windows development laptop with 8 GB RAM.
- Start with one framework: Playwright Python.
- Start with a local, controlled application and disposable data.
- Model inference is optional and must not block the deterministic baseline.
- Keep experiment execution bounded by time, attempts, and allowed actions.

## 9. Key risks

1. The injected failure may not be reliably reproducible.
2. The report may omit evidence needed for comparison.
3. Different failures may look superficially similar.
4. A local model may be too slow or produce unsupported diagnoses.
5. Scope may expand before the core capability is proven.

## 10. Working principles

- Make small changes that can be tested.
- Record decisions in ADRs.
- Keep implementation status distinct from planned capability.
- Never publish fabricated benchmark results.
- Treat sensitive logs, URLs, tokens, and test data as potentially confidential.
