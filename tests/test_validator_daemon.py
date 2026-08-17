"""One JVM instead of one per book — and the same answer out of it.

The owner asked whether EPUBCheck-as-a-publication-gate really means a JVM per
book, and whether that can be made faster or replaced. Measured here, on eight
real books between 0.8 MB and 23 MB, with the JVM options already tuned:

===============================  =========
one JVM per book, eight books      35.3 s
one JVM held open, eight books       8.4 s
===============================  =========

The interesting number is not the ratio, it is where the time was. A 1.8 KB
book cost 3602 ms. The JVM starts in 37 ms and has EPUBCheck's classes loaded
by 125 ms, so the other three and a half seconds are EPUBCheck compiling its
RelaxNG and Schematron schemas — work that has nothing to do with the book and
that a new process pays for again every time.

**Speed is worth nothing here if the answer changes.** EPUBCheck is the
authority this program defers to; a faster path that disagrees with it is not a
faster path, it is a second opinion. So the driver does not reimplement any
part of the checking or the reporting: it calls `EpubChecker.run` with the argv
the command line would have used, and EPUBCheck writes the same JSON. What is
tested below is that the two paths agree — on clean books, on broken ones, and
on the same book asked twice — and that every way the shared process can fail
ends in the old path rather than in an error.
"""

from __future__ import annotations

import os
import time

import pytest

from epubforge import validate as validate_module
from epubforge.validate import ENV_SHARED, SharedValidator, find_epubcheck, validate
from tests.factory import make_modern_epub, write_zip

pytestmark = pytest.mark.skipif(
    find_epubcheck() is None, reason="EPUBCheck is not installed here"
)

#: AUD-001. A machine with a JRE and no JDK cannot build the driver, so the
#: shared process cannot exist there — and five tests below said so by failing.
#: They are not defects: the runtime falls back to a JVM per book, which is the
#: behaviour this program had before the daemon and still has, and the tests
#: that prove *that* path keep running here without a compiler.
#:
#: Deliberately per test rather than on the module or the class. A blanket skip
#: would take the fallback tests down with it, and the fallback is exactly what
#: a JRE-only machine runs — hiding it would be the shortcut this is not.
#:
#: Not solved by committing a compiled class either, and the reason is not its
#: size. The release already compiles one at packaging time and ships it beside
#: `epubcheck.jar` (`packaging/build.py`), so nobody using the installer needs a
#: compiler; a class in the source tree would be a second copy of
#: `ForgeValidator.java` with nothing forcing the two to agree, and its bytecode
#: version would pin the very JRE it was meant to support.
needs_the_daemon = pytest.mark.skipif(
    validate_module._driver_class() is None,
    reason="the validator driver is not built and no javac was found to build it",
)


def verdict(result) -> tuple:
    """Everything a caller can see, so "the same answer" means all of it."""
    return (
        result.available,
        result.fatal,
        result.errors,
        result.warnings,
        tuple(sorted(result.codes.items())),
        tuple(result.messages),
    )


def one_shot(path: str):
    """The old way, forced, whatever the environment says."""
    previous = os.environ.get(ENV_SHARED)
    os.environ[ENV_SHARED] = "0"
    try:
        return validate(path)
    finally:
        if previous is None:
            os.environ.pop(ENV_SHARED, None)
        else:
            os.environ[ENV_SHARED] = previous


@pytest.fixture(scope="module")
def books(tmp_path_factory) -> dict[str, str]:
    """A good book, a book with a real EPUBCheck error, and a broken archive."""
    room = tmp_path_factory.mktemp("validator")
    good = make_modern_epub(str(room / "good.epub"))

    # An `<itemref>` naming nothing: RSC-005 from the package document, which is
    # an error EPUBCheck reports rather than a file it refuses to open.
    import zipfile

    entries = {}
    with zipfile.ZipFile(good) as archive:
        for name in archive.namelist():
            if name == "mimetype":
                continue  # write_zip lays that one down itself, first and stored
            entries[name] = archive.read(name)
    opf = next(name for name in entries if name.endswith(".opf"))
    entries[opf] = entries[opf].replace(b"</spine>", b'<itemref idref="nie-ma"/></spine>')
    broken_package = write_zip(str(room / "broken-package.epub"), entries)

    not_a_zip = room / "not-a-zip.epub"
    not_a_zip.write_bytes(b"to nie jest archiwum" * 40)

    return {"good": good, "broken": broken_package, "garbage": str(not_a_zip)}


class TestTheFastAnswerIsTheSameAnswer:
    """The only thing that makes the speed-up permissible."""

    @pytest.mark.parametrize("which", ["good", "broken", "garbage"])
    def test_both_paths_agree(self, books, which):
        assert verdict(validate(books[which])) == verdict(one_shot(books[which]))

    def test_a_book_with_errors_still_reports_them(self, books):
        result = validate(books["broken"])
        assert result.available
        assert result.errors or result.fatal, "the fixture stopped being broken"

    def test_asking_twice_answers_twice_the_same(self, books):
        """State kept between books is the risk a shared process introduces and
        a fresh process cannot have. A checker that remembered the last book
        would show up here first."""
        first = verdict(validate(books["broken"]))
        validate(books["good"])
        assert verdict(validate(books["broken"])) == first

    def test_a_clean_book_is_clean_after_a_broken_one(self, books):
        validate(books["garbage"])
        assert validate(books["good"]).clean


class TestEveryWayItCanFailEndsInTheOldPath:
    """`None` out of the shared validator means "one process, one book" — the
    behaviour this program had before any of this existed."""

    def test_switched_off_it_says_so_and_still_validates(self, books, monkeypatch):
        monkeypatch.setenv(ENV_SHARED, "0")
        shared = SharedValidator()
        assert shared.check(books["good"], "/tmp/nie-uzyte.json", timeout=30) is None
        assert ENV_SHARED in shared.reason
        assert validate(books["good"]).available

    @needs_the_daemon
    def test_a_process_that_dies_between_books_is_replaced(self, books):
        shared = SharedValidator()
        try:
            first = shared.check(books["good"], _json(), timeout=300)
            assert first is not None, shared.reason
            shared._process.kill()
            shared._process.wait(timeout=30)
            # The next call finds a corpse, starts a new process, and answers.
            assert shared.check(books["good"], _json(), timeout=300) is not None
        finally:
            shared.stop()

    @needs_the_daemon
    def test_an_answer_that_is_not_a_number_drops_the_process(self, books, monkeypatch):
        shared = SharedValidator()
        try:
            assert shared.check(books["good"], _json(), timeout=300) is not None
            monkeypatch.setattr(validate_module, "_read_line", lambda p, t: "nie liczba")
            assert shared.check(books["good"], _json(), timeout=300) is None
            assert "unreadable" in shared.reason
            assert shared._process is None, "a desynchronised pipe was kept"
        finally:
            shared.stop()

    @needs_the_daemon
    def test_silence_past_the_timeout_kills_it(self, books, monkeypatch):
        shared = SharedValidator()
        try:
            assert shared.check(books["good"], _json(), timeout=300) is not None
            monkeypatch.setattr(validate_module, "_read_line", lambda p, t: None)
            assert shared.check(books["good"], _json(), timeout=1) is None
            assert "no answer" in shared.reason
            assert shared._process is None
        finally:
            shared.stop()

    def test_with_no_driver_class_it_declines_rather_than_guesses(self, books, monkeypatch):
        monkeypatch.setattr(validate_module, "_driver_class", lambda: None)
        shared = SharedValidator()
        assert shared.check(books["good"], _json(), timeout=30) is None
        assert "driver" in shared.reason
        # And the caller still gets a verdict, because the fallback is the point.
        assert validate(books["good"]).available

    @needs_the_daemon
    def test_a_process_started_for_another_jar_is_not_reused(self, books, monkeypatch):
        """Found by accident, and the accident is the point.

        A test elsewhere stubs the EPUBCheck lookup and expects its stub to be
        used. It passed alone and failed in a full run: by then a real validator
        process was already alive, and a live process consulted nothing — it had
        read the lookup once, at start-up, and answered from the old jar for the
        rest of the session. Alone that is a confusing test failure; in a
        program it is `EPUBCHECK_JAR` pointed at a new release and a verdict
        still coming from the old one, with nothing said.
        """
        shared = SharedValidator()
        try:
            assert shared.check(books["good"], _json(), timeout=300) is not None
            live = shared._process
            monkeypatch.setattr(validate_module, "find_epubcheck", lambda: ["epubcheck-inny"])
            assert shared.check(books["good"], _json(), timeout=300) is None
            assert live.poll() is not None, "the old process was left running"
        finally:
            shared.stop()

    def test_stopping_it_twice_is_not_an_error(self):
        shared = SharedValidator()
        shared.stop()
        shared.stop()


class TestItIsActuallyFaster:
    """A shared process that is not faster is complexity for nothing."""

    @needs_the_daemon
    def test_the_second_book_costs_a_fraction_of_the_first(self, books):
        shared = SharedValidator()
        try:
            started = time.monotonic()
            assert shared.check(books["good"], _json(), timeout=300) is not None
            first = time.monotonic() - started

            started = time.monotonic()
            assert shared.check(books["good"], _json(), timeout=300) is not None
            second = time.monotonic() - started
        finally:
            shared.stop()
        # Measured at roughly 3.5 s against 0.05 s for this book; a tenth is a
        # wide margin that still fails loudly if the schemas ever get recompiled
        # per request.
        assert second < first / 10, f"first {first:.2f}s, second {second:.2f}s"

    def test_the_driver_source_ships_with_the_package(self):
        """The release compiles it at packaging time. If it is not in the
        package there is nothing to compile and every book pays the JVM."""
        assert validate_module._driver_source().is_file()


def _json() -> str:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        return handle.name
