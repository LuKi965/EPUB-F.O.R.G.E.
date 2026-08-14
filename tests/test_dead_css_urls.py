"""F-017: strict neutralises a dead link in a document and not in a stylesheet.

`ContentStage` has done this for documents since 0.2.19 — a strict rebuild
unlinks an `<a href>` to a file the book does not contain, and removes an
element whose `src` points at nothing. A stylesheet got the same reference and a
warning: `css.url-unresolved`, and the `url()` left exactly as found.

That was tolerable while EPUBCheck was advisory. It stopped being tolerable in
0.2.23, when strict grew a gate that refuses to publish an invalid file: a book
whose `@font-face` names a font the archive does not contain is invalid EPUB 3,
strict could not make it valid, and so strict could not produce that book at
all.

**What "neutralise" means depends on the property**, and the difference is the
whole of this change:

* `src` and `cursor` take a *list* of candidates, and dropping the dead one
  while keeping the rest is what a fallback list is for. `none` is not a value
  either property accepts, so substituting it would trade an unresolved
  reference for an invalid declaration.
* everywhere else the value is one image, and `none` is how CSS spells "there
  is no image here" — which is what a broken url rendered as anyway.

**A correction to the finding, measured.** The baseline records F-017 as the
reason strict refused two of the twelve public corpus books. It is not: those
two are refused for a package declaring media-overlay class names with no CSS
defining them, and for a fixed-layout document with no `viewport`. Neither is a
dead url and neither can be repaired without inventing something — a stylesheet
rule nobody wrote, or page dimensions nobody stated. Strict refusing them is
strict working. What F-017 actually blocked is the case below, and the suite's
own legacy fixture was one of them.
"""

from __future__ import annotations

import re
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
    '<title>R</title><link rel="stylesheet" type="text/css" href="style.css"/></head>'
    "<body><p>Tekst rozdziału.</p></body></html>"
)

PACKAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title>'
    "<dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
    "<manifest>{items}</manifest>"
    '<spine><itemref idref="c"/></spine></package>'
)

BASE_ITEMS = (
    '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    '<item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
    '<item id="s" href="style.css" media-type="text/css"/>'
)

#: A one-pixel PNG, so a book can carry a picture a stylesheet really can reach.
#: Generated rather than typed: the first version of this constant was hand
#: written and one byte wrong, EPUBCheck called it "Corrupted image file", and
#: the strict gate refused the book — a fixture failing a test about something
#: else entirely.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"
)


def book(path, css: str, *, extra_files: dict | None = None, extra_items: str = "") -> str:
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": PACKAGE.format(items=BASE_ITEMS + extra_items).encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/chapter.xhtml": PAGE.encode(),
        "OEBPS/style.css": css.encode(),
    }
    entries.update(extra_files or {})
    return write_zip(str(path), entries)


def stylesheet_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".css"))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestASingleDeadImageBecomesNone:
    CSS = "body { background-image: url(nie-ma-takiego.png); color: black; }"

    def test_strict_neutralises_it(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        css = stylesheet_of(result)
        assert "nie-ma-takiego.png" not in css
        assert "none" in css

    def test_and_says_so(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert "css.dead-url-neutralised" in rules_of(result)

    def test_the_rest_of_the_declaration_block_survives(self, tmp_path):
        """A neutralisation that took the `color` with it would be a removal
        wearing a repair's name."""
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert "color" in stylesheet_of(result)

    def test_preserve_leaves_it_and_reports_it(self, tmp_path):
        """Preserve's promise: the publisher's defect comes through, named.
        This is the half of the finding that was already right."""
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "nie-ma-takiego.png" in stylesheet_of(result)
        assert "css.url-unresolved" in rules_of(result)
        assert "css.dead-url-neutralised" not in rules_of(result)


class TestAFallbackListLosesOnlyTheDeadCandidate:
    """The case the audit names, and the one `none` would have broken."""

    CSS = (
        "@font-face { font-family: Moja; "
        "src: url(nie-ma.woff2) format('woff2'), url(jest.ttf) format('truetype'); }"
        "body { font-family: Moja, serif; }"
    )

    @pytest.fixture
    def rebuilt(self, tmp_path):
        return rebuild(
            book(
                tmp_path / "in.epub",
                self.CSS,
                extra_files={"OEBPS/jest.ttf": b"\x00\x01\x00\x00" + b"font" * 40},
                extra_items='<item id="f" href="jest.ttf" media-type="font/ttf"/>',
            ),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )

    def test_the_surviving_source_is_kept(self, rebuilt):
        assert rebuilt.status.wrote_a_file, rebuilt.report.to_text()
        assert "jest.ttf" in stylesheet_of(rebuilt)

    def test_the_dead_one_is_gone(self, rebuilt):
        assert "nie-ma.woff2" not in stylesheet_of(rebuilt)

    def test_and_none_was_not_substituted_into_a_src(self, rebuilt):
        """`src: none` is not a declaration CSS has. Getting this wrong trades
        an unresolved reference for an invalid one."""
        css = stylesheet_of(rebuilt)
        source_line = next(line for line in css.splitlines() if "src" in line)
        assert "none" not in source_line

    def test_the_face_still_exists(self, rebuilt):
        assert "@font-face" in stylesheet_of(rebuilt)


class TestAFaceWithNothingLeftGoesEntirely:
    CSS = (
        "@font-face { font-family: Moja; src: url(nie-ma.woff2) format('woff2'); }"
        "body { font-family: Moja, serif; }"
    )

    @pytest.fixture
    def rebuilt(self, tmp_path):
        return rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )

    def test_the_whole_rule_is_removed(self, rebuilt):
        """A face that can load nothing leaves a `font-family` name resolving to
        a font that does not exist, which is the same defect one level along —
        and the one that makes a page fall back to a system font silently."""
        assert rebuilt.status.wrote_a_file, rebuilt.report.to_text()
        assert "@font-face" not in stylesheet_of(rebuilt)

    def test_the_rules_that_use_the_family_are_untouched(self, rebuilt):
        """Not this change's business. `font-family: Moja, serif` falls back to
        serif, which is what it was written to do."""
        assert "serif" in stylesheet_of(rebuilt)


class TestAReferenceThatResolvesIsNotTouched:
    """The other half of every removal in this program: proving it only removes
    what it means to. A percent-encoded name is the case that looks dead to a
    string comparison and is not."""

    def test_an_encoded_name_that_exists_survives(self, tmp_path):
        css = 'body { background-image: url("obraz%20ze%20spacja.png"); }'
        result = rebuild(
            book(
                tmp_path / "in.epub",
                css,
                extra_files={"OEBPS/obraz ze spacja.png": PNG},
                extra_items='<item id="p" href="obraz%20ze%20spacja.png" media-type="image/png"/>',
            ),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert "css.dead-url-neutralised" not in rules_of(result)
        assert "none" not in stylesheet_of(result)

    def test_a_data_uri_is_not_a_missing_file(self, tmp_path):
        css = "body { background-image: url(data:image/gif;base64,R0lGODlhAQABAAAAACw=); }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert "data:image/gif" in stylesheet_of(result)

    def test_a_remote_url_is_not_a_missing_file_either(self, tmp_path):
        """Asked in preserve, and the reason is worth writing down.

        EPUB 3 allows a remote resource only for audio, video and fonts — a
        remote `background-image` is not "missing", it is *forbidden*, and the
        publication gate refuses the book for that whether or not this
        neutraliser exists. Asking it in strict would test the gate. What is
        under test here is that a remote url is not mistaken for a file the book
        has lost, which is a statement about this function.
        """
        css = "body { background-image: url(https://example.org/tlo.png); }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "example.org" in stylesheet_of(result)
        assert "css.dead-url-neutralised" not in rules_of(result)


class TestTheResultIsStillAStylesheetAndStillABook:
    def test_what_comes_out_parses(self, tmp_path):
        import cssutils

        css = (
            "@font-face { font-family: A; src: url(nie-ma.woff2); }"
            "body { background-image: url(tez-nie.png); color: red; }"
            "p { list-style-image: url(ani-to.gif); }"
        )
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        sheet = cssutils.parseString(stylesheet_of(result), validate=False)
        assert sheet is not None
        assert "color: red" in " ".join(stylesheet_of(result).split())

    @pytest.mark.skipif(find_epubcheck() is None, reason="EPUBCheck is not installed here")
    def test_and_the_validator_accepts_the_book(self, tmp_path):
        """The reason this finding is worth closing at all: without it, strict
        cannot publish this book."""
        css = "@font-face { font-family: A; src: url(nie-ma.woff2); }"
        source = book(tmp_path / "in.epub", css)

        before = validate(source, Report(source=source))
        assert before.errors, "the fixture stopped being the case under test"

        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("strict"))
        assert result.status is Status.SUCCEEDED, result.report.to_text()
        after = validate(result.output_path, Report(source=result.output_path))
        assert after.errors == 0, after.messages[:5]

    def test_it_is_entered_in_the_balance_sheet(self, tmp_path):
        """Markup taken out of somebody's stylesheet, so BA-2026-003 applies:
        appearance risk, and nothing in the output to put it back."""
        from epubforge.report import Action, Risk

        result = rebuild(
            book(tmp_path / "in.epub", "body { background-image: url(nie-ma.png); }"),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        entry = next(
            c for c in result.report.changes if c.rule == "css.dead-url-neutralised"
        )
        assert entry.action is Action.REPLACED
        assert entry.risk is Risk.APPEARANCE
        assert not entry.reversible
