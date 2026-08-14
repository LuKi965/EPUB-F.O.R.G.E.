"""A misdirected reference is not a dead one, and this program could not tell.

The owner asked how it knows a link is dead rather than merely lost, "and the
content is physically in the document". It did not know. It asked one question —
*does this path resolve to a resource* — and treated `no` as proof the target is
absent from the book. A path miss is not that proof.

Measured before writing any of this, across twenty books of both public corpora
and the owner's shelf: **three dangling references in total, and all three had a
file of that name elsewhere in the same book.** A link written `images/a.png`
from a document in `text/`, where the picture sits at `images/a.png` from the
container root, is one missing `../` — and strict was unlinking pictures that
were right there.

The repair is deliberately narrow. Exactly one file of that name in the book
makes the answer a derivation: there is nothing to choose between. Two makes it
a guess, and a guess is what F-010 settled this project does not make — those
stay as they are and, in strict, are still neutralised as before.
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Action, Risk
from tests.factory import write_zip

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

PACKAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title>'
    "<dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
    "<manifest>{items}</manifest><spine><itemref idref=\"c\"/></spine></package>"
)

#: The shared factory's navigation points at `chapter.xhtml`, and the chapter
#: here is `text/rozdzial.xhtml`. Borrowing it put a second, genuinely dead
#: reference in the book and this file would then have been testing the nav.
NAV = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl"><head>'
    '<meta charset="utf-8"/><title>Spis</title></head><body>'
    '<nav epub:type="toc"><ol><li><a href="text/rozdzial.xhtml">Rozdział</a>'
    "</li></ol></nav></body></html>"
)

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"
)


def page(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
        f"<meta charset=\"utf-8\"/><title>R</title></head><body>{body}</body></html>"
    ).encode()


def book(path, body: str, *, files: dict, items: str) -> str:
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": PACKAGE.format(
            items='<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/><item id="c" href="text/rozdzial.xhtml" '
            'media-type="application/xhtml+xml"/>' + items
        ).encode(),
        "OEBPS/nav.xhtml": NAV.encode(),
        "OEBPS/text/rozdzial.xhtml": page(body),
    }
    entries.update(files)
    return write_zip(str(path), entries)


def documents_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        return "".join(
            archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


#: The defect, exactly as it appears in the wild: the document sits in `text/`
#: and writes the path as if it sat at the root. One `../` short.
MISDIRECTED = '<p><img src="images/rysunek.png" alt="rysunek"/></p>'


@pytest.fixture
def misdirected(tmp_path):
    return book(
        tmp_path / "in.epub",
        MISDIRECTED,
        files={"OEBPS/images/rysunek.png": PNG},
        items='<item id="p" href="images/rysunek.png" media-type="image/png"/>',
    )


class TestTheContentIsFoundWhereItActuallyIs:
    def test_the_reference_is_repointed(self, tmp_path, misdirected):
        result = rebuild(
            misdirected, str(tmp_path / "out.epub"), Policy.preset("preserve")
        )
        assert result.status.wrote_a_file, result.report.to_text()
        sources = re.findall(r'src="([^"]+)"', documents_of(result))
        assert any(source.endswith("rysunek.png") for source in sources), sources
        assert not any(source == "images/rysunek.png" for source in sources)

    def test_the_picture_is_still_in_the_book(self, tmp_path, misdirected):
        """The point of repointing rather than unlinking: the reader sees it."""
        result = rebuild(
            misdirected, str(tmp_path / "out.epub"), Policy.preset("preserve")
        )
        with zipfile.ZipFile(result.output_path) as archive:
            assert any(name.endswith("rysunek.png") for name in archive.namelist())

    def test_it_is_reported(self, tmp_path, misdirected):
        result = rebuild(
            misdirected, str(tmp_path / "out.epub"), Policy.preset("preserve")
        )
        assert "xhtml.reference-relocated" in rules_of(result)

    def test_strict_does_not_unlink_it_any_more(self, tmp_path, misdirected):
        """What this change is for. Strict used to remove the `<img>`, because
        the path missed and a path miss was read as absence."""
        result = rebuild(
            misdirected,
            str(tmp_path / "out.epub"),
            Policy.preset("strict", validate_before_publish="off"),
        )
        assert "<img" in documents_of(result)
        assert "xhtml.dead-reference-neutralised" not in rules_of(result)

    def test_the_balance_sheet_calls_it_risk_free_and_reversible(self, tmp_path, misdirected):
        """Nothing a reader can see changes: the same picture, reached by the
        path it is really at. Both paths are in the report."""
        result = rebuild(
            misdirected, str(tmp_path / "out.epub"), Policy.preset("preserve")
        )
        entry = next(
            change
            for change in result.report.changes
            if change.rule == "xhtml.reference-relocated"
        )
        assert entry.action is Action.REPLACED
        assert entry.risk is Risk.NONE
        assert entry.reversible


class TestTwoCandidatesAreAQuestionAndNotAnAnswer:
    def test_an_ambiguous_name_is_left_alone(self, tmp_path):
        """`logo.png` in two directories: there is nothing to choose between
        them, so this does not choose. The reference stays as the publisher
        wrote it and strict handles it as it always did."""
        source = book(
            tmp_path / "in.epub",
            '<p><img src="logo.png" alt="logo"/></p>',
            files={
                "OEBPS/images/logo.png": PNG,
                "OEBPS/okladka/logo.png": PNG,
            },
            items='<item id="a" href="images/logo.png" media-type="image/png"/>'
            '<item id="b" href="okladka/logo.png" media-type="image/png"/>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "xhtml.reference-relocated" not in rules_of(result)

    def test_a_name_nothing_answers_to_is_still_dead(self, tmp_path):
        """The guard on the other side. This must not turn every dead reference
        into a repair by finding something vaguely similar — there is no
        similarity here, only an exact file name or nothing."""
        source = book(
            tmp_path / "in.epub",
            '<p><img src="images/nie-ma-tego.png" alt="x"/></p>',
            files={"OEBPS/images/rysunek.png": PNG},
            items='<item id="p" href="images/rysunek.png" media-type="image/png"/>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "xhtml.reference-relocated" not in rules_of(result)
        assert "xhtml.dead-reference-kept" in rules_of(result)


class TestAListOfReferencesIsStillReferences:
    """Found by asking why strict could not publish the gallery fixture once
    misdirected references stopped counting as dead ones. The two errors it had
    left were both `srcset`, and neither of them was new.

    `srcset="a.png 1x, a2x.png 2x"` matches no attribute the rewriting reads, so
    it was never rewritten at all. The relayout moves the files, `src` follows
    them, `srcset` stays behind naming a path nothing is at any more — in every
    mode, on every book that has one, reported as a clean rebuild. Strict then
    hid its own damage: it deleted the `<img>` the dead `src` hung off, the
    stale `srcset` went with the element, and EPUBCheck saw nothing to report.
    """

    @pytest.fixture
    def gallery(self, tmp_path):
        """Paths written correctly. Nothing here is misdirected; the only thing
        that moves these files is this program."""
        return book(
            tmp_path / "in.epub",
            '<p><img src="../images/a.png" srcset="../images/a2x.png 2x" '
            'alt="Ilustracja"/></p>',
            files={"OEBPS/images/a.png": PNG, "OEBPS/images/a2x.png": PNG},
            items='<item id="a" href="images/a.png" media-type="image/png"/>'
            '<item id="b" href="images/a2x.png" media-type="image/png"/>',
        )

    def test_the_list_moves_with_the_files(self, tmp_path, gallery):
        result = rebuild(gallery, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file, result.report.to_text()
        srcset = re.search(r'srcset="([^"]+)"', documents_of(result))
        assert srcset, documents_of(result)
        with zipfile.ZipFile(result.output_path) as archive:
            names = set(archive.namelist())
        document = next(n for n in names if n.endswith("rozdzial.xhtml"))
        import posixpath

        target = posixpath.normpath(
            posixpath.join(posixpath.dirname(document), srcset.group(1).split()[0])
        )
        assert target in names, f"{srcset.group(1)} from {document} is not in {sorted(names)}"

    def test_the_descriptor_is_kept(self, tmp_path, gallery):
        """`2x` is what makes the candidate mean anything; a list of URLs with
        the resolutions stripped is not a `srcset`."""
        result = rebuild(gallery, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert re.search(r'srcset="[^"]*\s2x"', documents_of(result))

    def test_a_dead_candidate_does_not_cost_the_illustration(self, tmp_path):
        """Strict, one candidate of two absent. The `<img>` stays: the reader
        still gets the picture from `src`, and the dropped candidate was the
        same picture at another resolution."""
        source = book(
            tmp_path / "in.epub",
            '<p><img src="../images/a.png" srcset="../images/nie-ma.png 2x" '
            'alt="Ilustracja"/></p>',
            files={"OEBPS/images/a.png": PNG},
            items='<item id="a" href="images/a.png" media-type="image/png"/>',
        )
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("strict", validate_before_publish="off"),
        )
        documents = documents_of(result)
        assert "<img" in documents
        assert "nie-ma.png" not in documents
        assert "xhtml.dead-reference-neutralised" in rules_of(result)

    def test_preserve_keeps_the_dead_candidate_and_says_so(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            '<p><img src="../images/a.png" srcset="../images/nie-ma.png 2x" '
            'alt="Ilustracja"/></p>',
            files={"OEBPS/images/a.png": PNG},
            items='<item id="a" href="images/a.png" media-type="image/png"/>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "nie-ma.png" in documents_of(result)
        assert "xhtml.dead-reference-kept" in rules_of(result)


class TestReadingASrcsetTheWayHtmlDoes:
    """A URL may contain a comma, so `split(",")` cuts one reference in half."""

    def test_a_comma_in_a_url_is_not_a_separator(self):
        from epubforge.stages.content import _split_srcset

        assert _split_srcset("a,b.png 2x") == [("a,b.png", "2x")]

    def test_candidates_are_separated(self):
        from epubforge.stages.content import _split_srcset

        assert _split_srcset("a.png 1x, b.png 2x") == [("a.png", "1x"), ("b.png", "2x")]

    def test_a_bare_url_has_no_descriptor(self):
        from epubforge.stages.content import _split_srcset

        assert _split_srcset("  a.png  ") == [("a.png", "")]

    def test_a_trailing_comma_ends_the_candidate_with_no_descriptor(self):
        """The only thing that ends a candidate before its descriptor. Note the
        consequence, which is HTML's and not this program's: `a.png,b.png` with
        no space is *one* URL containing a comma, not two candidates."""
        from epubforge.stages.content import _split_srcset

        assert _split_srcset("a.png, b.png 2x") == [("a.png", ""), ("b.png", "2x")]
        assert _split_srcset("a.png,b.png 2x") == [("a.png,b.png", "2x")]

    def test_width_descriptors_survive_the_round_trip(self):
        from epubforge.stages.content import _join_srcset, _split_srcset

        value = "a.png 400w, b.png 800w"
        assert _join_srcset(_split_srcset(value)) == value


class TestTheMeasurementThatPromptedThis:
    """The corpus case, kept as a test so the number cannot quietly go back."""

    def test_the_gallery_fixture_keeps_the_pictures_it_has(self, tmp_path):
        from epubforge.report import Report
        from epubforge.validate import find_epubcheck, validate

        from tests.public_corpus import build_all

        build_all(tmp_path / "books")
        source = str(tmp_path / "books" / "srcset-gallery.epub")
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "xhtml.reference-relocated" in rules_of(result)

        if find_epubcheck() is None:
            pytest.skip("EPUBCheck is not installed here")
        before = validate(source, Report(source=source))
        after = validate(result.output_path, Report(source=result.output_path))
        assert after.errors < before.errors, (
            f"{before.errors} missing-resource errors in, {after.errors} out — "
            f"the repointing recovered nothing"
        )
