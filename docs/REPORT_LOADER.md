# Report Loader — Playwright JSON Report Ingestion

## Supported schema

The report loader supports the Playwright **built-in JSON reporter** output (`--reporter=json`).

The expected top-level structure is:

```text
{
  "config":  { ... }         # optional — run configuration
  "suites":  [ ... ]         # required — array of test suites
  "errors":  [ ... ]         # optional — top-level reporter errors
  "stats":   { ... }         # optional — aggregate statistics
}
```

### Hierarchy

```
config → suites → specs → tests → results
```

| Level    | Represents                                  | Required fields  |
|----------|---------------------------------------------|------------------|
| suite    | A file or `test.describe()` block            | `title`          |
| spec     | An individual `test('…', …)` declaration     | `title`          |
| test     | A per-project instance of a spec             | (none strictly)  |
| result   | A single execution attempt (initial + retry) | `status`         |

Suites nest recursively: Playwright emits a file-level suite (e.g. `title: "example.spec.js"`) containing child suites for `test.describe()` blocks, which in turn contain `specs`.

### Result status values

Valid result statuses: `"passed"`, `"failed"`, `"timedOut"`, `"interrupted"`, `"skipped"`.

### Test status values

Valid test-level statuses: `"expected"`, `"unexpected"`, `"flaky"`, `"skipped"`.

### Error objects

Each error may contain:

| Field      | Type   | Description                                |
|------------|--------|--------------------------------------------|
| `message`  | string | Primary error message                      |
| `stack`    | string | Full stack trace                           |
| `snippet`  | string | Source code snippet around the failing line |
| `location` | object | `{ file, line, column }` source location   |

All error fields are optional — the loader preserves whatever is present.

## How to call the report loader

```python
from afra.intake.report_loader import load_report
from afra.models import LoaderConfig, ParsedReport, ReportLoadError

# With default configuration (10 MiB max file size)
report: ParsedReport = load_report("path/to/report.json")

# With custom file-size limit
config = LoaderConfig(max_size_bytes=5 * 1024 * 1024)  # 5 MiB
report = load_report("path/to/report.json", config=config)
```

The function returns a `ParsedReport` on success or raises `ReportLoadError` on failure.

## Extracted fields

The `ParsedReport` contains:

| Attribute      | Type                    | Description                                |
|----------------|-------------------------|--------------------------------------------|
| `suites`       | `tuple[TestSuite, ...]` | Top-level test suites                      |
| `stats`        | `ReportStats \| None`   | Aggregate statistics (if present)          |
| `errors`       | `tuple[TestError, ...]` | Top-level reporter errors                  |
| `config_file`  | `str \| None`           | Playwright config file path                |
| `root_dir`     | `str \| None`           | Test project root directory                |
| `source_file`  | `str`                   | Path to the loaded report file             |

Every data structure includes a `source_path` field (a JSONPath-like breadcrumb such as `$.suites[0].suites[0].specs[1].tests[0].results[0]`) that traces extracted evidence back to its location in the original report.

### Per-result evidence

Each `TestResult` captures:

- `status` — observed outcome (`"passed"`, `"failed"`, etc.)
- `duration_ms` — elapsed time in milliseconds (float or int)
- `retry` — zero-based retry counter
- `worker_index` — worker thread index
- `start_time` — ISO-8601 start timestamp
- `errors` — captured error details (message, stack, snippet, location)
- `attachments` — attachment references (name, contentType, path)
- `stdout` / `stderr` — captured output lines

## Validation failures

All validation failures raise `ReportLoadError` with:
- A short `reason` string (e.g. `"file not found"`, `"malformed JSON"`)
- An optional `detail` string with additional context

### Rejection cases

| Condition                              | Error reason                        |
|----------------------------------------|-------------------------------------|
| File does not exist                    | `file not found`                    |
| Path is not a regular file             | `path is not a regular file`        |
| File exceeds size limit                | `file exceeds size limit`           |
| File is not valid UTF-8                | `file is not valid UTF-8`           |
| Cannot access / read / stat file       | `cannot access file` / variants     |
| Not valid JSON                         | `malformed JSON`                    |
| JSON root is not an object             | `invalid report structure`          |
| Missing `suites` key                   | `missing required field`            |
| `suites` is not an array               | `invalid field type`                |
| Suite/spec missing `title`             | `missing or invalid required field` |
| Result missing/invalid `status`        | `invalid result status`             |
| Non-dict entry in structural array     | `invalid structure`                 |
| Array field has wrong type             | `invalid field type`                |
| Invalid `max_size_bytes` configuration | `invalid loader configuration`      |

### Empty vs. malformed reports

A report with `"suites": []` is **valid** — it represents a run that matched no test files.  It is distinct from a report missing the `suites` key, which is rejected.

## Test coverage

The test suite validates the loader through two complementary approaches:

### 1. Synthetic fixture tests (`tests/test_report_loader.py` — 54 tests)
- Valid reports with passing, failing, retried, and flaky tests.
- Nested suites and multiple specs.
- Missing optional metadata (missing config, stats, annotations, stdout, stderr).
- Partial error details (missing snippet, missing stack, missing location).
- Malformed inputs (truncated JSON, non-object root, wrong array types).
- Missing structural fields (`suites`, `title`, `status`).
- File-level guards (nonexistent path, directory path, non-UTF-8 bytes).
- Configurable file-size limit enforcement and configuration validation.
- Empty valid reports (`"suites": []`).

### 2. Real Playwright report validation (`tests/test_real_report.py` — 14 tests)
- Tested against a report generated by Playwright Test v1.64.1 running Chromium 156.0.8078.4.
- Test fixture: `tests/fixtures/real_playwright_report.json` generated from local HTML page (`index.html`) and test spec (`verify.spec.js`).
- Validates real nested suite structure (`verify.spec.js` → `AFRA Local Verification Suite`).
- Validates passing test outcome and timing.
- Validates failing test outcome, assertion failure message, failing line location (`verify.spec.js:17:26`), stack trace, and highlighted snippet.
- Validates failure attachment (`error-context.md`).
- Validates real `stats` with fractional millisecond duration (`duration_ms=3768.458`).
- Regression tests for schema compatibility adjustments discovered during real-report ingestion.

## Schema compatibility status

> **Verified against real Playwright reports.**
>
> **Playwright version:** 1.64.1  
> **Browser engine:** Chromium 156.0.8078.4 (headless)
>
> Compatibility was verified using a local HTML fixture with passing and failing assertions.

### Adaptations made for real Playwright reports

1. **Floating-point durations:** Playwright's JSON reporter emits fractional milliseconds in `stats.duration` (e.g. `3768.458`). The loader and models accept `float | None` for `duration_ms` so precision is preserved instead of being discarded by strict integer parsing.
2. **Dual error representations:** Playwright emits primary error details (`stack`, `snippet`, `location`) in `result.error` (an object), while `result.errors` (an array) often contains only `message` and `location`. The loader enriches the first entry of `result.errors` from `result.error`, ensuring that stack traces and code snippets are never lost.
3. **ANSI styling:** Real Playwright error messages and code snippets contain ANSI escape codes for terminal color highlighting. The loader safely preserves these raw strings without parsing failure.
4. **Nested describe blocks:** Playwright creates a file-level suite with nested suites for `test.describe()` blocks. The recursive suite extraction preserves the full hierarchy and generates accurate breadcrumb source paths.

## What is not yet supported

- **Trace archives** (`.zip` files) — only JSON report parsing is implemented.
- **Raw browser console logs** outside test stdio — not parsed.
- **Report merging** — only a single report file is loaded per call.
- **Streaming / incremental parsing** — the entire file is read into memory (bounded by `max_size_bytes`).
- **Attachment body decoding** — attachment metadata is captured; binary bodies are not loaded.
- **Custom reporter extensions** — non-standard third-party reporter fields are ignored.

1. **Floating-point durations:** Playwright's JSON reporter emits fractional milliseconds in `stats.duration` (e.g. `3768.458`). The loader and models accept `float | None` for `duration_ms` so precision is preserved instead of being discarded by strict integer parsing.
2. **Dual error representations:** Playwright emits primary error details (`stack`, `snippet`, `location`) in `result.error` (an object), while `result.errors` (an array) often contains only `message` and `location`. The loader enriches the first entry of `result.errors` from `result.error`, ensuring that stack traces and code snippets are never lost.
3. **ANSI styling:** Real Playwright error messages and code snippets contain ANSI escape codes for terminal color highlighting. The loader safely preserves these raw strings without parsing failure.
4. **Nested describe blocks:** Playwright creates a file-level suite with nested suites for `test.describe()` blocks. The recursive suite extraction preserves the full hierarchy and generates accurate breadcrumb source paths.

## What is not yet supported

- **Trace archives** (`.zip` files) — only JSON report parsing is implemented.
- **Raw browser console logs** outside test stdio — not parsed.
- **Report merging** — only a single report file is loaded per call.
- **Streaming / incremental parsing** — the entire file is read into memory (bounded by `max_size_bytes`).
- **Attachment body decoding** — attachment metadata is captured; binary bodies are not loaded.
- **Custom reporter extensions** — non-standard third-party reporter fields are ignored.

