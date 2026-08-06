"""The corpus regression against real books, committed with the source.

`test_corpus.py` points at a private shelf and skips wherever that shelf is
absent, which is everywhere except one machine. `test_public_corpus.py` points
at nine books the suite builds, which catches changes in behaviour but cannot
catch anything about books nobody would write on purpose.

These six are real. They come from Project Gutenberg, so they are in the public
domain and may be committed; every one is a book somebody actually reads, made
by a generator nobody here controls, and three of them are in Polish with the
diacritics and the file names that come with that.

They earned their place immediately. Recording them showed `text_invariant`
false on all six — not because text was lost, but because the field compared
character counts for equality, and generating a cover page adds two. K1 says no
character is *lost*; it does not say none may be added. See
`epubforge/corpus.py::_text_survived`.

EPUBCheck is switched off, as in the public corpus, so a signature does not
depend on whether a JVM is installed.

Refreshing after an intentional change:

    python -m tests.test_corpus_gutenberg --record
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from epubforge.corpus import books_in, compare, signature_files, summarise

CORPUS = pathlib.Path(__file__).parent / "corpus_gutenberg"
EXPECTED = CORPUS / "expected"


@pytest.fixture(autouse=True)
def without_epubcheck(monkeypatch):
    monkeypatch.setattr("epubforge.corpus.find_epubcheck", lambda: None)


def test_the_books_are_actually_here():
    """Committed on purpose. If they vanish, this file silently proves nothing —
    which is the failure mode the private corpus already has by necessity."""
    assert len(books_in(CORPUS)) == 6


def test_every_book_still_rebuilds_the_way_it_did():
    results = compare(CORPUS, EXPECTED)
    moved = [r for r in results if not r.ok]
    if moved:
        report = "\n".join(
            f"  {r.book} ({r.status}):\n" + "\n".join(f"    {d}" for d in r.differences)
            for r in moved
        )
        pytest.fail(
            f"{summarise(results)}\n{report}\n"
            "  If the change was intended: python -m tests.test_corpus_gutenberg --record"
        )


def test_no_book_loses_text():
    """K1 on real books, which is the point of having them.

    Asserted separately from the signature comparison so that losing a chapter
    reads as losing a chapter rather than as "a hash moved".
    """
    import json

    for path in signature_files(EXPECTED):
        recorded = json.loads(path.read_text(encoding="utf-8"))
        for mode, measurement in recorded.items():
            if not isinstance(measurement, dict) or "text_invariant" not in measurement:
                continue
            assert measurement["text_invariant"], f"{path.stem} lost text in {mode}"


class TestTheInvariantCheckActuallyChecks:
    """A test that always passes is worse than no test, and the previous
    version of this field passed for a reason that had nothing to do with
    text."""

    def _book(self, tmp_path, name, body):
        """A one-document book whose spine text is exactly `body`."""
        from .factory import CONTAINER, MODERN_NAV, write_zip

        opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Tekst</dc:title><dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="ch.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        document = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            '<meta charset="utf-8"/><title>T</title></head><body>' + body + "</body></html>"
        )
        return write_zip(
            str(tmp_path / name),
            {
                "META-INF/container.xml": CONTAINER.replace(
                    "OEBPS/content.opf", "OEBPS/package.opf"
                ),
                "OEBPS/package.opf": opf,
                "OEBPS/nav.xhtml": MODERN_NAV,
                "OEBPS/ch.xhtml": document,
            },
        )

    def test_identical_text_survives(self, tmp_path):
        from epubforge.corpus import _text_survived

        one = self._book(tmp_path, "a.epub", "<p>Zażółć gęślą jaźń.</p>")
        two = self._book(tmp_path, "b.epub", "<p>Zażółć gęślą jaźń.</p>")
        assert _text_survived(pathlib.Path(one), pathlib.Path(two))

    def test_added_text_still_counts_as_survived(self, tmp_path):
        """The case that made the old check useless: a generated cover page."""
        from epubforge.corpus import _text_survived

        one = self._book(tmp_path, "a.epub", "<p>Zdanie.</p>")
        two = self._book(tmp_path, "b.epub", "<p>Okładka</p><p>Zdanie.</p><p>Koniec</p>")
        assert _text_survived(pathlib.Path(one), pathlib.Path(two))

    def test_a_missing_word_is_caught(self, tmp_path):
        from epubforge.corpus import _text_survived

        one = self._book(tmp_path, "a.epub", "<p>Pierwsze zdanie tekstu.</p>")
        two = self._book(tmp_path, "b.epub", "<p>Pierwsze tekstu.</p>")
        assert not _text_survived(pathlib.Path(one), pathlib.Path(two))

    def test_reordered_text_is_caught(self, tmp_path):
        """Same characters, different order. A count cannot tell these apart."""
        from epubforge.corpus import _text_survived

        one = self._book(tmp_path, "a.epub", "<p>abc def</p>")
        two = self._book(tmp_path, "b.epub", "<p>def abc</p>")
        assert not _text_survived(pathlib.Path(one), pathlib.Path(two))


def main() -> int:
    import epubforge.corpus as corpus_module

    corpus_module.find_epubcheck = lambda: None  # see the module docstring
    results = compare(CORPUS, EXPECTED, record="--record" in sys.argv)
    for result in results:
        if result.status in ("changed", "new", "failed"):
            print(f"  {result.status:8} {result.book}")
            for line in result.differences:
                print(f"    {line}")
    print("\n" + summarise(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
