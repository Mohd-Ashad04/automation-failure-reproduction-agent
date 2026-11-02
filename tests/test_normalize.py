"""Tests for deterministic evidence normalization and failure signature generation.

Covers ANSI stripping, whitespace/newline normalization, path normalization,
conservative categorization rules, structured detail extraction, deterministic
signature stability, edge cases, and real report compatibility.
"""

from __future__ import annotations

import pathlib

import pytest

from afra.evidence.normalize import (
    classify_error,
    compute_signature,
    extract_error_details,
    normalize_error,
    normalize_path,
    normalize_report,
    normalize_result,
    normalize_text,
    strip_ansi,
)
from afra.intake.report_loader import load_report
from afra.models import (
    AttachmentRef,
    ErrorLocation,
    ParsedReport,
    TestError,
    TestResult,
    TestSpec,
    TestSuite,
)

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
REAL_REPORT_PATH = FIXTURES_DIR / "real_playwright_report.json"


# ===================================================================
# 1. ANSI Escape Removal
# ===================================================================


class TestAnsiStripping:
    """Verifies complete removal of ANSI escape codes from terminal text."""

    def test_strip_color_codes(self) -> None:
        raw = "\x1b[31mRed text\x1b[39m and \x1b[32mgreen text\x1b[39m"
        assert strip_ansi(raw) == "Red text and green text"

    def test_strip_formatting_styles(self) -> None:
        raw = "\x1b[1mBold\x1b[22m, \x1b[2mdim\x1b[22m, \x1b[7minverse\x1b[27m, \x1b[0mreset"
        assert strip_ansi(raw) == "Bold, dim, inverse, reset"

    def test_strip_real_playwright_snippet_codes(self) -> None:
        raw = "\x1b[0m \x1b[90m 15 |\x1b[39m     \x1b[36mconst\x1b[39m status\x1b[0m"
        assert strip_ansi(raw) == "  15 |     const status"

    def test_plain_text_unmodified(self) -> None:
        text = "Ordinary plain text with no escape sequences."
        assert strip_ansi(text) == text

    def test_empty_string(self) -> None:
        assert strip_ansi("") == ""


# ===================================================================
# 2. Whitespace and Line-Ending Normalization
# ===================================================================


class TestWhitespaceAndLineEndings:
    """Verifies normalization of line endings and whitespace."""

    def test_crlf_normalized_to_lf(self) -> None:
        raw = "Line 1\r\nLine 2\r\nLine 3\r\n"
        assert normalize_text(raw) == "Line 1\nLine 2\nLine 3"

    def test_cr_normalized_to_lf(self) -> None:
        raw = "Line 1\rLine 2\rLine 3"
        assert normalize_text(raw) == "Line 1\nLine 2\nLine 3"

    def test_trailing_line_whitespace_stripped(self) -> None:
        raw = "Line 1   \nLine 2\t\t\nLine 3 "
        assert normalize_text(raw) == "Line 1\nLine 2\nLine 3"

    def test_leading_trailing_empty_lines_trimmed(self) -> None:
        raw = "\n\n   \nActual content\n\n   \n"
        assert normalize_text(raw) == "Actual content"

    def test_empty_input(self) -> None:
        assert normalize_text("") == ""
        assert normalize_text("   \n\t\n   ") == ""


# ===================================================================
# 3. Path Normalization
# ===================================================================


class TestPathNormalization:
    """Verifies conversion to relative POSIX-style paths across platforms."""

    def test_windows_backslashes_to_slashes(self) -> None:
        raw = "tests\\e2e\\login.spec.ts"
        assert normalize_path(raw) == "tests/e2e/login.spec.ts"

    def test_windows_absolute_drive_stripped(self) -> None:
        raw = "C:\\projects\\tests\\login.spec.ts"
        assert normalize_path(raw) == "projects/tests/login.spec.ts"

    def test_strip_root_dir_prefix(self) -> None:
        root = "C:\\Users\\dev\\project"
        path = "C:\\Users\\dev\\project\\tests\\login.spec.ts"
        assert normalize_path(path, root_dir=root) == "tests/login.spec.ts"

    def test_redundant_dot_slash_removed(self) -> None:
        assert normalize_path("./tests/spec.js") == "tests/spec.js"
        assert normalize_path(".\\tests\\spec.js") == "tests/spec.js"

    def test_none_and_empty(self) -> None:
        assert normalize_path(None) is None
        assert normalize_path("") is None
        assert normalize_path("   ") is None


# ===================================================================
# 4. Error Categorization
# ===================================================================


class TestCategorizationRules:
    """Verifies deterministic failure classification rules."""

    def test_assertion_mismatch_expect_call(self) -> None:
        msg = "Error: expect(locator).toHaveText(expected) failed"
        assert classify_error(msg) == "assertion_mismatch"

    def test_assertion_mismatch_expected_received(self) -> None:
        msg = "Error: Value did not match\nExpected: true\nReceived: false"
        assert classify_error(msg) == "assertion_mismatch"

    def test_assertion_mismatch_assertion_error(self) -> None:
        msg = "AssertionError: expected element to be visible"
        assert classify_error(msg) == "assertion_mismatch"

    def test_timeout_wait_for_selector(self) -> None:
        msg = "TimeoutError: page.waitForSelector: Timeout 30000ms exceeded."
        assert classify_error(msg) == "timeout"

    def test_timeout_action(self) -> None:
        msg = "page.click: Timeout 5000ms exceeded while waiting for element"
        assert classify_error(msg) == "timeout"

    def test_locator_failure_strict_mode(self) -> None:
        msg = "Error: strict mode violation: locator('.item') resolved to 2 elements:"
        assert classify_error(msg) == "locator_failure"

    def test_locator_failure_zero_elements(self) -> None:
        msg = "Error: locator resolved to 0 elements while searching"
        assert classify_error(msg) == "locator_failure"

    def test_navigation_failure_net_err(self) -> None:
        msg = "page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:8080"
        assert classify_error(msg) == "navigation_failure"

    def test_navigation_failure_timeout(self) -> None:
        msg = "page.goto: Navigation timeout of 30000ms exceeded"
        assert classify_error(msg) == "navigation_failure"

    def test_unknown_for_unrecognized_errors(self) -> None:
        msg = "ZeroDivisionError: division by zero"
        assert classify_error(msg) == "unknown"

    def test_unknown_for_empty_message(self) -> None:
        assert classify_error("") == "unknown"
        assert classify_error(None) == "unknown"


# ===================================================================
# 5. Detail Extraction
# ===================================================================


class TestDetailExtraction:
    """Verifies extraction of structured fields from error text."""

    def test_extract_from_playwright_assertion(self) -> None:
        msg = (
            "Error: expect(locator).toHaveText(expected) failed\n\n"
            "Locator:  locator('#app-status')\n"
            'Expected: "STATUS: NONEXISTENT_FAILING_STATE"\n'
            'Received: "STATUS: READY"\n'
            "Timeout:  2000ms\n"
        )
        details = extract_error_details(msg)
        assert details["assertion"] == "toHaveText"
        assert details["locator"] == "locator('#app-status')"
        assert details["expected"] == "STATUS: NONEXISTENT_FAILING_STATE"
        assert details["actual"] == "STATUS: READY"
        assert details["headline"] == "Error: expect(locator).toHaveText(expected) failed"

    def test_volatile_retry_count_sanitized(self) -> None:
        msg = "Call log:\n  - waiting for locator\n    19 × locator resolved to <p>READY</p>"
        details = extract_error_details(msg)
        assert details["normalized_message"] is not None
        assert "19 ×" not in details["normalized_message"]
        assert "<N> × locator resolved" in details["normalized_message"]

    def test_empty_message_returns_nones(self) -> None:
        details = extract_error_details(None)
        assert details["assertion"] is None
        assert details["locator"] is None
        assert details["expected"] is None
        assert details["actual"] is None
        assert details["normalized_message"] is None


# ===================================================================
# 6. Deterministic Failure Signatures
# ===================================================================


class TestFailureSignatures:
    """Verifies stability, reproducibility, and distinctiveness of signatures."""

    def test_equivalent_errors_produce_same_signature(self) -> None:
        sig1 = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            line=17,
            assertion="toHaveText",
            locator="locator('#status')",
            expected="READY",
            actual="FAILED",
            headline="Error: expect(locator).toHaveText(expected) failed",
        )
        sig2 = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            line=17,
            assertion="toHaveText",
            locator="locator('#status')",
            expected="READY",
            actual="FAILED",
            headline="Error: expect(locator).toHaveText(expected) failed",
        )
        assert sig1.signature_hash == sig2.signature_hash
        assert sig1.canonical_text == sig2.canonical_text
        assert sig1.is_sufficient is True

    def test_windows_vs_linux_path_produces_same_signature(self) -> None:
        sig_win = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests\\e2e\\login.spec.js",
            line=10,
            headline="Error: assertion failed",
        )
        sig_posix = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/e2e/login.spec.js",
            line=10,
            headline="Error: assertion failed",
        )
        assert sig_win.signature_hash == sig_posix.signature_hash

    def test_different_expected_values_produce_different_signatures(self) -> None:
        sig_a = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            line=17,
            expected="STATE_A",
            actual="READY",
            headline="Error: assertion failed",
        )
        sig_b = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            line=17,
            expected="STATE_B",
            actual="READY",
            headline="Error: assertion failed",
        )
        assert sig_a.signature_hash != sig_b.signature_hash

    def test_different_actual_values_produce_different_signatures(self) -> None:
        sig_a = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            line=17,
            expected="READY",
            actual="VALUE_1",
            headline="Error: assertion failed",
        )
        sig_b = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            line=17,
            expected="READY",
            actual="VALUE_2",
            headline="Error: assertion failed",
        )
        assert sig_a.signature_hash != sig_b.signature_hash

    def test_different_locators_produce_different_signatures(self) -> None:
        sig_a = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            locator="locator('#btn-save')",
            headline="Error: assertion failed",
        )
        sig_b = compute_signature(
            category="assertion_mismatch",
            test_title="test status",
            file="tests/verify.spec.js",
            locator="locator('#btn-cancel')",
            headline="Error: assertion failed",
        )
        assert sig_a.signature_hash != sig_b.signature_hash

    def test_different_categories_produce_different_signatures(self) -> None:
        sig_assert = compute_signature(
            category="assertion_mismatch",
            test_title="test",
            headline="Error: failed",
        )
        sig_timeout = compute_signature(
            category="timeout",
            test_title="test",
            headline="Error: failed",
        )
        assert sig_assert.signature_hash != sig_timeout.signature_hash

    def test_contributing_fields_accurately_recorded(self) -> None:
        sig = compute_signature(
            category="timeout",
            test_title="slow test",
            file="tests/slow.spec.js",
            line=42,
            headline="TimeoutError: 30000ms exceeded",
        )
        assert sig.contributing_fields == (
            "category",
            "error_headline",
            "line",
            "test_file",
            "test_title",
        )


# ===================================================================
# 7. Insufficient Evidence Handling
# ===================================================================


class TestInsufficientEvidence:
    """Verifies that missing or generic errors are explicitly flagged as insufficient."""

    def test_missing_message_returns_insufficient_signature(self) -> None:
        sig = compute_signature(
            category="unknown",
            test_title="failing test",
            file="tests/spec.js",
            normalized_message=None,
            headline=None,
        )
        assert sig.is_sufficient is False
        assert sig.signature_hash == ""
        assert sig.canonical_text == ""
        assert sig.contributing_fields == ()
        assert sig.reason is not None
        assert "insufficient" in sig.reason

    def test_generic_error_headline_without_details_rejected(self) -> None:
        sig = compute_signature(
            category="unknown",
            test_title="failing test",
            headline="Error",
        )
        assert sig.is_sufficient is False
        assert sig.signature_hash == ""

    def test_whitespace_only_headline_rejected(self) -> None:
        sig = compute_signature(
            category="unknown",
            test_title="failing test",
            headline="   ",
        )
        assert sig.is_sufficient is False


# ===================================================================
# 8. Result Normalization
# ===================================================================


class TestNormalizeResult:
    """Verifies normalize_result against synthetic success and failure results."""

    def test_passing_result_has_no_failure_signature(self) -> None:
        res = TestResult(status="passed", duration_ms=100.0)
        spec = TestSpec(title="should pass")
        evidence = normalize_result(res, spec=spec)

        assert evidence.status == "passed"
        assert evidence.test_title == "should pass"
        assert evidence.errors == ()
        assert evidence.primary_error is None
        assert evidence.signature is None

    def test_failing_result_has_signature_and_normalized_error(self) -> None:
        err = TestError(
            message="Error: expect(locator).toBeVisible() failed\nLocator: locator('#modal')",
            location=ErrorLocation(file="tests/modal.spec.js", line=25, column=10),
        )
        res = TestResult(
            status="failed",
            duration_ms=500.0,
            errors=(err,),
            attachments=(AttachmentRef(name="screenshot", path="/tmp/s.png"),),
        )
        spec = TestSpec(title="modal should appear", file="tests/modal.spec.js", line=20)
        suite = TestSuite(title="Modal Suite", file="tests/modal.spec.js")

        evidence = normalize_result(res, spec=spec, suite=suite)

        assert evidence.status == "failed"
        assert evidence.category == "assertion_mismatch"
        assert evidence.file == "tests/modal.spec.js"
        assert evidence.primary_error is not None
        assert evidence.primary_error.locator == "locator('#modal')"
        assert evidence.primary_error.location is not None
        assert evidence.primary_error.location.line == 25
        assert evidence.signature is not None
        assert evidence.signature.is_sufficient is True
        assert evidence.signature.signature_hash != ""
        assert len(evidence.attachments) == 1

    def test_missing_spec_and_suite_uses_fallbacks(self) -> None:
        err = TestError(message="Error: network disconnected")
        res = TestResult(status="failed", errors=(err,))
        evidence = normalize_result(res)

        assert evidence.test_title == "<unnamed test>"
        assert evidence.suite_title is None
        assert evidence.signature is not None

    def test_normalize_error_directly(self) -> None:
        err = TestError(
            message="\x1b[31mError: expect(locator).toHaveText(expected)\x1b[39m\nLocator: locator('#heading')",
            stack="Error: ...\n    at tests\\heading.spec.js:12:5",
            snippet="> 12 | await expect...",
            location=ErrorLocation(file="C:\\project\\tests\\heading.spec.js", line=12, column=5),
        )
        norm_err = normalize_error(err, root_dir="C:\\project")
        assert norm_err.category == "assertion_mismatch"
        assert norm_err.message == "Error: expect(locator).toHaveText(expected)\nLocator: locator('#heading')"
        assert norm_err.locator == "locator('#heading')"
        assert norm_err.location is not None
        assert norm_err.location.file == "tests/heading.spec.js"
        assert norm_err.location.line == 12
        assert norm_err.location.column == 5
        assert norm_err.snippet == "> 12 | await expect..."


# ===================================================================
# 9. Real Playwright Report Normalization
# ===================================================================


class TestNormalizeReportRealReport:
    """Verifies end-to-end normalization of the actual Playwright-generated report."""

    @pytest.fixture
    def real_parsed_report(self) -> ParsedReport:
        assert REAL_REPORT_PATH.exists()
        return load_report(REAL_REPORT_PATH)

    def test_normalize_real_report(self, real_parsed_report: ParsedReport) -> None:
        norm = normalize_report(real_parsed_report)

        # 2 total tests: 1 passing, 1 failing
        assert len(norm.tests) == 2
        assert len(norm.failures) == 1

        # Passing test
        passing = norm.tests[0]
        assert passing.status == "passed"
        assert passing.test_title == "passing test: heading has expected text"
        assert passing.signature is None
        assert passing.primary_error is None

        # Failing test
        failing = norm.failures[0]
        assert failing.status == "failed"
        assert failing.test_title == "failing test: status has expected text"
        assert failing.category == "assertion_mismatch"
        assert failing.file == "verify.spec.js"

        # Check extracted structured error details
        err = failing.primary_error
        assert err is not None
        assert err.assertion == "toHaveText"
        assert err.locator == "locator('#app-status')"
        assert err.expected == "STATUS: NONEXISTENT_FAILING_STATE"
        assert err.actual == "STATUS: READY"
        assert err.location is not None
        assert err.location.line == 17
        assert err.location.column == 26

        # Check signature
        sig = failing.signature
        assert sig is not None
        assert sig.is_sufficient is True
        assert len(sig.signature_hash) == 64  # SHA-256 hex length
        assert sig.category == "assertion_mismatch"
        assert "STATUS: NONEXISTENT_FAILING_STATE" in sig.canonical_text
        assert "STATUS: READY" in sig.canonical_text
        assert "locator('#app-status')" in sig.canonical_text
        assert sig.contributing_fields == (
            "actual",
            "assertion",
            "category",
            "error_headline",
            "expected",
            "line",
            "locator",
            "test_file",
            "test_title",
        )

    def test_original_parsed_report_unmutated(self, real_parsed_report: ParsedReport) -> None:
        """Confirms that normalization does not mutate the input report."""
        norm = normalize_report(real_parsed_report)
        assert norm is not None
        # Assert report data remains as originally loaded
        assert real_parsed_report.suites[0].suites[0].specs[1].ok is False
        assert len(real_parsed_report.suites[0].suites[0].specs[1].tests[0].results[0].errors) == 1
