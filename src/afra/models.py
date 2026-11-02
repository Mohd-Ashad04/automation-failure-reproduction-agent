"""Typed data contracts for AFRA.

Immutable data structures representing parsed Playwright test report evidence.
These models capture observable facts from a test report without diagnosing
root causes or claiming reproduction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Error evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorLocation:
    """Source location where a test error originated.

    Fields may be ``None`` when the report omits location data.
    """

    file: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class TestError:
    """A single error captured during a test attempt.

    Preserves the raw ``message``, ``stack``, code ``snippet``, and optional
    source ``location`` exactly as they appear in the report.  All fields are
    optional because the Playwright JSON reporter may omit any of them.
    """

    __test__ = False
    message: str | None = None
    stack: str | None = None
    snippet: str | None = None
    location: ErrorLocation | None = None


# ---------------------------------------------------------------------------
# Attachment reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttachmentRef:
    """Reference to a test attachment (screenshot, trace, video, etc.).

    Only the metadata is captured — the attachment body is *not* loaded.
    """

    name: str
    content_type: str | None = None
    path: str | None = None
    body: str | None = None  # base64 body reference, not decoded


# ---------------------------------------------------------------------------
# Test result (single attempt)
# ---------------------------------------------------------------------------

ResultStatus = Literal["passed", "failed", "timedOut", "interrupted", "skipped"]


@dataclass(frozen=True)
class TestResult:
    """Evidence from a single execution attempt of a test.

    Attributes:
        status: Observed outcome of the attempt.
        duration_ms: Elapsed time in milliseconds, if reported.
        retry: Zero-based retry counter (``0`` = first attempt).
        worker_index: Worker that executed the attempt, if reported.
        start_time: ISO-8601 start timestamp, if reported.
        errors: Errors captured during the attempt (may be empty).
        attachments: Attachment references (may be empty).
        stdout: Captured standard-output entries (may be empty).
        stderr: Captured standard-error entries (may be empty).
        source_path: JSONPath-like breadcrumb to locate this result
            within the original report (for traceability).
    """

    __test__ = False
    status: ResultStatus
    duration_ms: float | None = None
    retry: int | None = None
    worker_index: int | None = None
    start_time: str | None = None
    errors: tuple[TestError, ...] = ()
    attachments: tuple[AttachmentRef, ...] = ()
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    source_path: str = ""


# ---------------------------------------------------------------------------
# Test instance (per-project variant of a spec)
# ---------------------------------------------------------------------------

TestStatus = Literal["expected", "unexpected", "flaky", "skipped"]


@dataclass(frozen=True)
class TestInstance:
    """A single test variant — a spec run against a particular project.

    Attributes:
        expected_status: What the test was expected to do (usually ``"passed"``).
        status: Resolved overall status (``"expected"``, ``"unexpected"``, etc.).
        timeout_ms: Configured timeout for this test instance.
        project_name: Playwright project name (e.g. ``"chromium"``).
        project_id: Playwright project identifier, if different from name.
        annotations: Free-form annotations attached via ``test.info()``.
        results: One entry per execution attempt (initial + retries).
        source_path: JSONPath-like breadcrumb for traceability.
    """

    __test__ = False
    expected_status: str | None = None
    status: TestStatus | None = None
    timeout_ms: int | None = None
    project_name: str | None = None
    project_id: str | None = None
    annotations: tuple[dict[str, object], ...] = ()
    results: tuple[TestResult, ...] = ()
    source_path: str = ""


# ---------------------------------------------------------------------------
# Spec (individual test declaration)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestSpec:
    """An individual test declaration (``test('…', …)``) inside a suite.

    Attributes:
        title: Human-readable test title.
        ok: Whether the spec completed without unexpected failures.
        tags: Tags applied to the test.
        tests: Per-project test instances derived from this spec.
        file: Source file path, if reported at spec level.
        line: Source line number.
        column: Source column number.
        source_path: JSONPath-like breadcrumb for traceability.
    """

    __test__ = False
    title: str
    ok: bool | None = None
    tags: tuple[str, ...] = ()
    tests: tuple[TestInstance, ...] = ()
    file: str | None = None
    line: int | None = None
    column: int | None = None
    source_path: str = ""


# ---------------------------------------------------------------------------
# Suite (file or describe block)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestSuite:
    """A test suite — typically a file or ``test.describe()`` block.

    Suites nest recursively: a file-level suite may contain child suites
    representing describe blocks.

    Attributes:
        title: Suite title (file name or describe label).
        file: Relative path to the test file, if reported.
        line: Source line number.
        column: Source column number.
        specs: Direct child specs.
        suites: Nested child suites.
        source_path: JSONPath-like breadcrumb for traceability.
    """

    __test__ = False
    title: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    specs: tuple[TestSpec, ...] = ()
    suites: tuple[TestSuite, ...] = ()
    source_path: str = ""


# ---------------------------------------------------------------------------
# Report statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportStats:
    """Aggregate statistics from the top-level ``stats`` object.

    All fields are optional — they may not be present in every reporter
    version.
    """

    start_time: str | None = None
    duration_ms: float | None = None
    expected: int | None = None
    unexpected: int | None = None
    skipped: int | None = None
    flaky: int | None = None


# ---------------------------------------------------------------------------
# Top-level parsed report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedReport:
    """Structured evidence extracted from a Playwright JSON test report.

    This is the primary output of :func:`afra.intake.report_loader.load_report`.
    It preserves the suite → spec → test → result hierarchy exactly as the
    Playwright JSON reporter emits it.

    Attributes:
        suites: Top-level test suites.
        stats: Aggregate run statistics, if present.
        errors: Top-level reporter errors (not per-test).
        config_file: Path to the Playwright config used for the run.
        root_dir: Root directory of the test project, if reported.
        source_file: Path to the report file that was loaded.
    """

    suites: tuple[TestSuite, ...] = ()
    stats: ReportStats | None = None
    errors: tuple[TestError, ...] = ()
    config_file: str | None = None
    root_dir: str | None = None
    source_file: str = ""


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class ReportLoadError(Exception):
    """Raised when a Playwright JSON report cannot be safely loaded.

    Provides a human-readable ``reason`` for diagnostic purposes without
    leaking raw file contents.

    Attributes:
        reason: Short classification of the failure.
        detail: Optional extra detail (file path, field name, etc.).
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        parts = [reason]
        if detail:
            parts.append(detail)
        super().__init__(": ".join(parts))


# ---------------------------------------------------------------------------
# Size-limit configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MiB


@dataclass(frozen=True)
class LoaderConfig:
    """Configuration for the report loader.

    Attributes:
        max_size_bytes: Maximum allowed report file size in bytes.  Must be
            a positive integer.  Defaults to 10 MiB.
    """

    max_size_bytes: int = field(default=DEFAULT_MAX_SIZE_BYTES)

    def __post_init__(self) -> None:
        if not isinstance(self.max_size_bytes, int) or self.max_size_bytes <= 0:
            raise ReportLoadError(
                "invalid loader configuration",
                f"max_size_bytes must be a positive integer, got {self.max_size_bytes!r}",
            )


# ---------------------------------------------------------------------------
# Normalized Evidence and Failure Signatures
# ---------------------------------------------------------------------------

FailureCategory = Literal[
    "assertion_mismatch",
    "timeout",
    "locator_failure",
    "navigation_failure",
    "unknown",
]


@dataclass(frozen=True)
class NormalizedLocation:
    """Normalized source location with consistent forward-slash path separators."""

    file: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class NormalizedError:
    """Normalized representation of a single test error.

    All terminal formatting codes (ANSI) and inconsistent line endings have been
    removed. Extracted locator, assertion, and expectation fields are populated
    when discernible through deterministic parsing.
    """

    message: str | None = None
    category: FailureCategory = "unknown"
    normalized_message: str | None = None
    stack: str | None = None
    snippet: str | None = None
    location: NormalizedLocation | None = None
    expected: str | None = None
    actual: str | None = None
    locator: str | None = None
    assertion: str | None = None


@dataclass(frozen=True)
class FailureSignature:
    """Deterministic failure signature for comparing test failures across runs.

    Attributes:
        signature_hash: SHA-256 hex digest representing the canonical signature,
            or empty string if evidence is insufficient.
        canonical_text: Canonical deterministic string before hashing (for auditing).
        category: Failure category used in the signature.
        contributing_fields: Tuple of field names that were included in the signature.
        is_sufficient: Whether the evidence was sufficient to generate a stable signature.
        reason: Diagnostic reason if evidence was insufficient.
    """

    signature_hash: str
    canonical_text: str
    category: FailureCategory
    contributing_fields: tuple[str, ...]
    is_sufficient: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class NormalizedTestEvidence:
    """Normalized evidence extracted from a test execution attempt.

    Attributes:
        test_title: Full or spec title of the test.
        status: Observed result status (e.g. "failed", "passed").
        suite_title: Enclosing suite title, if known.
        file: Normalized relative file path.
        category: Failure category (or "unknown" if not classified or passing).
        errors: Tuple of normalized errors captured during the attempt.
        primary_error: The primary normalized error, if any.
        signature: Deterministic failure signature, or None if the test did not fail.
        source_path: Breadcrumb path to original result in report.
        attachments: Tuple of attachments from the result.
        stdout: Cleaned stdout lines.
        stderr: Cleaned stderr lines.
    """

    test_title: str
    status: ResultStatus
    suite_title: str | None = None
    file: str | None = None
    category: FailureCategory = "unknown"
    errors: tuple[NormalizedError, ...] = ()
    primary_error: NormalizedError | None = None
    signature: FailureSignature | None = None
    source_path: str = ""
    attachments: tuple[AttachmentRef, ...] = ()
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedReport:
    """Collection of normalized test evidence from a ParsedReport.

    Attributes:
        tests: All normalized test attempts (passing and failing).
        failures: Subset of tests that failed or produced unexpected results.
        source_file: Original report file path.
        config_file: Configuration file, if reported.
        stats: Run statistics from report.
    """

    tests: tuple[NormalizedTestEvidence, ...] = ()
    failures: tuple[NormalizedTestEvidence, ...] = ()
    source_file: str = ""
    config_file: str | None = None
    stats: ReportStats | None = None
