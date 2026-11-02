"""Deterministic failure evidence normalization and signature generation.

This module transforms parsed Playwright test report evidence into normalized,
platform-independent representations and computes stable failure signatures for
comparing test failures across separate executions.

Normalization principles:
1. Determinism — identical evidence always produces identical normalized output
   and signatures.
2. Immutability — source reports and results are never mutated.
3. Volatile exclusion — timestamps, elapsed durations, retry counts, worker indices,
   and machine-specific absolute path prefixes are excluded from signatures.
4. Conservative classification — categories are assigned only when explicit
   evidence patterns match; otherwise ``"unknown"`` is used.
5. Explicit insufficiency — when evidence lacks enough detail to construct a
   reliable signature, that state is recorded explicitly (``is_sufficient=False``)
   rather than fabricating a misleading signature.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from afra.models import (
    FailureCategory,
    FailureSignature,
    NormalizedError,
    NormalizedLocation,
    NormalizedReport,
    NormalizedTestEvidence,
    ParsedReport,
    TestError,
    TestResult,
    TestSpec,
    TestSuite,
)

__all__ = [
    "classify_error",
    "compute_signature",
    "extract_error_details",
    "normalize_error",
    "normalize_path",
    "normalize_report",
    "normalize_result",
    "normalize_text",
    "strip_ansi",
]

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# ANSI terminal escape sequences (colors, cursor, formatting)
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"
    r"|\x1b\].*?(?:\x07|\x1b\\)"
    r"|\x1b[()][AB012]"
)

# Locator pattern in Playwright assertion messages: e.g. "Locator: locator('#app-status')"
_LOCATOR_RE = re.compile(r"^\s*Locator:\s*(.+)$", re.MULTILINE)

# Expected value pattern: e.g. 'Expected: "STATUS: NONEXISTENT_FAILING_STATE"'
_EXPECTED_RE = re.compile(r"^\s*Expected:\s*(.+)$", re.MULTILINE)

# Received/Actual value pattern: e.g. 'Received: "STATUS: READY"'
_RECEIVED_RE = re.compile(r"^\s*Received:\s*(.+)$", re.MULTILINE)

# Assertion matcher name: e.g. "expect(locator).toHaveText(expected)" -> "toHaveText"
_ASSERTION_MATCHER_RE = re.compile(
    r"(?:expect|expect\.soft|expect\.poll)\([^)]*\)\.([a-zA-Z0-9_]+)\("
)

# Volatile retry counter in Playwright call logs: e.g. "19 × locator resolved"
_CALL_LOG_RETRY_COUNT_RE = re.compile(
    r"\b\d+\s*[×x]\s*locator resolved",
    re.IGNORECASE,
)

# Volatile timeout duration numbers: e.g. "with timeout 2000ms" or "Timeout: 2000ms"
_TIMEOUT_DURATION_RE = re.compile(
    r"\bwith timeout \d+ms\b|\bTimeout:\s*\d+ms\b|\bTimeout \d+ms exceeded\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Text and Path Cleaning
# ---------------------------------------------------------------------------


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (terminal styling and colors) from *text*.

    If *text* is empty or contains no ANSI codes, it is returned unchanged.
    """
    if not text:
        return text
    return _ANSI_ESCAPE_RE.sub("", text)


def normalize_text(text: str) -> str:
    """Normalize whitespace, line endings, and terminal styling in *text*.

    - Removes ANSI escape codes.
    - Normalizes Windows (``\\r\\n``) and legacy Mac (``\\r``) line endings to ``\\n``.
    - Strips trailing whitespace from each line.
    - Trims leading and trailing blank lines.
    """
    if not text:
        return ""
    cleaned = strip_ansi(text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    return "\n".join(lines).strip()


def normalize_path(path: str | None, root_dir: str | None = None) -> str | None:
    """Normalize a filesystem path to a platform-independent relative POSIX path.

    - Replaces backslashes with forward slashes.
    - If *root_dir* is provided and *path* starts with it, makes *path* relative.
    - Strips Windows drive letters (e.g. ``C:/``).
    - Removes leading ``./`` components.
    - Returns ``None`` if *path* is ``None`` or blank.
    """
    if path is None:
        return None
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return None

    if root_dir:
        norm_root = root_dir.replace("\\", "/").rstrip("/") + "/"
        normalized = normalized.removeprefix(norm_root)

    # Strip Windows drive letter (e.g. "C:/path" -> "path")
    if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
        normalized = normalized[2:].lstrip("/")

    # Strip redundant leading "./"
    while normalized.startswith("./"):
        normalized = normalized[2:]

    return normalized or None


# ---------------------------------------------------------------------------
# Error Categorization
# ---------------------------------------------------------------------------


def classify_error(message: str | None, stack: str | None = None) -> FailureCategory:
    """Classify failure evidence into a conservative, deterministic FailureCategory.

    Rules are evaluated in precedence order:
    1. ``assertion_mismatch``:
       - Playwright ``expect(...)`` matcher calls (e.g. ``expect(locator).toHaveText``).
       - Both ``Expected:`` and ``Received:`` lines present.
       - Explicit ``AssertionError``.
    2. ``timeout``:
       - Explicit ``TimeoutError`` or operation timeout without an expect assertion.
       - ``page.waitFor...: Timeout`` exceeded.
    3. ``locator_failure``:
       - Playwright ``strict mode violation`` (multiple elements resolved).
       - ``locator resolved to 0 elements`` or element detached/hidden when not an assertion.
    4. ``navigation_failure``:
       - Network error codes (e.g. ``net::ERR_CONNECTION_REFUSED``).
       - ``page.goto:`` failures or explicit navigation timeout.
    5. ``unknown``:
       - Anything that does not match the above rules, or when message is empty.

    This classification reflects observable failure characteristics and does
    NOT assert root cause.
    """
    if not message and not stack:
        return "unknown"

    clean_msg = normalize_text(message or "")
    clean_stack = normalize_text(stack or "")
    combined = f"{clean_msg}\n{clean_stack}".strip()

    if not combined:
        return "unknown"

    # Rule 1: Assertion mismatch (highest precedence for expect matchers)
    if (
        "AssertionError" in combined
        or "expect(" in clean_msg
        or "expect.soft(" in clean_msg
        or "expect.poll(" in clean_msg
        or ("Expected:" in clean_msg and "Received:" in clean_msg)
    ):
        return "assertion_mismatch"

    # Rule 2: Navigation failure
    if (
        "net::ERR_" in combined
        or "page.goto:" in combined
        or "Navigation failed" in combined
        or "Navigation timeout" in combined
    ):
        return "navigation_failure"

    # Rule 3: Locator resolution failure (outside assertion matchers)
    if (
        "strict mode violation" in combined
        or "resolved to 0 elements" in combined
        or "resolved to 2 elements" in combined
        or "Target closed" in combined
    ):
        return "locator_failure"

    # Rule 4: Action or wait timeout
    if (
        "TimeoutError" in combined
        or "Timeout " in clean_msg
        or "timed out" in clean_msg.lower()
        or "Timeout:" in clean_msg
    ):
        return "timeout"

    return "unknown"


# ---------------------------------------------------------------------------
# Detail Extraction from Error Text
# ---------------------------------------------------------------------------


def extract_error_details(message: str | None) -> dict[str, str | None]:
    """Extract structured details from a clean Playwright error message.

    Returns a dict with:
    - ``assertion``: Matcher function name (e.g. ``"toHaveText"``) or ``None``.
    - ``locator``: Locator selector (e.g. ``"locator('#app-status')"``) or ``None``.
    - ``expected``: Expected value string or ``None``.
    - ``actual``: Received value string or ``None``.
    - ``normalized_message``: Sanitized error text with volatile values replaced.
    - ``headline``: First non-empty headline of the error message.
    """
    if not message:
        return {
            "assertion": None,
            "locator": None,
            "expected": None,
            "actual": None,
            "normalized_message": None,
            "headline": None,
        }

    clean = normalize_text(message)
    if not clean:
        return {
            "assertion": None,
            "locator": None,
            "expected": None,
            "actual": None,
            "normalized_message": None,
            "headline": None,
        }

    # Extract headline (first non-empty line)
    headline: str | None = None
    for line in clean.split("\n"):
        line_stripped = line.strip()
        if line_stripped:
            headline = line_stripped
            break

    # Extract matcher assertion name
    assertion: str | None = None
    m_assert = _ASSERTION_MATCHER_RE.search(clean)
    if m_assert:
        assertion = m_assert.group(1).strip()

    # Extract locator
    locator: str | None = None
    m_loc = _LOCATOR_RE.search(clean)
    if m_loc:
        locator = m_loc.group(1).strip()

    # Extract expected value
    expected: str | None = None
    m_exp = _EXPECTED_RE.search(clean)
    if m_exp:
        raw_val = m_exp.group(1).strip()
        # Strip surrounding quotation marks if symmetric
        if len(raw_val) >= 2 and (
            (raw_val[0] == '"' and raw_val[-1] == '"')
            or (raw_val[0] == "'" and raw_val[-1] == "'")
        ):
            expected = raw_val[1:-1]
        else:
            expected = raw_val

    # Extract actual/received value
    actual: str | None = None
    m_rec = _RECEIVED_RE.search(clean)
    if m_rec:
        raw_val = m_rec.group(1).strip()
        if len(raw_val) >= 2 and (
            (raw_val[0] == '"' and raw_val[-1] == '"')
            or (raw_val[0] == "'" and raw_val[-1] == "'")
        ):
            actual = raw_val[1:-1]
        else:
            actual = raw_val

    # Normalize volatile parts of the error message for comparison
    norm_msg = _CALL_LOG_RETRY_COUNT_RE.sub("<N> × locator resolved", clean)
    norm_msg = _TIMEOUT_DURATION_RE.sub("Timeout <TIMEOUT>", norm_msg)

    return {
        "assertion": assertion,
        "locator": locator,
        "expected": expected,
        "actual": actual,
        "normalized_message": norm_msg,
        "headline": headline,
    }


# ---------------------------------------------------------------------------
# Error Normalization
# ---------------------------------------------------------------------------


def normalize_error(error: TestError, root_dir: str | None = None) -> NormalizedError:
    """Normalize a raw :class:`TestError` into a :class:`NormalizedError`.

    Strips ANSI codes, normalizes whitespace and line endings, categorizes the
    error using conservative rules, and extracts structured fields where discernible.
    """
    clean_msg = normalize_text(error.message) if error.message else None
    clean_stack = normalize_text(error.stack) if error.stack else None
    clean_snippet = normalize_text(error.snippet) if error.snippet else None

    category = classify_error(clean_msg, clean_stack)
    details = extract_error_details(clean_msg)

    location: NormalizedLocation | None = None
    if error.location:
        location = NormalizedLocation(
            file=normalize_path(error.location.file, root_dir),
            line=error.location.line,
            column=error.location.column,
        )

    return NormalizedError(
        message=clean_msg,
        category=category,
        normalized_message=details["normalized_message"],
        stack=clean_stack,
        snippet=clean_snippet,
        location=location,
        expected=details["expected"],
        actual=details["actual"],
        locator=details["locator"],
        assertion=details["assertion"],
    )


# ---------------------------------------------------------------------------
# Stable Signature Construction
# ---------------------------------------------------------------------------


def compute_signature(
    *,
    category: FailureCategory,
    test_title: str | None = None,
    file: str | None = None,
    line: int | None = None,
    assertion: str | None = None,
    locator: str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    headline: str | None = None,
    normalized_message: str | None = None,
) -> FailureSignature:
    """Construct a deterministic :class:`FailureSignature` from normalized evidence.

    Design rules:
    - Excludes volatile values (timestamps, durations, retry counts, machine paths).
    - Preserves meaningful failure distinctions (category, test title, file, line,
      assertion, locator, expected vs actual).
    - If evidence is insufficient (no message, assertion, or locator), returns
      an explicit invalid signature with ``is_sufficient=False``.
    - Serializes canonical fields in deterministic sorted key order before hashing.
    - Hash is standard SHA-256 hex digest.
    """
    clean_title = test_title.strip() if test_title else None
    clean_file = normalize_path(file) if file else None
    clean_headline = headline.strip() if headline else None
    clean_msg = normalized_message.strip() if normalized_message else None

    # Check for sufficient evidence
    has_message_evidence = bool(clean_headline or clean_msg)
    has_structured_evidence = bool(assertion or locator or (expected and actual))

    # Reject generic or empty errors
    is_empty_or_generic = (
        not has_message_evidence
        and not has_structured_evidence
    ) or (
        clean_headline in ("Error", "Error:", "failed", "Exception")
        and not has_structured_evidence
    )

    if is_empty_or_generic:
        return FailureSignature(
            signature_hash="",
            canonical_text="",
            category=category,
            contributing_fields=(),
            is_sufficient=False,
            reason="insufficient error evidence (no specific error message, assertion, or locator)",
        )

    # Build canonical fields dictionary
    fields: dict[str, Any] = {"category": category}

    if clean_title:
        fields["test_title"] = clean_title
    if clean_file:
        fields["test_file"] = clean_file
    if line is not None and line > 0:
        fields["line"] = line
    if assertion:
        fields["assertion"] = assertion.strip()
    if locator:
        fields["locator"] = locator.strip()
    if expected is not None:
        fields["expected"] = expected.strip()
    if actual is not None:
        fields["actual"] = actual.strip()

    # Include sanitized primary error headline
    if clean_headline:
        # Strip volatile numbers from headline
        sanitized_headline = _TIMEOUT_DURATION_RE.sub("Timeout <TIMEOUT>", clean_headline)
        fields["error_headline"] = sanitized_headline

    # Canonical serialization: sorted keys, compact separators
    canonical_text = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    signature_hash = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    contributing_fields = tuple(sorted(fields.keys()))

    return FailureSignature(
        signature_hash=signature_hash,
        canonical_text=canonical_text,
        category=category,
        contributing_fields=contributing_fields,
        is_sufficient=True,
    )


# ---------------------------------------------------------------------------
# Result Normalization
# ---------------------------------------------------------------------------


def normalize_result(
    result: TestResult,
    spec: TestSpec | None = None,
    suite: TestSuite | None = None,
    root_dir: str | None = None,
) -> NormalizedTestEvidence:
    """Normalize a :class:`TestResult` into :class:`NormalizedTestEvidence`.

    Parameters
    ----------
    result:
        Raw execution attempt result.
    spec:
        Optional parent spec declaration.
    suite:
        Optional parent suite block.
    root_dir:
        Optional project root directory used to make file paths relative.

    Returns
    -------
    NormalizedTestEvidence
        Deterministic normalized evidence and failure signature.
    """
    test_title = spec.title if spec else "<unnamed test>"
    suite_title = suite.title if suite else None

    # Resolve normalized test file path from spec, suite, or error location
    file_candidate = spec.file if spec and spec.file else (suite.file if suite and suite.file else None)
    if not file_candidate and result.errors:
        for err in result.errors:
            if err.location and err.location.file:
                file_candidate = err.location.file
                break
    normalized_file = normalize_path(file_candidate, root_dir)

    # Normalize errors
    normalized_errors = tuple(
        normalize_error(err, root_dir=root_dir)
        for err in result.errors
    )
    primary_error = normalized_errors[0] if normalized_errors else None

    # Determine failure category
    category: FailureCategory
    if primary_error:
        category = primary_error.category
    elif result.status == "timedOut":
        category = "timeout"
    else:
        category = "unknown"

    # Compute signature only for failed or unexpected attempts
    signature: FailureSignature | None = None
    if result.status in ("failed", "timedOut", "interrupted"):
        headline = None
        line_num = None
        assertion = None
        locator = None
        expected = None
        actual = None
        norm_msg = None

        if primary_error:
            headline = primary_error.message.split("\n")[0].strip() if primary_error.message else None
            line_num = primary_error.location.line if primary_error.location else None
            assertion = primary_error.assertion
            locator = primary_error.locator
            expected = primary_error.expected
            actual = primary_error.actual
            norm_msg = primary_error.normalized_message

        # Fall back to spec location if primary error location line is missing
        if line_num is None and spec and spec.line:
            line_num = spec.line

        signature = compute_signature(
            category=category,
            test_title=test_title,
            file=normalized_file,
            line=line_num,
            assertion=assertion,
            locator=locator,
            expected=expected,
            actual=actual,
            headline=headline,
            normalized_message=norm_msg,
        )

    # Clean stdout/stderr lines
    clean_stdout = tuple(
        normalize_text(line) for line in result.stdout if line and normalize_text(line)
    )
    clean_stderr = tuple(
        normalize_text(line) for line in result.stderr if line and normalize_text(line)
    )

    return NormalizedTestEvidence(
        test_title=test_title,
        status=result.status,
        suite_title=suite_title,
        file=normalized_file,
        category=category,
        errors=normalized_errors,
        primary_error=primary_error,
        signature=signature,
        source_path=result.source_path,
        attachments=result.attachments,
        stdout=clean_stdout,
        stderr=clean_stderr,
    )


# ---------------------------------------------------------------------------
# Report Normalization
# ---------------------------------------------------------------------------


def normalize_report(report: ParsedReport) -> NormalizedReport:
    """Normalize all test attempts from a :class:`ParsedReport`.

    Recursively traverses all suites, extracts and normalizes evidence for each
    test attempt, and segregates failures from overall tests.

    Parameters
    ----------
    report:
        Parsed Playwright test report.

    Returns
    -------
    NormalizedReport
        Collection of all normalized tests and the subset of failures.
    """
    tests: list[NormalizedTestEvidence] = []
    failures: list[NormalizedTestEvidence] = []

    def _walk_suite(suite: TestSuite) -> None:
        # Process specs in this suite
        for spec in suite.specs:
            for test_inst in spec.tests:
                for res in test_inst.results:
                    evidence = normalize_result(
                        result=res,
                        spec=spec,
                        suite=suite,
                        root_dir=report.root_dir,
                    )
                    tests.append(evidence)
                    if evidence.status in ("failed", "timedOut", "interrupted"):
                        failures.append(evidence)

        # Process nested child suites
        for child_suite in suite.suites:
            _walk_suite(child_suite)

    for top_suite in report.suites:
        _walk_suite(top_suite)

    return NormalizedReport(
        tests=tuple(tests),
        failures=tuple(failures),
        source_file=report.source_file,
        config_file=report.config_file,
        stats=report.stats,
    )
