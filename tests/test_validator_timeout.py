"""The validator's allowance grows with the file, and running out of it is
named for what it is.

Audit 2026-09-03, A-05: the largest book on the shelf (28.6 MB, 9 810
documents) got no answer from the warm JVM within a fixed 300 s, the cold
path was then given the same 300 s and ran out too, and the strict gate
refused a clean book over a stopwatch. Three things follow, each held here:
the allowance is a function of size with named constants; a warm validator
that fell silent for the whole allowance is not retried cold for the same
allowance again; and the report says how long was waited on how big a file,
rather than "could not be run at all".
"""

from __future__ import annotations

import subprocess

import pytest

from epubforge import validate as validate_module
from epubforge.report import Report
from epubforge.validate import (
    VALIDATION_BASE_SECONDS,
    VALIDATION_SECONDS_PER_MEGABYTE,
    validate,
    validation_timeout,
)


def a_file_of(tmp_path, megabytes: float):
    path = tmp_path / f"{megabytes}.epub"
    with open(path, "wb") as handle:
        handle.truncate(int(megabytes * 1_000_000))
    return str(path)


class TestTheAllowanceGrowsWithTheFile:
    def test_an_empty_file_gets_the_base(self, tmp_path):
        assert validation_timeout(a_file_of(tmp_path, 0)) == VALIDATION_BASE_SECONDS

    def test_each_megabyte_buys_its_seconds(self, tmp_path):
        assert validation_timeout(a_file_of(tmp_path, 10)) == pytest.approx(
            VALIDATION_BASE_SECONDS + 10 * VALIDATION_SECONDS_PER_MEGABYTE
        )

    def test_the_shelfs_largest_book_now_fits(self, tmp_path):
        """28.6 MB: 300 s was not enough for it (record 044); the allowance
        it gets now is well past what the same file took cold (1 min 49 s)."""
        assert validation_timeout(a_file_of(tmp_path, 28.6)) > 600

    def test_a_file_that_is_not_there_still_gets_the_base(self, tmp_path):
        assert validation_timeout(str(tmp_path / "nie-ma.epub")) == VALIDATION_BASE_SECONDS

    def test_the_constants_are_named_and_positive(self):
        assert VALIDATION_BASE_SECONDS > 0 and VALIDATION_SECONDS_PER_MEGABYTE > 0


def pretend_the_validator_exists(monkeypatch):
    monkeypatch.setattr(validate_module, "find_epubcheck", lambda: ["java", "-jar", "x.jar"])


class TestRunningOutIsNamed:
    def test_a_cold_run_that_times_out_is_reported_with_its_numbers(self, tmp_path, monkeypatch):
        pretend_the_validator_exists(monkeypatch)
        monkeypatch.setattr(validate_module.SHARED, "check", lambda *a, **k: None)
        monkeypatch.setattr(validate_module.SHARED, "timed_out", False)

        def hang(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        monkeypatch.setattr(validate_module.spawn, "run", hang)
        book = a_file_of(tmp_path, 5)
        report = Report(source=book)
        result = validate(book, report)
        assert not result.available
        (finding,) = [f for f in report.findings if f.rule.startswith("epubcheck.")]
        assert finding.rule == "epubcheck.no-answer"
        assert finding.values["size"] == "5.0"
        assert finding.values["seconds"] == int(validation_timeout(book))

    def test_a_warm_validator_that_fell_silent_is_not_retried_cold(self, tmp_path, monkeypatch):
        pretend_the_validator_exists(monkeypatch)
        calls = []

        def silent(*args, **kwargs):
            validate_module.SHARED.timed_out = True
            return None

        monkeypatch.setattr(validate_module.SHARED, "check", silent)
        monkeypatch.setattr(validate_module.spawn, "run", lambda *a, **k: calls.append(a))
        book = a_file_of(tmp_path, 1)
        report = Report(source=book)
        result = validate(book, report)
        assert not result.available
        assert calls == [], "the cold path was run for the same allowance again"
        assert any(f.rule == "epubcheck.no-answer" for f in report.findings)

    def test_any_other_reason_for_none_still_goes_the_old_way(self, tmp_path, monkeypatch):
        pretend_the_validator_exists(monkeypatch)
        calls = []

        def declined(*args, **kwargs):
            validate_module.SHARED.timed_out = False
            return None

        monkeypatch.setattr(validate_module.SHARED, "check", declined)

        def cold(command, **kwargs):
            calls.append(kwargs["timeout"])
            raise OSError("no java here")

        monkeypatch.setattr(validate_module.spawn, "run", cold)
        book = a_file_of(tmp_path, 2)
        report = Report(source=book)
        assert not validate(book, report).available
        assert calls == [validation_timeout(book)]
        assert any(f.rule == "epubcheck.failed" for f in report.findings)

    def test_the_daemon_passes_its_allowance_through(self, tmp_path, monkeypatch):
        pretend_the_validator_exists(monkeypatch)
        seen = []

        def record(path, json_path, timeout):
            seen.append(timeout)
            validate_module.SHARED.timed_out = False
            return None

        monkeypatch.setattr(validate_module.SHARED, "check", record)
        monkeypatch.setattr(validate_module.spawn, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        book = a_file_of(tmp_path, 3)
        validate(book, Report(source=book))
        assert seen == [validation_timeout(book)]
