"""Playwright JSON report loader.

Safely loads, validates, and extracts structured test evidence from a
Playwright JSON reporter output file.

Supported schema
----------------
The Playwright built-in JSON reporter emits a top-level object with:

- ``config``  — run configuration (optional for ingestion).
- ``suites``  — array of test suites (required).
- ``errors``  — top-level reporter errors (optional).
- ``stats``   — aggregate statistics (optional).

Each suite contains ``specs`` (individual tests) and optionally nested
``suites`` (``test.describe()`` blocks).  Each spec contains ``tests``
(per-project instances), and each test contains ``results`` (execution
attempts including retries).

This module extracts observable evidence *only*.  It does not diagnose
root causes or claim that any failure has been reproduced.

Schema compatibility
--------------------
The fixture format is based on the documented Playwright JSON reporter
schema as of Playwright ≥ 1.50.  Compatibility with an actual generated
report has **not** been verified because Playwright is not installed in
the current environment.  See ``docs/REPORT_LOADER.md`` for details.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, cast

from afra.models import (
    AttachmentRef,
    ErrorLocation,
    LoaderConfig,
    ParsedReport,
    ReportLoadError,
    ReportStats,
    TestError,
    TestInstance,
    TestResult,
    TestSpec,
    TestStatus,
    TestSuite,
)

__all__ = ["load_report"]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_report(
    path: str | pathlib.Path,
    config: LoaderConfig | None = None,
) -> ParsedReport:
    """Load and validate a Playwright JSON test report.

    Parameters
    ----------
    path:
        Filesystem path to the JSON report file.
    config:
        Optional loader configuration.  When ``None``, default limits
        (10 MiB max file size) are applied.

    Returns
    -------
    ParsedReport
        Structured evidence extracted from the report.

    Raises
    ------
    ReportLoadError
        If the file is missing, unreadable, oversized, not valid UTF-8,
        not valid JSON, or does not conform to the expected Playwright
        JSON reporter schema.
    """
    cfg = config or LoaderConfig()
    file_path = pathlib.Path(path)

    raw_text = _read_file_safely(file_path, cfg.max_size_bytes)
    data = _parse_json(raw_text, file_path)
    _validate_root(data, file_path)

    # _validate_root guarantees data is a dict with a "suites" key
    assert isinstance(data, dict)
    return _extract_report(data, source_file=str(file_path))


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _read_file_safely(path: pathlib.Path, max_size: int) -> str:
    """Read a file with size and encoding guards.

    Raises :class:`ReportLoadError` for missing/unreadable files,
    files exceeding the size limit, or non-UTF-8 content.
    """
    # Existence / readability ---------------------------------------------------
    try:
        if not path.exists():
            raise ReportLoadError("file not found", str(path))
    except OSError as exc:
        raise ReportLoadError(
            "cannot access file", f"{path}: {_safe_os_error(exc)}"
        ) from exc

    if not path.is_file():
        raise ReportLoadError("path is not a regular file", str(path))

    # Size check ---------------------------------------------------------------
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ReportLoadError(
            "cannot stat file", f"{path}: {_safe_os_error(exc)}"
        ) from exc

    if size > max_size:
        raise ReportLoadError(
            "file exceeds size limit",
            f"{size} bytes > {max_size} bytes",
        )

    # Read UTF-8 ---------------------------------------------------------------
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ReportLoadError("file is not valid UTF-8", str(path))
    except OSError as exc:
        raise ReportLoadError(
            "cannot read file", f"{path}: {_safe_os_error(exc)}"
        ) from exc


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def _parse_json(text: str, path: pathlib.Path) -> object:
    """Parse JSON text.  Raises :class:`ReportLoadError` on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportLoadError(
            "malformed JSON",
            f"{path}: {exc.msg} (line {exc.lineno}, col {exc.colno})",
        ) from exc


# ---------------------------------------------------------------------------
# Root validation
# ---------------------------------------------------------------------------


def _validate_root(data: object, path: pathlib.Path) -> None:
    """Ensure the root is a dict with the required ``suites`` array."""
    if not isinstance(data, dict):
        raise ReportLoadError(
            "invalid report structure",
            f"expected a JSON object at root, got {type(data).__name__}",
        )

    if "suites" not in data:
        raise ReportLoadError(
            "missing required field",
            "'suites' is required in the top-level report object",
        )

    if not isinstance(data["suites"], list):
        raise ReportLoadError(
            "invalid field type",
            f"'suites' must be an array, got {type(data['suites']).__name__}",
        )


# ---------------------------------------------------------------------------
# Report extraction
# ---------------------------------------------------------------------------


def _extract_report(data: dict[str, Any], *, source_file: str) -> ParsedReport:
    """Build a :class:`ParsedReport` from validated JSON data."""
    suites = tuple(
        _extract_suite(s, path=f"$.suites[{i}]")
        for i, s in enumerate(data["suites"])
        if _require_dict(s, f"$.suites[{i}]")
    )

    stats: ReportStats | None = None
    raw_stats = data.get("stats")
    if isinstance(raw_stats, dict):
        stats = _extract_stats(raw_stats)

    errors: tuple[TestError, ...] = ()
    raw_errors = data.get("errors")
    if isinstance(raw_errors, list):
        errors = tuple(
            _extract_error(e)
            for e in raw_errors
            if isinstance(e, dict)
        )

    config_obj = data.get("config")
    config_file: str | None = None
    root_dir: str | None = None
    if isinstance(config_obj, dict):
        cf = config_obj.get("configFile")
        if isinstance(cf, str):
            config_file = cf
        rd = config_obj.get("rootDir")
        if isinstance(rd, str):
            root_dir = rd

    return ParsedReport(
        suites=suites,
        stats=stats,
        errors=errors,
        config_file=config_file,
        root_dir=root_dir,
        source_file=source_file,
    )


# ---------------------------------------------------------------------------
# Suite extraction (recursive)
# ---------------------------------------------------------------------------


def _extract_suite(data: dict[str, Any], *, path: str) -> TestSuite:
    """Extract a :class:`TestSuite` from a suite dict."""
    title = _require_str(data, "title", path)

    # Optional location fields
    file_val = _opt_str(data, "file")
    line_val = _opt_int(data, "line")
    column_val = _opt_int(data, "column")

    # Specs
    raw_specs = data.get("specs")
    specs: tuple[TestSpec, ...]
    if raw_specs is None:
        specs = ()
    elif not isinstance(raw_specs, list):
        raise ReportLoadError(
            "invalid field type",
            f"'{path}.specs' must be an array, got {type(raw_specs).__name__}",
        )
    else:
        specs = tuple(
            _extract_spec(s, path=f"{path}.specs[{i}]")
            for i, s in enumerate(raw_specs)
            if _require_dict(s, f"{path}.specs[{i}]")
        )

    # Nested child suites
    raw_suites = data.get("suites")
    child_suites: tuple[TestSuite, ...]
    if raw_suites is None:
        child_suites = ()
    elif not isinstance(raw_suites, list):
        raise ReportLoadError(
            "invalid field type",
            f"'{path}.suites' must be an array, got {type(raw_suites).__name__}",
        )
    else:
        child_suites = tuple(
            _extract_suite(s, path=f"{path}.suites[{i}]")
            for i, s in enumerate(raw_suites)
            if _require_dict(s, f"{path}.suites[{i}]")
        )

    return TestSuite(
        title=title,
        file=file_val,
        line=line_val,
        column=column_val,
        specs=specs,
        suites=child_suites,
        source_path=path,
    )


# ---------------------------------------------------------------------------
# Spec extraction
# ---------------------------------------------------------------------------


def _extract_spec(data: dict[str, Any], *, path: str) -> TestSpec:
    """Extract a :class:`TestSpec`."""
    title = _require_str(data, "title", path)

    ok_val = data.get("ok")
    ok: bool | None = ok_val if isinstance(ok_val, bool) else None

    raw_tags = data.get("tags")
    tags: tuple[str, ...]
    if isinstance(raw_tags, list):
        tags = tuple(t for t in raw_tags if isinstance(t, str))
    else:
        tags = ()

    file_val = _opt_str(data, "file")
    line_val = _opt_int(data, "line")
    column_val = _opt_int(data, "column")

    # Tests
    raw_tests = data.get("tests")
    tests: tuple[TestInstance, ...]
    if raw_tests is None:
        tests = ()
    elif not isinstance(raw_tests, list):
        raise ReportLoadError(
            "invalid field type",
            f"'{path}.tests' must be an array, got {type(raw_tests).__name__}",
        )
    else:
        tests = tuple(
            _extract_test(t, path=f"{path}.tests[{i}]")
            for i, t in enumerate(raw_tests)
            if _require_dict(t, f"{path}.tests[{i}]")
        )

    return TestSpec(
        title=title,
        ok=ok,
        tags=tags,
        tests=tests,
        file=file_val,
        line=line_val,
        column=column_val,
        source_path=path,
    )


# ---------------------------------------------------------------------------
# Test instance extraction
# ---------------------------------------------------------------------------

_VALID_TEST_STATUSES = frozenset({"expected", "unexpected", "flaky", "skipped"})
_VALID_RESULT_STATUSES = frozenset(
    {"passed", "failed", "timedOut", "interrupted", "skipped"}
)


def _extract_test(data: dict[str, Any], *, path: str) -> TestInstance:
    """Extract a :class:`TestInstance`."""
    expected_status = _opt_str(data, "expectedStatus")

    raw_status = data.get("status")
    status: TestStatus | None = (
        cast(TestStatus, raw_status)
        if isinstance(raw_status, str) and raw_status in _VALID_TEST_STATUSES
        else None
    )

    timeout_val = _opt_int(data, "timeout")
    project_name = _opt_str(data, "projectName")
    project_id = _opt_str(data, "projectId")

    raw_annotations = data.get("annotations")
    annotations: tuple[dict[str, object], ...]
    if isinstance(raw_annotations, list):
        annotations = tuple(a for a in raw_annotations if isinstance(a, dict))
    else:
        annotations = ()

    # Results
    raw_results = data.get("results")
    results: tuple[TestResult, ...]
    if raw_results is None:
        results = ()
    elif not isinstance(raw_results, list):
        raise ReportLoadError(
            "invalid field type",
            f"'{path}.results' must be an array, got {type(raw_results).__name__}",
        )
    else:
        results = tuple(
            _extract_result(r, path=f"{path}.results[{i}]")
            for i, r in enumerate(raw_results)
            if _require_dict(r, f"{path}.results[{i}]")
        )

    return TestInstance(
        expected_status=expected_status,
        status=status,
        timeout_ms=timeout_val,
        project_name=project_name,
        project_id=project_id,
        annotations=annotations,
        results=results,
        source_path=path,
    )


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------


def _extract_result(data: dict[str, Any], *, path: str) -> TestResult:
    """Extract a :class:`TestResult`."""
    raw_status = data.get("status")
    if not isinstance(raw_status, str) or raw_status not in _VALID_RESULT_STATUSES:
        raise ReportLoadError(
            "invalid result status",
            f"'{path}.status' must be one of {sorted(_VALID_RESULT_STATUSES)}, "
            f"got {raw_status!r}",
        )

    duration = _opt_number(data, "duration")
    retry = _opt_int(data, "retry")
    worker_index = _opt_int(data, "workerIndex")
    start_time = _opt_str(data, "startTime")

    raw_error = data.get("error") if isinstance(data.get("error"), dict) else None
    raw_errors = data.get("errors")

    # Errors — both ``errors`` array and detailed ``error`` single object
    errors_list: list[TestError] = []
    if isinstance(raw_errors, list):
        for i, e in enumerate(raw_errors):
            if isinstance(e, dict):
                # The primary error in `errors` is enriched with details (stack, snippet)
                # from `error` when present in Playwright's reporter output.
                fb = raw_error if i == 0 else None
                errors_list.append(_extract_error(e, fallback=fb))

    if not errors_list and raw_error:
        errors_list.append(_extract_error(raw_error))

    # Attachments
    attachments: tuple[AttachmentRef, ...] = ()
    raw_attachments = data.get("attachments")
    if isinstance(raw_attachments, list):
        attachments = tuple(
            _extract_attachment(a) for a in raw_attachments if isinstance(a, dict)
        )

    # stdout / stderr
    stdout = _extract_stdio(data.get("stdout"))
    stderr = _extract_stdio(data.get("stderr"))

    return TestResult(
        status=raw_status,  # type: ignore[arg-type]  # validated above
        duration_ms=duration,
        retry=retry,
        worker_index=worker_index,
        start_time=start_time,
        errors=tuple(errors_list),
        attachments=attachments,
        stdout=stdout,
        stderr=stderr,
        source_path=path,
    )


# ---------------------------------------------------------------------------
# Error extraction
# ---------------------------------------------------------------------------


def _extract_error(
    data: dict[str, Any],
    fallback: dict[str, Any] | None = None,
) -> TestError:
    """Extract a :class:`TestError`.

    When *fallback* is provided, missing optional fields (such as ``stack``,
    ``snippet``, or ``location``) are populated from it.  This handles
    Playwright reports where the detailed stack/snippet lives on ``result.error``
    while ``result.errors[0]`` contains only basic message/location data.
    """
    fb = fallback if isinstance(fallback, dict) else {}
    message = _opt_str(data, "message") or _opt_str(fb, "message")
    stack = _opt_str(data, "stack") or _opt_str(fb, "stack")
    snippet = _opt_str(data, "snippet") or _opt_str(fb, "snippet")

    raw_loc = data.get("location") if isinstance(data.get("location"), dict) else fb.get("location")
    location: ErrorLocation | None = None
    if isinstance(raw_loc, dict):
        location = ErrorLocation(
            file=_opt_str(raw_loc, "file"),
            line=_opt_int(raw_loc, "line"),
            column=_opt_int(raw_loc, "column"),
        )

    return TestError(
        message=message,
        stack=stack,
        snippet=snippet,
        location=location,
    )


# ---------------------------------------------------------------------------
# Attachment extraction
# ---------------------------------------------------------------------------


def _extract_attachment(data: dict[str, Any]) -> AttachmentRef:
    """Extract an :class:`AttachmentRef`."""
    name = data.get("name")
    if not isinstance(name, str):
        name = "<unnamed>"
    return AttachmentRef(
        name=name,
        content_type=_opt_str(data, "contentType"),
        path=_opt_str(data, "path"),
        body=_opt_str(data, "body"),
    )


# ---------------------------------------------------------------------------
# Stdio extraction
# ---------------------------------------------------------------------------


def _extract_stdio(raw: object) -> tuple[str, ...]:
    """Extract stdout/stderr entries as a tuple of strings."""
    if not isinstance(raw, list):
        return ()
    entries: list[str] = []
    for item in raw:
        if isinstance(item, str):
            entries.append(item)
        elif isinstance(item, dict):
            # Playwright may emit ``{text: "..."}`` objects
            text = item.get("text")
            if isinstance(text, str):
                entries.append(text)
    return tuple(entries)


# ---------------------------------------------------------------------------
# Stats extraction
# ---------------------------------------------------------------------------


def _extract_stats(data: dict[str, Any]) -> ReportStats:
    """Extract a :class:`ReportStats` from the ``stats`` dict."""
    return ReportStats(
        start_time=_opt_str(data, "startTime"),
        duration_ms=_opt_number(data, "duration"),
        expected=_opt_int(data, "expected"),
        unexpected=_opt_int(data, "unexpected"),
        skipped=_opt_int(data, "skipped"),
        flaky=_opt_int(data, "flaky"),
    )


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def _require_str(data: dict[str, Any], key: str, path: str) -> str:
    """Return a required string field, or raise."""
    val = data.get(key)
    if not isinstance(val, str):
        raise ReportLoadError(
            "missing or invalid required field",
            f"'{path}.{key}' must be a string, got {type(val).__name__}",
        )
    return val


def _opt_str(data: dict[str, Any], key: str) -> str | None:
    """Return an optional string field, or ``None``."""
    val = data.get(key)
    return val if isinstance(val, str) else None


def _opt_int(data: dict[str, Any], key: str) -> int | None:
    """Return an optional integer field, or ``None``.

    Rejects ``bool`` values (which are ``int`` subclasses in Python)
    to avoid silently accepting malformed data.
    """
    val = data.get(key)
    if isinstance(val, bool):
        return None
    return val if isinstance(val, int) else None


def _opt_number(data: dict[str, Any], key: str) -> float | None:
    """Return an optional numeric field as a float, or ``None``.

    Supports both integers and floats (e.g. fractional millisecond durations
    emitted by the Playwright JSON reporter). Rejects ``bool`` values.
    """
    val = data.get(key)
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _require_dict(value: object, path: str) -> bool:
    """Validate that *value* is a dict.  Raises on non-dict values.

    Returns ``True`` so callers can use this in a generator predicate.
    """
    if not isinstance(value, dict):
        raise ReportLoadError(
            "invalid structure",
            f"expected an object at '{path}', got {type(value).__name__}",
        )
    return True


def _safe_os_error(exc: OSError) -> str:
    """Return a safe, short description of an OS error.

    Avoids leaking raw file contents — only the error class and
    OS-level message are included.
    """
    return f"{type(exc).__name__}: {exc.strerror or str(exc)}"
