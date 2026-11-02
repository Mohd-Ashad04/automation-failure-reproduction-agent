"""Tests for the Playwright JSON report loader.

Fixtures are based on the documented Playwright JSON reporter schema
(config → suites → specs → tests → results) as of Playwright ≥ 1.50.

**Assumption:** Playwright is not installed in this environment.
Compatibility with an actual generated report has NOT been verified.
See ``docs/REPORT_LOADER.md`` for details.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from afra.intake.report_loader import load_report
from afra.models import (
    LoaderConfig,
    ParsedReport,
    ReportLoadError,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_json(tmp_path: pathlib.Path, data: Any, name: str = "report.json") -> pathlib.Path:
    """Write *data* as JSON to a temp file and return its path."""
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _minimal_report(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid Playwright JSON report structure."""
    report: dict[str, Any] = {"suites": [], **overrides}
    return report


def _make_result(
    *,
    status: str = "passed",
    duration: int = 100,
    retry: int = 0,
    errors: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a single result dict."""
    result: dict[str, Any] = {
        "status": status,
        "duration": duration,
        "retry": retry,
        "workerIndex": 0,
        "startTime": "2026-01-01T00:00:00.000Z",
        "errors": errors or [],
        "stdout": [],
        "stderr": [],
        "attachments": [],
        **extra,
    }
    return result


def _make_test(
    *,
    expected_status: str = "passed",
    status: str = "expected",
    results: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a single test instance dict."""
    return {
        "timeout": 30000,
        "annotations": [],
        "expectedStatus": expected_status,
        "projectId": "chromium",
        "projectName": "chromium",
        "results": results if results is not None else [_make_result()],
        "status": status,
        **extra,
    }


def _make_spec(
    title: str = "should work",
    *,
    ok: bool = True,
    tests: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a spec dict."""
    return {
        "title": title,
        "ok": ok,
        "tags": [],
        "tests": tests if tests is not None else [_make_test()],
        **extra,
    }


def _make_suite(
    title: str = "example.spec.ts",
    *,
    specs: list[dict[str, Any]] | None = None,
    suites: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a suite dict."""
    suite: dict[str, Any] = {
        "title": title,
        "file": "tests/example.spec.ts",
        "line": 0,
        "column": 0,
        **extra,
    }
    if specs is not None:
        suite["specs"] = specs
    else:
        suite["specs"] = [_make_spec()]
    if suites is not None:
        suite["suites"] = suites
    return suite


def _full_report(**overrides: Any) -> dict[str, Any]:
    """Return a complete Playwright JSON report with one passing test."""
    return {
        "config": {
            "configFile": "/project/playwright.config.ts",
            "rootDir": "/project",
        },
        "suites": [_make_suite()],
        "errors": [],
        "stats": {
            "startTime": "2026-01-01T00:00:00.000Z",
            "duration": 5000,
            "expected": 1,
            "unexpected": 0,
            "skipped": 0,
            "flaky": 0,
        },
        **overrides,
    }


# ===================================================================
# 1. Valid report — failed test
# ===================================================================


class TestValidFailedReport:
    """Loading a report with a failed test preserves failure evidence."""

    def test_failed_test_evidence_preserved(self, tmp_path: pathlib.Path) -> None:
        error_data = {
            "message": "expect(locator).toBeVisible()",
            "stack": "Error: ...\n    at tests/login.spec.ts:15:31",
            "location": {"file": "tests/login.spec.ts", "line": 15, "column": 31},
            "snippet": "> 15 |   await expect(page.locator('.dashboard')).toBeVisible();",
        }
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(
                            title="should log in",
                            ok=False,
                            tests=[
                                _make_test(
                                    status="unexpected",
                                    results=[
                                        _make_result(
                                            status="failed",
                                            errors=[error_data],
                                        ),
                                    ],
                                )
                            ],
                        )
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert len(parsed.suites) == 1
        spec = parsed.suites[0].specs[0]
        assert spec.title == "should log in"
        assert spec.ok is False

        test_inst = spec.tests[0]
        assert test_inst.status == "unexpected"
        assert len(test_inst.results) == 1

        result = test_inst.results[0]
        assert result.status == "failed"
        assert len(result.errors) == 1

        err = result.errors[0]
        assert err.message == "expect(locator).toBeVisible()"
        assert err.snippet is not None
        assert err.location is not None
        assert err.location.file == "tests/login.spec.ts"
        assert err.location.line == 15
        assert err.location.column == 31


# ===================================================================
# 2. Valid report — passing test
# ===================================================================


class TestValidPassingReport:
    """Loading a report with a passing test works correctly."""

    def test_passing_test(self, tmp_path: pathlib.Path) -> None:
        report = _full_report()
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert len(parsed.suites) == 1
        spec = parsed.suites[0].specs[0]
        assert spec.ok is True

        test_inst = spec.tests[0]
        assert test_inst.status == "expected"
        assert test_inst.results[0].status == "passed"
        assert test_inst.results[0].errors == ()

    def test_config_and_stats_extracted(self, tmp_path: pathlib.Path) -> None:
        report = _full_report()
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert parsed.config_file == "/project/playwright.config.ts"
        assert parsed.root_dir == "/project"
        assert parsed.stats is not None
        assert parsed.stats.expected == 1
        assert parsed.stats.unexpected == 0

    def test_source_file_recorded(self, tmp_path: pathlib.Path) -> None:
        report = _full_report()
        path = _write_json(tmp_path, report)
        parsed = load_report(path)
        assert parsed.source_file == str(path)


# ===================================================================
# 3. Multiple tests and nested suites
# ===================================================================


class TestMultipleAndNested:
    """Multiple specs and nested suites are handled correctly."""

    def test_multiple_specs(self, tmp_path: pathlib.Path) -> None:
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(title="test A"),
                        _make_spec(title="test B"),
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)
        titles = [s.title for s in parsed.suites[0].specs]
        assert titles == ["test A", "test B"]

    def test_nested_suites(self, tmp_path: pathlib.Path) -> None:
        inner_suite = _make_suite(title="inner describe", specs=[_make_spec(title="inner test")])
        outer_suite = _make_suite(title="outer", specs=[], suites=[inner_suite])
        report = _full_report(suites=[outer_suite])
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        outer = parsed.suites[0]
        assert outer.title == "outer"
        assert len(outer.suites) == 1

        inner = outer.suites[0]
        assert inner.title == "inner describe"
        assert len(inner.specs) == 1
        assert inner.specs[0].title == "inner test"

    def test_source_paths_reflect_nesting(self, tmp_path: pathlib.Path) -> None:
        inner_suite = _make_suite(title="inner", specs=[_make_spec(title="t")])
        outer_suite = _make_suite(title="outer", specs=[], suites=[inner_suite])
        report = _full_report(suites=[outer_suite])
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert parsed.suites[0].source_path == "$.suites[0]"
        assert parsed.suites[0].suites[0].source_path == "$.suites[0].suites[0]"
        assert parsed.suites[0].suites[0].specs[0].source_path == "$.suites[0].suites[0].specs[0]"

    def test_multiple_suites_at_top_level(self, tmp_path: pathlib.Path) -> None:
        suite_a = _make_suite(title="suite A")
        suite_b = _make_suite(title="suite B")
        report = _full_report(suites=[suite_a, suite_b])
        path = _write_json(tmp_path, report)
        parsed = load_report(path)
        assert len(parsed.suites) == 2
        assert parsed.suites[0].title == "suite A"
        assert parsed.suites[1].title == "suite B"


# ===================================================================
# 4. Retry history and multiple attempts
# ===================================================================


class TestRetryHistory:
    """Retry/attempt history is preserved accurately."""

    def test_multiple_results_represent_retries(self, tmp_path: pathlib.Path) -> None:
        results = [
            _make_result(status="failed", retry=0, errors=[{"message": "first fail"}]),
            _make_result(status="failed", retry=1, errors=[{"message": "second fail"}]),
            _make_result(status="passed", retry=2),
        ]
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(
                            ok=True,
                            tests=[_make_test(status="flaky", results=results)],
                        )
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        test_inst = parsed.suites[0].specs[0].tests[0]
        assert test_inst.status == "flaky"
        assert len(test_inst.results) == 3

        assert test_inst.results[0].retry == 0
        assert test_inst.results[0].status == "failed"
        assert test_inst.results[0].errors[0].message == "first fail"

        assert test_inst.results[1].retry == 1
        assert test_inst.results[1].status == "failed"

        assert test_inst.results[2].retry == 2
        assert test_inst.results[2].status == "passed"
        assert test_inst.results[2].errors == ()


# ===================================================================
# 5. Missing optional metadata
# ===================================================================


class TestMissingOptionalMetadata:
    """Optional fields that are absent remain as None, not fabricated."""

    def test_no_config_or_stats(self, tmp_path: pathlib.Path) -> None:
        report = _minimal_report(suites=[_make_suite()])
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert parsed.config_file is None
        assert parsed.root_dir is None
        assert parsed.stats is None

    def test_missing_test_annotations(self, tmp_path: pathlib.Path) -> None:
        test_data: dict[str, Any] = {
            "expectedStatus": "passed",
            "status": "expected",
            "results": [_make_result()],
        }
        report = _full_report(
            suites=[_make_suite(specs=[_make_spec(tests=[test_data])])]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        test_inst = parsed.suites[0].specs[0].tests[0]
        assert test_inst.timeout_ms is None
        assert test_inst.project_name is None
        assert test_inst.annotations == ()

    def test_missing_result_optional_fields(self, tmp_path: pathlib.Path) -> None:
        result_data: dict[str, Any] = {"status": "passed"}
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[_make_spec(tests=[_make_test(results=[result_data])])]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        result = parsed.suites[0].specs[0].tests[0].results[0]
        assert result.duration_ms is None
        assert result.retry is None
        assert result.worker_index is None
        assert result.start_time is None
        assert result.errors == ()
        assert result.attachments == ()
        assert result.stdout == ()
        assert result.stderr == ()

    def test_missing_suite_file(self, tmp_path: pathlib.Path) -> None:
        suite_data: dict[str, Any] = {"title": "no-file suite", "specs": [_make_spec()]}
        report = _full_report(suites=[suite_data])
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert parsed.suites[0].file is None
        assert parsed.suites[0].line is None


# ===================================================================
# 6. Missing failure error details
# ===================================================================


class TestMissingErrorDetails:
    """Failure evidence is preserved even when error details are partial."""

    def test_error_with_no_location_or_snippet(self, tmp_path: pathlib.Path) -> None:
        error_data: dict[str, Any] = {"message": "boom"}
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(
                            ok=False,
                            tests=[
                                _make_test(
                                    status="unexpected",
                                    results=[
                                        _make_result(status="failed", errors=[error_data])
                                    ],
                                )
                            ],
                        )
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        err = parsed.suites[0].specs[0].tests[0].results[0].errors[0]
        assert err.message == "boom"
        assert err.location is None
        assert err.snippet is None
        assert err.stack is None

    def test_error_with_only_stack(self, tmp_path: pathlib.Path) -> None:
        error_data: dict[str, Any] = {"stack": "Error: timeout\n    at ..."}
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(
                            ok=False,
                            tests=[
                                _make_test(
                                    status="unexpected",
                                    results=[
                                        _make_result(status="failed", errors=[error_data])
                                    ],
                                )
                            ],
                        )
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        err = parsed.suites[0].specs[0].tests[0].results[0].errors[0]
        assert err.message is None
        assert err.stack == "Error: timeout\n    at ..."

    def test_failed_result_with_empty_errors_array(self, tmp_path: pathlib.Path) -> None:
        """A failed result with an empty errors array is still loaded."""
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(
                            ok=False,
                            tests=[
                                _make_test(
                                    status="unexpected",
                                    results=[_make_result(status="failed", errors=[])],
                                )
                            ],
                        )
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        result = parsed.suites[0].specs[0].tests[0].results[0]
        assert result.status == "failed"
        assert result.errors == ()

    def test_legacy_single_error_field(self, tmp_path: pathlib.Path) -> None:
        """The ``error`` (singular) field is used when ``errors`` is absent."""
        result_data: dict[str, Any] = {
            "status": "failed",
            "error": {"message": "legacy error"},
        }
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[
                        _make_spec(
                            ok=False,
                            tests=[_make_test(status="unexpected", results=[result_data])],
                        )
                    ]
                )
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        result = parsed.suites[0].specs[0].tests[0].results[0]
        assert len(result.errors) == 1
        assert result.errors[0].message == "legacy error"


# ===================================================================
# 7. Malformed JSON
# ===================================================================


class TestMalformedJson:
    """Malformed JSON is rejected with a clear error."""

    def test_truncated_json(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "broken.json"
        p.write_text('{"suites": [', encoding="utf-8")
        with pytest.raises(ReportLoadError, match="malformed JSON"):
            load_report(p)

    def test_completely_invalid_text(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "garbage.json"
        p.write_text("this is not json at all!", encoding="utf-8")
        with pytest.raises(ReportLoadError, match="malformed JSON"):
            load_report(p)


# ===================================================================
# 8. Invalid JSON root
# ===================================================================


class TestInvalidJsonRoot:
    """A non-object JSON root is rejected."""

    def test_root_is_array(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, [{"suites": []}])
        with pytest.raises(ReportLoadError, match="invalid report structure"):
            load_report(p)

    def test_root_is_string(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, "just a string")
        with pytest.raises(ReportLoadError, match="invalid report structure"):
            load_report(p)

    def test_root_is_number(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, 42)
        with pytest.raises(ReportLoadError, match="invalid report structure"):
            load_report(p)

    def test_root_is_null(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, None)
        with pytest.raises(ReportLoadError, match="invalid report structure"):
            load_report(p)

    def test_root_is_bool(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, True)
        with pytest.raises(ReportLoadError, match="invalid report structure"):
            load_report(p)


# ===================================================================
# 9. Missing required structural fields
# ===================================================================


class TestMissingRequiredFields:
    """Reports missing required fields are rejected."""

    def test_no_suites_key(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, {"config": {}})
        with pytest.raises(ReportLoadError, match="missing required field"):
            load_report(p)

    def test_suites_is_not_array(self, tmp_path: pathlib.Path) -> None:
        p = _write_json(tmp_path, {"suites": "not an array"})
        with pytest.raises(ReportLoadError, match="invalid field type"):
            load_report(p)

    def test_suite_missing_title(self, tmp_path: pathlib.Path) -> None:
        report = _minimal_report(suites=[{"specs": []}])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="missing or invalid required field"):
            load_report(p)

    def test_spec_missing_title(self, tmp_path: pathlib.Path) -> None:
        suite = _make_suite(specs=[{"ok": True, "tests": []}])
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="missing or invalid required field"):
            load_report(p)

    def test_result_missing_status(self, tmp_path: pathlib.Path) -> None:
        result_data: dict[str, Any] = {"duration": 100}
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[_make_spec(tests=[_make_test(results=[result_data])])]
                )
            ]
        )
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid result status"):
            load_report(p)

    def test_result_invalid_status(self, tmp_path: pathlib.Path) -> None:
        result_data: dict[str, Any] = {"status": "banana"}
        report = _full_report(
            suites=[
                _make_suite(
                    specs=[_make_spec(tests=[_make_test(results=[result_data])])]
                )
            ]
        )
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid result status"):
            load_report(p)


# ===================================================================
# 10. Invalid nested suite/spec/test/result structures
# ===================================================================


class TestInvalidNestedStructures:
    """Non-object entries in structural arrays are rejected."""

    def test_suite_is_not_dict(self, tmp_path: pathlib.Path) -> None:
        report = _minimal_report(suites=["not a dict"])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid structure"):
            load_report(p)

    def test_spec_is_not_dict(self, tmp_path: pathlib.Path) -> None:
        suite = _make_suite(specs=[42])
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid structure"):
            load_report(p)

    def test_test_is_not_dict(self, tmp_path: pathlib.Path) -> None:
        spec = _make_spec(tests=["bad"])
        suite = _make_suite(specs=[spec])
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid structure"):
            load_report(p)

    def test_result_is_not_dict(self, tmp_path: pathlib.Path) -> None:
        test = _make_test(results=[None])
        spec = _make_spec(tests=[test])
        suite = _make_suite(specs=[spec])
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid structure"):
            load_report(p)

    def test_specs_field_is_wrong_type(self, tmp_path: pathlib.Path) -> None:
        suite: dict[str, Any] = {"title": "bad", "specs": "not-a-list"}
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid field type"):
            load_report(p)

    def test_tests_field_is_wrong_type(self, tmp_path: pathlib.Path) -> None:
        spec: dict[str, Any] = {"title": "bad", "tests": "not-a-list"}
        suite = _make_suite(specs=[spec])
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid field type"):
            load_report(p)

    def test_results_field_is_wrong_type(self, tmp_path: pathlib.Path) -> None:
        test: dict[str, Any] = {
            "expectedStatus": "passed",
            "status": "expected",
            "results": "not-a-list",
        }
        spec = _make_spec(tests=[test])
        suite = _make_suite(specs=[spec])
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid field type"):
            load_report(p)

    def test_nested_suites_field_is_wrong_type(self, tmp_path: pathlib.Path) -> None:
        suite: dict[str, Any] = {"title": "bad", "specs": [], "suites": "nope"}
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        with pytest.raises(ReportLoadError, match="invalid field type"):
            load_report(p)


# ===================================================================
# 11. Missing or unreadable file
# ===================================================================


class TestMissingOrUnreadableFile:
    """Missing or unreadable files produce clear errors."""

    def test_file_does_not_exist(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "nonexistent.json"
        with pytest.raises(ReportLoadError, match="file not found"):
            load_report(p)

    def test_path_is_a_directory(self, tmp_path: pathlib.Path) -> None:
        d = tmp_path / "adir"
        d.mkdir()
        with pytest.raises(ReportLoadError, match="path is not a regular file"):
            load_report(d)


# ===================================================================
# 12. Invalid UTF-8 input
# ===================================================================


class TestInvalidUtf8:
    """Non-UTF-8 files are rejected."""

    def test_invalid_utf8_bytes(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "bad_encoding.json"
        p.write_bytes(b'{"suites": [\xff\xfe]}')
        with pytest.raises(ReportLoadError, match="not valid UTF-8"):
            load_report(p)


# ===================================================================
# 13. File-size limit enforcement
# ===================================================================


class TestFileSizeLimit:
    """File size limits are enforced."""

    def test_file_exceeds_default_limit(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "huge.json"
        # Write a file just over the default 10 MiB limit
        p.write_text("x" * (10 * 1024 * 1024 + 1), encoding="utf-8")
        with pytest.raises(ReportLoadError, match="file exceeds size limit"):
            load_report(p)

    def test_file_exceeds_custom_limit(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "small.json"
        p.write_text('{"suites": []}', encoding="utf-8")
        cfg = LoaderConfig(max_size_bytes=5)
        with pytest.raises(ReportLoadError, match="file exceeds size limit"):
            load_report(p, config=cfg)

    def test_file_within_custom_limit(self, tmp_path: pathlib.Path) -> None:
        report = _minimal_report()
        p = _write_json(tmp_path, report)
        cfg = LoaderConfig(max_size_bytes=10 * 1024 * 1024)
        parsed = load_report(p, config=cfg)
        assert isinstance(parsed, ParsedReport)


# ===================================================================
# 14. Invalid size-limit configuration
# ===================================================================


class TestInvalidSizeLimitConfig:
    """Invalid loader configurations are rejected."""

    def test_zero_max_size(self) -> None:
        with pytest.raises(ReportLoadError, match="invalid loader configuration"):
            LoaderConfig(max_size_bytes=0)

    def test_negative_max_size(self) -> None:
        with pytest.raises(ReportLoadError, match="invalid loader configuration"):
            LoaderConfig(max_size_bytes=-1)

    def test_non_int_max_size(self) -> None:
        with pytest.raises(ReportLoadError, match="invalid loader configuration"):
            LoaderConfig(max_size_bytes=10.5)  # type: ignore[arg-type]


# ===================================================================
# 15. Empty but structurally valid report
# ===================================================================


class TestEmptyValidReport:
    """An empty but valid report is not treated as malformed.

    The Playwright JSON reporter schema permits ``"suites": []`` —
    this represents a run where no test files matched.  It is distinct
    from a malformed report missing the ``suites`` key.
    """

    def test_empty_suites(self, tmp_path: pathlib.Path) -> None:
        report = _minimal_report()
        p = _write_json(tmp_path, report)
        parsed = load_report(p)

        assert parsed.suites == ()
        assert parsed.stats is None
        assert parsed.errors == ()

    def test_suite_with_empty_specs(self, tmp_path: pathlib.Path) -> None:
        suite: dict[str, Any] = {"title": "empty file", "specs": []}
        report = _full_report(suites=[suite])
        p = _write_json(tmp_path, report)
        parsed = load_report(p)

        assert len(parsed.suites) == 1
        assert parsed.suites[0].specs == ()
        assert parsed.suites[0].title == "empty file"


# ===================================================================
# Additional edge-case tests
# ===================================================================


class TestAttachments:
    """Attachment references are captured."""

    def test_attachment_metadata_preserved(self, tmp_path: pathlib.Path) -> None:
        result = _make_result(
            attachments=[
                {
                    "name": "screenshot",
                    "contentType": "image/png",
                    "path": "/tmp/screenshot.png",
                }
            ]
        )
        report = _full_report(
            suites=[_make_suite(specs=[_make_spec(tests=[_make_test(results=[result])])])]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        att = parsed.suites[0].specs[0].tests[0].results[0].attachments
        assert len(att) == 1
        assert att[0].name == "screenshot"
        assert att[0].content_type == "image/png"
        assert att[0].path == "/tmp/screenshot.png"


class TestStdio:
    """Stdout/stderr evidence is captured."""

    def test_stdout_strings(self, tmp_path: pathlib.Path) -> None:
        result = _make_result(stdout=["line 1", "line 2"])
        # Need to override the stdout field in the result
        result["stdout"] = ["line 1", "line 2"]
        report = _full_report(
            suites=[_make_suite(specs=[_make_spec(tests=[_make_test(results=[result])])])]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        stdout = parsed.suites[0].specs[0].tests[0].results[0].stdout
        assert stdout == ("line 1", "line 2")

    def test_stdout_text_objects(self, tmp_path: pathlib.Path) -> None:
        result = _make_result()
        result["stdout"] = [{"text": "from object"}]
        report = _full_report(
            suites=[_make_suite(specs=[_make_spec(tests=[_make_test(results=[result])])])]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        stdout = parsed.suites[0].specs[0].tests[0].results[0].stdout
        assert stdout == ("from object",)


class TestTopLevelErrors:
    """Top-level reporter errors are captured."""

    def test_top_level_errors(self, tmp_path: pathlib.Path) -> None:
        report = _full_report(
            errors=[
                {"message": "Config error", "stack": "at config.ts:1:1"},
            ]
        )
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert len(parsed.errors) == 1
        assert parsed.errors[0].message == "Config error"


class TestTags:
    """Test tags are captured."""

    def test_spec_tags(self, tmp_path: pathlib.Path) -> None:
        spec = _make_spec(title="tagged test")
        spec["tags"] = ["@smoke", "@fast"]
        report = _full_report(suites=[_make_suite(specs=[spec])])
        path = _write_json(tmp_path, report)
        parsed = load_report(path)

        assert parsed.suites[0].specs[0].tags == ("@smoke", "@fast")
