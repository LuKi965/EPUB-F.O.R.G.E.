"""EF-071 — the publisher's `aria-label` on a regenerated navigation section.

Found by the audit's third finding put into practice: counting semantic
attributes before and after a rebuild. Over sixty books of a strict run the
one count that ever fell was `aria-label`, nine times in six books, all of
them on the source's own `<nav epub:type="toc" … aria-label="Table of
Contents">`. The navigation document is regenerated from the model, the model
had no place for that label, and so it left with the old document — F-018's
shape one floor down. The label is text the publisher wrote for a screen
reader; it is carried now, word for word, and a book without one gets none.
"""

from __future__ import annotations

from tests.test_nav_semantics import built, navigation, rules_of, source

LABELLED_NAV = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Spis</title></head>
  <body>
    <nav epub:type="toc" id="spis" role="doc-toc" aria-label="Spis treści &amp; reszta">
      <h1>Spis treści</h1>
      <ol><li><a href="chapter.xhtml#start">Rozdział</a></li></ol>
    </nav>
    <nav epub:type="landmarks" aria-label="Punkty orientacyjne" hidden="hidden">
      <ol><li><a epub:type="bodymatter" href="chapter.xhtml#start">Początek</a></li></ol>
    </nav>
    <nav epub:type="page-list" aria-label="Lista stron">
      <ol><li><a href="chapter.xhtml#start">7</a></li></ol>
    </nav>
  </body>
</html>
"""

PLAIN_NAV = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Spis</title></head>
  <body>
    <nav epub:type="toc" id="spis">
      <h1>Spis treści</h1>
      <ol><li><a href="chapter.xhtml#start">Rozdział</a></li></ol>
    </nav>
  </body>
</html>
"""


class TestThePublishersLabelIsCarried:
    def test_on_the_contents_word_for_word(self, tmp_path):
        result = built(source(tmp_path / "labelled.epub", LABELLED_NAV), tmp_path)
        document = navigation(result)
        assert 'epub:type="toc" id="toc" role="doc-toc" aria-label="Spis treści &amp; reszta"' in document

    def test_on_the_landmarks_and_the_page_list_too(self, tmp_path):
        result = built(source(tmp_path / "labelled.epub", LABELLED_NAV), tmp_path)
        document = navigation(result)
        assert 'aria-label="Punkty orientacyjne"' in document
        assert 'aria-label="Lista stron"' in document

    def test_and_the_report_says_so(self, tmp_path):
        result = built(source(tmp_path / "labelled.epub", LABELLED_NAV), tmp_path)
        assert "nav.labels-carried" in rules_of(result)
        (finding,) = [f for f in result.report.findings if f.rule == "nav.labels-carried"]
        assert finding.values["count"] == 3

    def test_in_strict_mode_as_well(self, tmp_path):
        result = built(source(tmp_path / "labelled.epub", LABELLED_NAV), tmp_path, mode="strict")
        assert 'aria-label="Spis treści &amp; reszta"' in navigation(result)


class TestABookWithoutOneGetsNone:
    def test_nothing_is_invented(self, tmp_path):
        """K4: a label this program wrote would be its claim, not the book's.
        The heading is the section's name; that is what the reader gets."""
        result = built(source(tmp_path / "plain.epub", PLAIN_NAV), tmp_path)
        document = navigation(result)
        assert "aria-label" not in document
        assert "nav.labels-carried" not in rules_of(result)
