# Deterministic Failure Normalization and Signatures

## Overview

The normalization module (`afra.evidence.normalize`) transforms raw evidence extracted from Playwright test reports into normalized, platform-independent representations and computes deterministic **failure signatures**.

It operates strictly on observed test evidence:
- **No LLM or probabilistic reasoning:** All categorization and signature rules are deterministic.
- **No root-cause claims:** A matching failure signature confirms observable failure equivalence across runs, not a proven root cause.
- **Immutability:** Source reports and results are never modified.

---

## Architecture and Boundaries

```text
ParsedReport (from intake.report_loader)
                 │
                 ▼
     ┌────────────────────────┐
     │  afra.evidence.normalize │
     │                        │
     │  - strip_ansi()        │
     │  - normalize_text()    │
     │  - normalize_path()    │
     │  - classify_error()    │
     │  - extract_details()   │
     │  - compute_signature() │
     └───────────┬────────────┘
                 │
                 ▼
         NormalizedReport
      ├── tests: tuple[NormalizedTestEvidence, ...]
      └── failures: tuple[NormalizedTestEvidence, ...]
                 │
                 └── FailureSignature (SHA-256)
```

### Module Responsibilities

1. **Text & Path Sanitization:** Strip ANSI terminal escape codes, normalize line endings (`\r\n` / `\r` → `\n`), trim whitespace, and convert Windows-specific paths into relative POSIX paths.
2. **Error Detail Extraction:** Parse Playwright error output to isolate failing locators, expected/actual values, and matcher assertion names.
3. **Conservative Classification:** Assign deterministic failure categories based on explicit patterns.
4. **Stable Signature Generation:** Hash canonical normalized evidence into a reproducible SHA-256 fingerprint for outcome comparison.

---

## Data Contracts

Defined in [`src/afra/models.py`](file:///c:/Users/Mohd%20Ashad/Downloads/automation-failure-reproduction-agent-starter/automation-failure-reproduction-agent/src/afra/models.py):

### `FailureCategory`

```python
FailureCategory = Literal[
    "assertion_mismatch",
    "timeout",
    "locator_failure",
    "navigation_failure",
    "unknown",
]
```

### `NormalizedLocation`

```python
@dataclass(frozen=True)
class NormalizedLocation:
    file: str | None = None      # Platform-independent relative path (e.g. "tests/verify.spec.js")
    line: int | None = None      # 1-based line number
    column: int | None = None    # 1-based column number
```

### `NormalizedError`

```python
@dataclass(frozen=True)
class NormalizedError:
    message: str | None = None              # Clean message without ANSI styling
    category: FailureCategory = "unknown"   # Categorized failure type
    normalized_message: str | None = None   # Sanitized message with volatile counters replaced
    stack: str | None = None                # Stack trace without ANSI codes
    snippet: str | None = None              # Code snippet without ANSI codes
    location: NormalizedLocation | None = None
    expected: str | None = None             # Extracted expectation value
    actual: str | None = None               # Extracted received value
    locator: str | None = None              # Extracted selector/locator string
    assertion: str | None = None            # Extracted matcher name (e.g. "toHaveText")
```

### `FailureSignature`

```python
@dataclass(frozen=True)
class FailureSignature:
    signature_hash: str                  # SHA-256 hex digest, or "" if insufficient
    canonical_text: str                  # Canonical sorted JSON string before hashing
    category: FailureCategory
    contributing_fields: tuple[str, ...] # Tuple of field names included in signature
    is_sufficient: bool = True           # False when evidence lacks diagnostic detail
    reason: str | None = None            # Diagnostic reason if is_sufficient is False
```

### `NormalizedTestEvidence`

```python
@dataclass(frozen=True)
class NormalizedTestEvidence:
    test_title: str
    status: ResultStatus
    suite_title: str | None = None
    file: str | None = None
    category: FailureCategory = "unknown"
    errors: tuple[NormalizedError, ...] = ()
    primary_error: NormalizedError | None = None
    signature: FailureSignature | None = None  # None for passing/skipped tests
    source_path: str = ""
    attachments: tuple[AttachmentRef, ...] = ()
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
```

---

## Categorization Rules

Categories are evaluated in strict precedence order:

| Precedence | Category | Trigger Rule | Example Triggers |
|---|---|---|---|
| 1 | `assertion_mismatch` | Message contains `expect(`, `expect.soft(`, `expect.poll(`, both `Expected:` and `Received:`, or `AssertionError` | `Error: expect(locator).toHaveText(expected) failed`<br>`Expected: "READY" Received: "PENDING"` |
| 2 | `navigation_failure` | Message/stack contains `net::ERR_`, `page.goto:`, `Navigation failed`, or `Navigation timeout` | `net::ERR_CONNECTION_REFUSED`<br>`page.goto: Navigation timeout` |
| 3 | `locator_failure` | Outside an assertion, contains `strict mode violation`, `resolved to 0 elements`, `resolved to 2 elements`, or `Target closed` | `strict mode violation: locator('.row') resolved to 2 elements` |
| 4 | `timeout` | Outside an assertion, contains `TimeoutError`, `Timeout <N>ms exceeded`, or `timed out` | `TimeoutError: page.waitForSelector: Timeout 30000ms exceeded` |
| 5 | `unknown` | Error does not match any of the above explicit rules, or message is empty | `ZeroDivisionError`, generic runtime exceptions |

---

## Signature Construction and Canonical Serialization

The failure signature compares failures across distinct test executions.

### Contributing Fields

Only fields with non-null, non-volatile evidence are included:
- `category`: Assigned `FailureCategory`
- `test_file`: Normalized relative file path (e.g. `tests/verify.spec.js`)
- `test_title`: Spec/test title
- `line`: 1-based source line number (from primary error or spec)
- `assertion`: Extracted matcher name (e.g. `toHaveText`)
- `locator`: Extracted locator string (e.g. `locator('#app-status')`)
- `expected`: Extracted expected value
- `actual`: Extracted received value
- `error_headline`: Sanitized primary headline with timeout values masked

### Deterministic Serialization

The contributing fields dictionary is serialized using compact, sorted JSON:
```python
canonical_text = json.dumps(fields, sort_keys=True, separators=(",", ":"))
signature_hash = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
```

### Excluded Volatile Fields

The following fields are strictly excluded from the canonical signature:
- **Timestamps:** (`startTime`, ISO dates) — differ on every run.
- **Elapsed Durations:** (`duration`, `duration_ms`) — runtime performance varies per run.
- **Worker & Retry Indices:** (`workerIndex`, `parallelIndex`, `retry`) — depend on test runner scheduling.
- **Machine-Specific Paths:** Absolute drive paths (e.g. `C:\Users\dev\...`) are stripped to relative test paths.
- **Dynamic Iteration Counts:** Playwright call logs frequently record polling iterations (e.g. `19 × locator resolved`). These are normalized to `<N> × locator resolved`.
- **Configured Timeout Durations:** Timeout parameters (e.g. `with timeout 2000ms`) are normalized to `Timeout <TIMEOUT>`.

---

## Insufficient Evidence Handling

When an error lacks diagnostic details (e.g. empty string, whitespace only, or a bare `"Error"` string with no locator, assertion, or expected values):

1. `is_sufficient` is set to `False`.
2. `signature_hash` is set to `""`.
3. `canonical_text` is set to `""`.
4. `contributing_fields` is set to `()`.
5. `reason` explicitly explains the condition:
   `"insufficient error evidence (no specific error message, assertion, or locator)"`.

This prevents generating a misleading signature from non-informative data.

---

## Limitations

1. **Comparison, Not Diagnosis:** A matching failure signature establishes that two runs exhibited the same observable failure characteristics (same test, file, line, assertion, locator, and mismatch values). It does **not** prove that the underlying root cause is identical.
2. **Custom Assertion Frameworks:** Expectation extraction targets Playwright's built-in assertion reporter format (`Expected: ...`, `Received: ...`, `Locator: ...`). Custom user-defined assertion libraries that format errors differently will fall back to using the error headline and categorized error text.
3. **Trace Evidence:** Binary trace files (`.zip`) are not parsed in this module; rich trace timeline evidence will be handled in subsequent trace-reader tasks.

