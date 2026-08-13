"""F-017 and F-028 — proving the book survived, not just that the file validates.

The audit's complaint, which is one complaint filed twice: *the suite proves the
output conforms and does not prove it still looks like itself.* Every rule in
this program is a judgement about appearance — remove this declaration, unwrap
that span, replace this navigation document — and the evidence for all of them
was a validator's silence plus my reading of the diff. A validator has no
opinion about a book that came out with three hundred fewer links in it.

The owner's decision on 2026-08-13 was to build the harness **in stages,
starting without screenshots**, because comparing text, structure, media and
reading order catches most of what can go wrong and needs no browser. This is
stage one, and it earned its place on the day it was written: pointed at the six
books of the public corpus it found a real, silent, K1-class loss in three of
them — Project Gutenberg writes its page list as `epub:type="landmarks"` with
every entry typed `normal`, and the landmark deduplication kept the first and
deleted 293. No test here had anything to say about it. No validator did either.

What this file asserts is that the harness *can fail*. A comparison that always
passes is decoration, so every check below is shown catching the thing it exists
to catch, on a book deliberately damaged in that one way.
"""

from __future__ import annotations

import glob
import pathlib
import zipfile

import pytest

from epubforge import fidelity
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import MODERN_NAV, MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>{title}</title></head>
  <body><h1>{title}</h1><p>{body}</p><p><img src="picture.png" alt="rys"/></p></body>
</html>
"""

GUTENBERG = pathlib.Path(__file__).parent / "corpus_gutenberg"


def source(path, *, body: str = "Pierwszy akapit książki.", title: str = "Rozdział") -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="").encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": CHAPTER.format(title=title, body=body).encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )


def damaged(original: str, path: str, **changes: bytes) -> str:
    """A copy of an EPUB with named entries replaced — a rebuild gone wrong."""
    with zipfile.ZipFile(original) as archive:
        entries = {
            name: archive.read(name) for name in archive.namelist() if name != "mimetype"
        }
    entries.update(changes)
    return write_zip(path, entries)


class TestTheHarnessCanFail:
    """Each check, shown catching its own defect. Without these the file is a
    row of green ticks that would stay green if the comparison did nothing."""

    def test_a_missing_word_is_a_missing_word(self, tmp_path):
        original = source(tmp_path / "a.epub", body="Pierwszy akapit książki.")
        broken = damaged(
            original,
            str(tmp_path / "b.epub"),
            **{"OEBPS/chapter.xhtml": CHAPTER.format(
                title="Rozdział", body="Pierwszy akapit."
            ).encode()},
        )
        check = fidelity.text_survives(original, broken)
        assert not check.ok
        assert "książki" in check.detail

    def test_a_lost_heading_is_a_lost_heading(self, tmp_path):
        original = source(tmp_path / "c.epub")
        flattened = CHAPTER.format(title="Rozdział", body="x").replace("<h1>", "<p>").replace(
            "</h1>", "</p>"
        )
        broken = damaged(
            original, str(tmp_path / "d.epub"), **{"OEBPS/chapter.xhtml": flattened.encode()}
        )
        check = fidelity.shape_survives(original, broken)
        assert not check.ok
        assert "h1" in check.detail

    def test_a_picture_that_changed_is_reported(self, tmp_path):
        original = source(tmp_path / "e.epub")
        broken = damaged(
            original,
            str(tmp_path / "f.epub"),
            **{"OEBPS/picture.png": png_bytes(color=(1, 2, 3))},
        )
        check = fidelity.media_survives(original, broken)
        assert not check.ok
        assert "picture.png" in check.detail

    def test_a_reordered_book_is_reported(self, tmp_path):
        package = MODERN_OPF.format(title="Test", extra_metadata="").replace(
            "</manifest>",
            '<item id="ch2" href="second.xhtml" media-type="application/xhtml+xml"/></manifest>',
        )
        entries = {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": CHAPTER.format(title="Jeden", body="Pierwszy").encode(),
            "OEBPS/second.xhtml": CHAPTER.format(title="Dwa", body="Drugi").encode(),
            "OEBPS/picture.png": png_bytes(),
        }
        one = write_zip(
            str(tmp_path / "g.epub"),
            {**entries, "OEBPS/package.opf": package.replace(
                "</spine>", '<itemref idref="ch2"/></spine>'
            ).encode()},
        )
        other = write_zip(
            str(tmp_path / "h.epub"),
            {**entries, "OEBPS/package.opf": package.replace(
                '<itemref idref="ch1"/>', '<itemref idref="ch2"/><itemref idref="ch1"/>'
            ).encode()},
        )
        assert not fidelity.reading_order_survives(one, other).ok

    def test_a_book_compared_with_itself_passes_everything(self, tmp_path):
        """The other half: a harness that fails on identical files is noise."""
        original = source(tmp_path / "i.epub")
        assert fidelity.compare(original, original).ok


class TestARealRebuildKeepsARealBook:
    @pytest.mark.parametrize("mode", ["preserve", "strict", "minimal"])
    def test_nothing_of_the_book_is_lost(self, tmp_path, mode):
        original = source(tmp_path / "j.epub")
        destination = str(tmp_path / f"{mode}.epub")
        rebuild(original, destination, Policy.preset(mode))
        measured = fidelity.compare(original, destination)
        assert measured.ok, measured.to_text()


@pytest.mark.skipif(not list(GUTENBERG.glob("*.epub")), reason="no public corpus here")
class TestTheBooksThatFoundTheDefect:
    """The public corpus, through the harness. Six real books, six comparisons.

    This is the test that would have caught the landmark deduplication deleting
    293 page links per Gutenberg title, and it is here so that the next thing of
    that shape is caught by a test run rather than by somebody noticing.
    """

    @pytest.mark.parametrize(
        "book", sorted(glob.glob(str(GUTENBERG / "*.epub"))), ids=lambda p: pathlib.Path(p).stem[:24]
    )
    def test_the_rebuild_keeps_it(self, tmp_path, book):
        destination = str(tmp_path / "out.epub")
        result = rebuild(book, destination, Policy.preset("preserve"))
        assert result.status.wrote_a_file
        measured = fidelity.compare(book, destination)
        assert measured.ok, measured.to_text()


class TestF017TheLandmarkSweepThatDeletedThePageList:
    """Named for the finding, because this is the defect the harness found.

    Gutenberg writes `<nav epub:type="landmarks" aria-label="Page List">` with
    every entry typed `normal`. Deduplicating landmarks by type alone read that
    as "one book, one `normal` landmark" and kept a single link out of 294.
    """

    @staticmethod
    def with_a_page_list(path) -> str:
        entries = "".join(
            f'<li><a href="chapter.xhtml#p{n}" epub:type="normal">[{n}]</a></li>'
            for n in range(1, 40)
        )
        nav = (
            '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
            "<head><meta charset='utf-8'/><title>Spis</title></head><body>"
            '<nav epub:type="toc"><ol><li><a href="chapter.xhtml">R</a></li></ol></nav>'
            f'<nav epub:type="landmarks" aria-label="Numery stron"><ol>{entries}</ol></nav>'
            "</body></html>"
        )
        body = "".join(f'<span id="p{n}">{n}</span>' for n in range(1, 40))
        return write_zip(
            str(path),
            {
                "META-INF/container.xml": CONTAINER.encode(),
                "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="").encode(),
                "OEBPS/nav.xhtml": nav.encode(),
                "OEBPS/chapter.xhtml": CHAPTER.format(title="Rozdział", body=body).encode(),
                "OEBPS/picture.png": png_bytes(),
            },
        )

    def test_every_entry_reaches_the_rebuilt_book(self, tmp_path):
        original = self.with_a_page_list(tmp_path / "pages.epub")
        destination = str(tmp_path / "out.epub")
        rebuild(original, destination, Policy.preset("preserve"))
        with zipfile.ZipFile(destination) as archive:
            navigation = next(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.endswith("nav.xhtml")
            )
        assert navigation.count("epub:type=\"normal\"") >= 39, (
            "39 links into the book; the sweep used to keep one"
        )

    def test_and_the_harness_agrees(self, tmp_path):
        original = self.with_a_page_list(tmp_path / "pages2.epub")
        destination = str(tmp_path / "out2.epub")
        rebuild(original, destination, Policy.preset("preserve"))
        measured = fidelity.compare(original, destination)
        assert measured.ok, measured.to_text()


class TestItIsReachable:
    """The owner's rule: everything, the debugging things included, in the window."""

    def test_the_window_offers_it(self):
        from epubforge.gui.strings import EN, PL

        source_text = (
            pathlib.Path(__file__).resolve().parent.parent / "epubforge" / "gui" / "tabs.py"
        ).read_text(encoding="utf-8")
        assert "self.fidelity_choice" in source_text
        assert "_fidelity" in source_text
        for catalogue in (EN, PL):
            assert catalogue["diagnostics.fidelity"]
            assert len(catalogue["diagnostics.fidelity.tip"]) > 200

    def test_the_command_line_offers_it_too(self):
        from epubforge.cli import build_parser

        parsed = build_parser().parse_args(["fidelity", "x.epub"])
        assert parsed.func.__name__ == "command_fidelity"
        assert parsed.mode == "preserve"


class TestF017TheCascadeCheck:
    """F-017 on its own, because it is not F-028 with the same file name.

    The finding: *the CSS is modified on an approximate model of the cascade,
    and nothing checks that the modification preserved the rendering.* Sharing a
    test file with F-028 made the status tool report it done the moment the file
    existed — which is the same "counted its own list" failure that put this
    harness on the schedule in the first place.

    The model is still approximate. What makes the comparison meaningful is that
    the *same* approximation is applied to both sides: a difference is then a
    real change in which declarations reach an element, not an artefact.
    """

    @staticmethod
    def styled(path, *, rule: str = "p { text-align: justify }") -> str:
        chapter = CHAPTER.format(title="Rozdział", body="Akapit tekstu.").replace(
            "</head>", '<link rel="stylesheet" type="text/css" href="styl.css"/></head>'
        )
        return write_zip(
            str(path),
            {
                "META-INF/container.xml": CONTAINER.encode(),
                "OEBPS/package.opf": MODERN_OPF.format(title="T", extra_metadata="").encode(),
                "OEBPS/nav.xhtml": MODERN_NAV.encode(),
                "OEBPS/chapter.xhtml": chapter.encode(),
                "OEBPS/styl.css": rule.encode(),
                "OEBPS/picture.png": png_bytes(),
            },
        )

    def test_a_declaration_that_changed_is_caught(self, tmp_path):
        original = self.styled(tmp_path / "k.epub")
        restyled = damaged(
            original,
            str(tmp_path / "l.epub"),
            **{"OEBPS/styl.css": b"p { text-align: center }"},
        )
        check = fidelity.style_survives(original, restyled)
        assert not check.ok
        assert "text-align" in check.detail

    def test_a_declaration_that_disappeared_is_caught(self, tmp_path):
        original = self.styled(tmp_path / "m.epub")
        stripped = damaged(original, str(tmp_path / "n.epub"), **{"OEBPS/styl.css": b""})
        check = fidelity.style_survives(original, stripped)
        assert not check.ok
        assert "text-align" in check.detail

    def test_an_inline_style_counts_too(self, tmp_path):
        """Half of what this program rewrites is inline, so a cascade check that
        ignored `style=` would be blind to the busiest half of the work."""
        chapter = CHAPTER.format(title="R", body="Tekst.").replace(
            "<p>Tekst.</p>", '<p style="text-indent: 2em">Tekst.</p>'
        )
        original = write_zip(
            str(tmp_path / "o.epub"),
            {
                "META-INF/container.xml": CONTAINER.encode(),
                "OEBPS/package.opf": MODERN_OPF.format(title="T", extra_metadata="").encode(),
                "OEBPS/nav.xhtml": MODERN_NAV.encode(),
                "OEBPS/chapter.xhtml": chapter.encode(),
                "OEBPS/picture.png": png_bytes(),
            },
        )
        without = damaged(
            original,
            str(tmp_path / "p.epub"),
            **{"OEBPS/chapter.xhtml": CHAPTER.format(title="R", body="Tekst.").encode()},
        )
        assert not fidelity.style_survives(original, without).ok

    def test_a_real_rebuild_does_not_change_what_applies(self, tmp_path):
        original = self.styled(tmp_path / "q.epub")
        destination = str(tmp_path / "r.epub")
        rebuild(original, destination, Policy.preset("preserve"))
        check = fidelity.style_survives(original, destination)
        assert check.ok, check.detail

    def test_and_neither_does_strict(self, tmp_path):
        """The mode that is allowed to change appearance is the one worth
        measuring: `strict` removes declarations on purpose, and the promise is
        that what it removes was doing nothing."""
        original = self.styled(tmp_path / "s.epub")
        destination = str(tmp_path / "t.epub")
        rebuild(original, destination, Policy.preset("strict"))
        check = fidelity.style_survives(original, destination)
        assert check.ok, check.detail

    def test_a_rule_that_depends_on_an_ancestor_is_left_out_rather_than_guessed(self, tmp_path):
        """The limit of the model, asserted so nobody re-derives it from a bug.

        `epubforge.cascade` reads the rightmost compound of a selector, so
        `.centred table` looks to it like `table`. On the public corpus that
        turned one correctly-removed dead rule into four false alarms. A harness
        that cries wolf teaches people to skip its output, so a rule this model
        cannot decide is not answered with a guess — it is left out, and what it
        does to the page still shows in the text and structure checks.
        """
        original = self.styled(tmp_path / "u.epub", rule=".brak p { text-align: center }")
        stripped = damaged(original, str(tmp_path / "v.epub"), **{"OEBPS/styl.css": b""})
        assert fidelity.style_survives(original, stripped).ok

    def test_but_a_plain_selector_is_still_decided(self, tmp_path):
        """The guard on the guard: if the filter dropped everything, the check
        above would pass for the wrong reason and so would every other."""
        original = self.styled(tmp_path / "w.epub", rule="p { text-align: center }")
        stripped = damaged(original, str(tmp_path / "x.epub"), **{"OEBPS/styl.css": b""})
        assert not fidelity.style_survives(original, stripped).ok
