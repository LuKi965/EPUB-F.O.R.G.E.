"""WP-2 from the 2026-08-14 baseline: F-011 and F-004.

Two ways a rebuild can hand back something other than the book it was given,
both reproduced against a release I had called clean.

**F-011 — the writer filtering metadata by prefix.** Two lines did it. One was
`if name.startswith("calibre:"): continue`, and the two calibre entries this
model understands never reach it — the reader consumes `calibre:series` and
`calibre:series_index` into fields — so the only things it removed were the
ones nothing else carried. The other was `prop.startswith(("schema:",
"rendition:", "media:"))`, whose intent was "do not write `schema:accessMode`
twice" and whose effect was deleting three entire vocabularies whether or not
this rebuild had anything to say about them.

The fix is not a longer list. The writer now reads back the `<meta>` lines it
has already emitted and skips only what it has actually said, because a
hand-kept list of "properties we generate" is a second copy of the emitters and
the copy is what drifted.

**F-004 — recovery presented as a reading.** `recover=True` accepted a package
document with crossed tags, produced the title `ORIGINALpl` out of
`<dc:title>ORIGINAL<dc:language>pl</dc:title></dc:language>`, dropped the
language, and published the book with no finding of any kind. The bytes are
still parsed the same way; what changed is that the strict parser is asked
first, so "this file says X" and "a parser guessed X" stop being the same
answer. The owner's decision on what to do about it was neither refuse nor
publish quietly: *show the differences and let them be corrected.*
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from epubforge.report import Report
from epubforge.validate import find_epubcheck, validate
from tests.factory import MODERN_NAV, write_zip

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title></head><body><p>Tekst rozdziału.</p></body></html>"
)


def package(metadata: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="pub-id" prefix="wydawca: https://example.org/w#">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"{metadata}</metadata>"
        '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/><item id="c" href="chapter.xhtml" '
        'media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c"/></spine></package>'
    )


def book(path, metadata: str) -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": package(metadata).encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": PAGE.encode(),
        },
    )


def opf_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".opf"))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


WELL_FORMED = (
    '<dc:identifier id="pub-id">urn:uuid:1</dc:identifier>'
    "<dc:title>Tytuł</dc:title><dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>'
)


class TestF011NothingIsDroppedForTheVocabularyItIsIn:
    @pytest.fixture
    def rebuilt(self, tmp_path):
        # Values the schemas accept, because the point is which *statements*
        # survive and an invented value for `rendition:spread` fails EPUBCheck
        # on its own — which is how the first draft of this fixture failed, and
        # a test whose fixture is invalid proves nothing about the program.
        extra = (
            '<meta name="calibre:custom-order" content="ORDER-12345"/>'
            '<meta name="calibre:rating" content="8"/>'
            '<meta property="schema:accessibilityHazard">noFlashingHazard</meta>'
            '<meta property="rendition:spread">both</meta>'
            '<meta property="media:narrator">MEDIA-KEEP-ME</meta>'
            '<meta property="wydawca:staz">CUSTOM-PREFIX-KEPT</meta>'
        )
        source = book(tmp_path / "rich.epub", WELL_FORMED + extra)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file, result.report.to_text()
        return result

    @pytest.mark.parametrize(
        "marker",
        ["ORDER-12345", "schema:accessibilityHazard", "rendition:spread",
         "MEDIA-KEEP-ME", "CUSTOM-PREFIX-KEPT"],
    )
    def test_every_control_marker_survives(self, rebuilt, marker):
        """Five statements in five vocabularies. Before this, four of the five
        disappeared and the fifth — the one with a prefix nobody had thought to
        filter — came through, which is what made the filter visible at all."""
        assert marker in opf_of(rebuilt)

    def test_a_calibre_field_nothing_else_carries_survives(self, rebuilt):
        assert "calibre:rating" in opf_of(rebuilt)

    def test_and_the_result_still_validates(self, rebuilt):
        """Carrying an EPUB 2 `<meta name>` back into an EPUB 3 package is the
        obvious way this fix could have made things worse."""
        if find_epubcheck() is None:
            pytest.skip("EPUBCheck is not installed here")
        answer = validate(rebuilt.output_path, Report(source=rebuilt.output_path))
        assert answer.errors == 0, answer.messages[:5]

    def test_what_the_rebuild_states_itself_is_not_written_twice(self, tmp_path):
        """The half of the old filter that was right: `dcterms:modified` is
        written by this program from the model, and the source's copy must not
        appear beside it."""
        source = book(tmp_path / "dup.epub", WELL_FORMED)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert opf_of(result).count('property="dcterms:modified"') == 1

    def test_and_a_supersession_is_reported_rather_than_silent(self, tmp_path):
        """`schema:accessMode` is written by the accessibility stage from what
        the book actually contains, so the source's copy is genuinely superseded
        — and the report says so instead of the statement simply not appearing.
        That distinction is the whole finding: silence and a decision look
        identical in the output."""
        source = book(
            tmp_path / "dup.epub",
            WELL_FORMED + '<meta property="schema:accessMode">textual</meta>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "metadata.property-superseded" in rules_of(result)


#: Crossed tags. `recover=True` accepts this and reads the title as "ORIGINALpl"
#: with no language — which is a defensible guess and not what the file says.
MALFORMED = (
    '<dc:identifier id="pub-id">urn:uuid:1</dc:identifier>'
    '<dc:title id="title">ORIGINAL<dc:language>pl</dc:title></dc:language>'
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>'
)


class TestF004AGuessIsNotAReading:
    @pytest.fixture
    def rebuilt(self, tmp_path):
        source = book(tmp_path / "malformed.epub", MALFORMED)
        return rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))

    def test_the_recovery_is_reported_at_all(self, rebuilt):
        """It was not. That is the finding: a parser rewrote the book's own
        description of itself and the report had nothing to say."""
        assert "reader.xml-recovered" in rules_of(rebuilt)

    def test_the_report_names_the_fields_that_came_out_of_the_guess(self, rebuilt):
        finding = next(
            f for f in rebuilt.report.findings if f.rule == "package.metadata-from-a-guess"
        )
        assert "title" in finding.values["fields"]

    def test_nobody_asked_means_nothing_written(self, rebuilt):
        """DELTA-2026-08-15-001, and it corrects this very test.

        The old assertion said "publishing is still the outcome; the status is
        the warning", which was the owner's decision as far as it went — show
        the difference, let it be corrected — and it quietly assumed somebody
        was there to see the difference. With nobody there, the guess went into
        the book: `ORIGINALpl` became the title in somebody's library, a string
        no publisher ever wrote and this program's own parser assembled out of
        two crossed elements.

        "Unanswered changes nothing" was true of the book and false of the
        outcome. Now it is true of both.
        """
        assert rebuilt.status is Status.BLOCKED
        assert not rebuilt.output_path
        assert "package.metadata-unconfirmed" in rules_of(rebuilt)

    def test_keeping_the_guess_is_a_decision_and_publishes(self, tmp_path):
        """The other half, and the reason this is a question rather than a
        refusal: somebody who looks at `ORIGINALpl` and decides it is fine has
        decided, and this program does not get a vote."""
        from epubforge import decisions

        class Keeps:
            def ask(self, question):
                return decisions.Answer(option=decisions.KEEP)

        source = book(tmp_path / "malformed.epub", MALFORMED)
        result = rebuild(
            source, str(tmp_path / "out.epub"), Policy.preset("preserve"), asker=Keeps()
        )
        assert result.status is Status.SUCCEEDED_WITH_PROBLEMS
        assert result.output_path

    def test_consent_can_be_given_in_advance(self, tmp_path):
        """For a batch nobody is watching. One field, set on purpose."""
        source = book(tmp_path / "malformed.epub", MALFORMED)
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", accept_reconstructed_metadata=True),
        )
        assert result.status is Status.SUCCEEDED_WITH_PROBLEMS
        assert result.output_path

    def test_a_field_written_by_hand_is_not_a_guess(self, tmp_path):
        """And therefore is not asked about and does not hold the book back.
        Somebody typing the title has settled it more firmly than any answer
        to a question about it could."""
        source = book(tmp_path / "malformed.epub", MALFORMED)
        policy = Policy.preset("preserve")
        policy.metadata_overrides["title"] = "Tytuł prawdziwy"
        policy.metadata_overrides["language"] = "pl"
        policy.metadata_overrides["identifier"] = "urn:uuid:1"
        result = rebuild(source, str(tmp_path / "out.epub"), policy)
        assert result.output_path, result.report.to_text()

    def test_the_fields_can_be_corrected_on_the_spot(self, tmp_path):
        """"Let them be corrected" is only true if correcting them works. The
        window and the command line both write these, and this is the path they
        take."""
        source = book(tmp_path / "malformed.epub", MALFORMED)
        policy = Policy.preset("preserve")
        policy.metadata_overrides["title"] = "Tytuł prawdziwy"
        policy.metadata_overrides["language"] = "pl"
        policy.metadata_overrides["identifier"] = "urn:uuid:1"
        policy.default_language = "pl"
        result = rebuild(source, str(tmp_path / "out.epub"), policy)
        opf = opf_of(result)
        assert "Tytuł prawdziwy" in opf
        assert "ORIGINALpl" not in opf
        assert "<dc:language>pl</dc:language>" in opf

    def test_a_well_formed_package_says_nothing_about_recovery(self, tmp_path):
        """The guard. A warning on every book is a warning nobody reads."""
        source = book(tmp_path / "fine.epub", WELL_FORMED)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "reader.xml-recovered" not in rules_of(result)
        assert "package.metadata-from-a-guess" not in rules_of(result)
        assert result.status is Status.SUCCEEDED

    def test_the_complaint_is_carried_so_somebody_can_see_what_broke(self, rebuilt):
        finding = next(f for f in rebuilt.report.findings if f.rule == "reader.xml-recovered")
        assert finding.values["detail"], "recovered, and would not say from what"
        assert finding.location.endswith(".opf")
