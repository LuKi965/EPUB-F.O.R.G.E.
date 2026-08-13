"""K.2 invariant 12 — EPUBCheck asked *before* the file is published.

The last of the audit's fourteen system invariants, and the one left undone
with a reason attached: a gate meant a JVM per book, a few seconds each. The
reason stopped being true. Measured on eight real books, one process held open
validates them in 8.4 s where a process per book took 35.3 s, and three and a
half of every four seconds turned out to be EPUBCheck compiling its schemas
rather than reading anybody's book.

**Where the gate stands matters more than that it exists.** `write_epub` builds
the archive under a temporary name beside the destination and then calls
`os.replace`, which is atomic — that is how a full disk halfway through stopped
being able to leave a truncated file where a good book had been. So "validate
the file and delete it if it is bad" would delete the *previous* good book at
that name. The gate is therefore handed the staging file, one line before the
replace, and a refusal never reaches the destination at all. The first class
below is about nothing else.

**Three settings rather than two**, because two would have forced a bad choice,
and the corpus said so within the hour of the gate being switched on:

* `clean` refuses anything EPUBCheck calls an error. It is right for `strict`,
  whose whole promise is a conformant file, and it refuses books this program
  did nothing wrong to — ones that arrive invalid and cannot be repaired
  without guessing.
* `no-new-errors` validates the source as well and refuses only what this
  rebuild added. That is preserve's promise stated as a gate: carry a
  publisher's defect, never add one.
* `off` publishes and reports, which is what this program did until now.

Read `no-new-errors` knowing what it compares: a 2.0 source is judged by EPUB 2
rules and a 3.3 rebuild by EPUB 3 rules, so "new" can also mean "EPUB 3 has a
rule EPUB 2 did not". A stylesheet pointing at a font the book never contained
is an error in EPUB 3 and silence in EPUB 2, and it arrived that way.
"""

from __future__ import annotations

import os
import zipfile

import pytest

from epubforge import pipeline
from epubforge.pipeline import Status, rebuild
from epubforge.policy import GATES, Policy
from epubforge.validate import ValidationResult, find_epubcheck
from tests.factory import make_legacy_epub, make_modern_epub, write_zip

needs_epubcheck = pytest.mark.skipif(
    find_epubcheck() is None, reason="EPUBCheck is not installed here"
)


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


@pytest.fixture
def good(tmp_path) -> str:
    return make_modern_epub(str(tmp_path / "dobra.epub"))


@pytest.fixture
def invalid(tmp_path) -> str:
    """A book EPUBCheck rejects, and still rejects after a preserve rebuild.

    A link to a document the book does not contain, which is `RSC-007`. The
    first version of this fixture pointed the spine at a manifest id that was
    not there — and the rebuild *repaired* it, so the gate had nothing to refuse
    and six tests failed for the best possible reason. A dead link is the right
    defect here because preserve is documented to carry it: the publisher wrote
    it, removing it would be this program deciding where the reader meant to go.
    """
    source = make_modern_epub(str(tmp_path / "przed.epub"))
    entries = {}
    with zipfile.ZipFile(source) as archive:
        for name in archive.namelist():
            if name != "mimetype":
                entries[name] = archive.read(name)
    document = next(name for name in entries if name.endswith(".xhtml") and "nav" not in name)
    entries[document] = entries[document].replace(
        b"</body>", b'<p><a href="nie-ma-takiego.xhtml">dalej</a></p></body>'
    )
    return write_zip(str(tmp_path / "zla.epub"), entries)


class TestARefusalNeverTouchesWhatIsAlreadyThere:
    """The property the whole design is arranged around."""

    @needs_epubcheck
    def test_the_previous_book_at_that_name_survives(self, tmp_path, invalid):
        destination = tmp_path / "wynik.epub"
        earlier = b"a good book somebody already has" * 40
        destination.write_bytes(earlier)

        # preserve, not strict: strict neutralises the dead link and the book
        # comes out clean, so there would be nothing to refuse. Preserve carries
        # it, which is what puts a refusal in front of an existing file.
        result = rebuild(
            invalid, str(destination), Policy.preset("preserve", validate_before_publish="clean")
        )

        assert result.status is Status.BLOCKED
        assert result.output_path is None
        assert destination.read_bytes() == earlier, (
            "the gate destroyed the file it exists to protect"
        )

    @needs_epubcheck
    def test_and_where_there_was_nothing_nothing_appears(self, tmp_path, invalid):
        destination = tmp_path / "wynik.epub"
        result = rebuild(
            invalid, str(destination), Policy.preset("preserve", validate_before_publish="clean")
        )
        assert result.status is Status.BLOCKED
        assert not destination.exists()

    @needs_epubcheck
    def test_no_staging_file_is_left_behind(self, tmp_path, invalid):
        """The refusal goes out through the same handler that cleans up after a
        crash, so this is really a test that it still does."""
        rebuild(
            invalid,
            str(tmp_path / "wynik.epub"),
            Policy.preset("preserve", validate_before_publish="clean"),
        )
        leftovers = [name for name in os.listdir(tmp_path) if ".part" in name]
        assert not leftovers, leftovers


class TestWhatEachSettingRefuses:
    @needs_epubcheck
    def test_clean_refuses_an_invalid_book(self, tmp_path, invalid):
        result = rebuild(
            invalid,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="clean"),
        )
        assert result.status is Status.BLOCKED
        assert "package.gate-refused" in rules_of(result)

    @needs_epubcheck
    def test_clean_publishes_a_valid_one(self, tmp_path, good):
        result = rebuild(
            good,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="clean"),
        )
        assert result.status.wrote_a_file, result.report.to_text()

    @needs_epubcheck
    def test_no_new_errors_publishes_a_book_that_arrived_broken(self, tmp_path, invalid):
        """The distinction the whole setting exists for. This book is invalid,
        it was invalid before this program touched it, and preserve's promise is
        to hand it back with the defect and the report rather than to refuse
        it."""
        result = rebuild(
            invalid,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="no-new-errors"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert "package.errors-were-already-there" in rules_of(result)

    @needs_epubcheck
    def test_no_new_errors_refuses_one_this_program_broke(self, tmp_path, good, monkeypatch):
        """Forced, because a rebuild that reliably breaks a book is a defect
        rather than a fixture. What is under test is the comparison and the
        refusal, so the comparison is given something to find."""
        real = pipeline.__dict__["_publication_gate"]

        from epubforge import validate as validate_module

        genuine = validate_module.validate

        def fake(path, report=None, **kwargs):
            answer = genuine(path, report, **kwargs)
            if "part" in os.path.basename(path):  # the staging file: the output
                answer.errors += 1
                answer.shapes = {**answer.shapes, "RSC-005: something new": 1}
            return answer

        monkeypatch.setattr(validate_module, "validate", fake)
        assert real is pipeline._publication_gate  # the gate reads it at call time

        result = rebuild(
            good,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="no-new-errors"),
        )
        assert result.status is Status.BLOCKED
        assert "package.gate-refused-new" in rules_of(result)

    @needs_epubcheck
    def test_off_publishes_whatever_it_built(self, tmp_path, invalid):
        result = rebuild(
            invalid,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert result.status.wrote_a_file
        assert "package.gate-refused" not in rules_of(result)


class TestWithNoValidatorTheAnswersDiffer:
    """The asymmetry, and it is a decision rather than an oversight."""

    def test_clean_refuses_because_an_unchecked_claim_is_not_a_claim(
        self, tmp_path, good, monkeypatch
    ):
        monkeypatch.setattr("epubforge.validate.find_epubcheck", lambda: None)
        destination = tmp_path / "out.epub"
        result = rebuild(
            good, str(destination), Policy.preset("preserve", validate_before_publish="clean")
        )
        assert result.status is Status.BLOCKED
        assert "package.gate-cannot-run" in rules_of(result)
        assert not destination.exists()

    def test_no_new_errors_publishes_and_says_it_compared_nothing(
        self, tmp_path, good, monkeypatch
    ):
        monkeypatch.setattr("epubforge.validate.find_epubcheck", lambda: None)
        result = rebuild(
            good,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="no-new-errors"),
        )
        assert result.status.wrote_a_file
        assert "package.gate-skipped" in rules_of(result)

    def test_and_off_does_not_go_looking_for_one(self, tmp_path, good, monkeypatch):
        monkeypatch.setattr("epubforge.validate.find_epubcheck", lambda: None)
        result = rebuild(
            good, str(tmp_path / "out.epub"), Policy.preset("preserve", validate_before_publish="off")
        )
        assert result.status.wrote_a_file
        assert "package.gate-skipped" not in rules_of(result)


class TestWhichModeAsksForWhich:
    def test_strict_refuses_an_invalid_file(self):
        assert Policy.preset("strict").validate_before_publish == "clean"

    def test_preserve_publishes_and_reports(self):
        """Preserve's promise. A book that arrives with a broken link is
        published with the broken link and a report saying so; refusing it would
        make preserve into strict with worse messages."""
        assert Policy.preset("preserve").validate_before_publish == "off"

    def test_and_so_does_minimal(self):
        assert Policy.preset("minimal").validate_before_publish == "off"

    def test_a_misspelt_setting_is_refused_rather_than_read_as_off(self):
        """The one outcome nobody would notice: a typo meaning "no gate"."""
        with pytest.raises(ValueError, match="unknown validation gate"):
            Policy(validate_before_publish="no-new-erors")

    def test_the_settings_are_ordered_least_to_most_refusing(self):
        """Every interface offers them in this order, so it is worth being an
        assertion rather than a convention."""
        assert GATES == ("off", "no-new-errors", "clean")


class TestWhatTheGateFoundOnTheCorpusTheHourItWasSwitchedOn:
    """Two findings, and the second is the reason a gate is worth having.

    Across the public corpus in all three modes, exactly one mode on exactly one
    book introduced an EPUBCheck error: strict, on the srcset gallery. Removing
    a dead `<img>` left the `<picture>` that wrapped it with no `<img>` child,
    which is invalid — an element the reader displays nothing for either way.
    """

    @needs_epubcheck
    def test_a_picture_does_not_outlive_the_image_inside_it(self, tmp_path):
        from tests.public_corpus import build_all

        build_all(tmp_path / "books")
        source = tmp_path / "books" / "srcset-gallery.epub"
        result = rebuild(
            str(source),
            str(tmp_path / "out.epub"),
            Policy.preset("strict", validate_before_publish="off"),
        )
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            markup = "".join(
                archive.read(name).decode("utf-8", "replace")
                for name in archive.namelist()
                if name.endswith(".xhtml")
            )
        assert "<picture" not in markup or "<img" in markup

    @needs_epubcheck
    def test_and_now_no_mode_adds_an_error_to_any_book_in_it(self, tmp_path):
        """The measurement the gate exists to keep true. It runs the whole
        public corpus through every mode, so it is slow, and it is the one
        assertion in this file that would notice a regression anywhere in the
        program rather than in the gate."""
        from epubforge.report import Report
        from epubforge.validate import validate

        from tests.public_corpus import build_all

        build_all(tmp_path / "books")
        introduced: dict[str, list[str]] = {}
        for book in sorted((tmp_path / "books").glob("*.epub")):
            before = validate(str(book), Report(source=str(book)))
            for mode in ("preserve", "strict", "minimal"):
                result = rebuild(
                    str(book),
                    str(tmp_path / f"{mode}-{book.name}"),
                    Policy.preset(mode, validate_before_publish="off"),
                )
                if not result.output_path:
                    continue
                after = validate(result.output_path, Report(source=result.output_path))
                new = [
                    shape
                    for shape, count in after.shapes.items()
                    if count > before.shapes.get(shape, 0)
                ]
                if new:
                    introduced[f"{mode}/{book.stem}"] = new
        assert not introduced, introduced


class TestTheReportSaysEnoughToActOn:
    @needs_epubcheck
    def test_a_refusal_names_the_errors(self, tmp_path, invalid):
        result = rebuild(
            invalid,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="clean"),
        )
        finding = next(f for f in result.report.findings if f.rule == "package.gate-refused")
        assert finding.values["count"] >= 1
        assert finding.values["detail"], "refused, and would not say what for"

    @needs_epubcheck
    def test_a_carried_defect_is_reported_as_the_publishers(self, tmp_path, invalid):
        result = rebuild(
            invalid,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="no-new-errors"),
        )
        finding = next(
            f for f in result.report.findings if f.rule == "package.errors-were-already-there"
        )
        assert finding.values["count"] >= 1
