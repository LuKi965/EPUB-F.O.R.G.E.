"""F-011's remainder, and the invariant nothing was checking.

The audit graded Metadata **FAIL** and OPF **FAIL**, on the argument that the
package document is reconstructed from a model that does not hold everything the
source said. Most of that was closed along the way — multiple titles, creators
with roles and file-as and alternate scripts, several identifiers, several
languages, subjects, open vocabularies. Probed at the end, a rich OPF came back
with fourteen of sixteen things intact and two gone:

* `<meta refines="#t2" property="display-seq">2</meta>` — a refinement this
  model has no field for. The reader consumed the refinements it knew and
  `continue`d past the rest.
* `<link rel="record" href="…"/>` inside `<metadata>` — the publication
  pointing at a catalogue record about itself. Never read at all.

Both are now carried, in the idiom the navigation sections settled on: **carried
rather than understood**. A refinement is re-pointed at whatever id the rebuilt
package gives that node, because `refines="#t2"` naming an id the output does not
have is not a preserved statement — it is an invalid one.

And separately, the audit's K.2 invariant 11: *the result can be read again by
the same strict reader, without recovery and without an error.* The writer's
verifier asks whether the ZIP survived the trip to disk; the commit gate asks
whether the model made sense; nothing asked whether what was written reads back
as a book.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
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

RICH = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id"
         prefix="wydawca: https://example.org/wydawca#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:isbn:9788324141234</dc:identifier>
    <dc:identifier id="doi">10.1000/xyz</dc:identifier>
    <dc:title id="t1">Tytuł główny</dc:title>
    <dc:title id="t2">Podtytuł dzieła</dc:title>
    <meta refines="#t1" property="title-type">main</meta>
    <meta refines="#t2" property="title-type">subtitle</meta>
    <meta refines="#t2" property="display-seq">2</meta>
    <dc:creator id="a1">Jan Kowalski</dc:creator>
    <meta refines="#a1" property="role">aut</meta>
    <meta refines="#a1" property="wydawca:staz">od 1994</meta>
    <dc:contributor id="c1">Anna Nowak</dc:contributor>
    <meta refines="#c1" property="role">trl</meta>
    <dc:language>pl</dc:language>
    <dc:language>en</dc:language>
    <dc:subject>Powieść</dc:subject>
    <dc:rights>Wszelkie prawa zastrzeżone</dc:rights>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
    <link rel="record" href="https://example.org/onix" media-type="application/xml"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c"/></spine>
</package>
"""


def rich_book(path, package: str = RICH) -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": package.encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": PAGE.encode(),
        },
    )


def package_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".opf"))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


@pytest.fixture
def rebuilt(tmp_path):
    result = rebuild(
        rich_book(tmp_path / "rich.epub"),
        str(tmp_path / "out.epub"),
        Policy.preset("preserve"),
    )
    assert result.status.wrote_a_file, result.report.to_text()
    return result


class TestF011WhatTheModelDoesNotUnderstandIsStillCarried:
    def test_a_refinement_with_no_field_of_its_own_survives(self, rebuilt):
        assert "display-seq" in package_of(rebuilt)

    def test_and_so_does_one_nobody_has_ever_heard_of(self, rebuilt):
        """The vocabulary is open. "Not recognised" says something about this
        program and nothing about the book."""
        assert "wydawca:staz" in package_of(rebuilt)

    def test_and_it_brings_its_vocabulary_declaration_with_it(self, rebuilt):
        """A carried `x:whatever` with no declaration of `x` is not a preserved
        statement, it is an invalid document — and that is exactly what the
        first version of this carry produced. EPUBCheck said so on the output of
        the change that introduced it."""
        package = package_of(rebuilt)
        assert "wydawca: https://example.org/wydawca#" in package

    def test_it_refines_the_node_it_used_to_refine(self, rebuilt):
        """`refines="#t2"` naming an id the output does not have is not a
        preserved statement — it is an invalid one. The writer renames those
        nodes, so a carried refinement is re-pointed at the new id."""
        package = package_of(rebuilt)
        line = next(l for l in package.splitlines() if "display-seq" in l)
        anchor = line.split('refines="#', 1)[1].split('"', 1)[0]
        assert f'id="{anchor}"' in package, f"refines #{anchor}, which nothing declares"

    def test_a_metadata_link_survives_whole(self, rebuilt):
        package = package_of(rebuilt)
        assert "https://example.org/onix" in package
        assert 'rel="record"' in package
        assert 'media-type="application/xml"' in package

    def test_the_report_says_it_carried_them(self, rebuilt):
        assert "package.refinements-carried" in rules_of(rebuilt)

    def test_a_refinement_whose_target_is_gone_is_dropped_and_counted(self, tmp_path):
        """Not written pointing at nothing. A `refines` naming a node that did
        not survive would make the output invalid, and it says nothing anyway."""
        package = RICH.replace('refines="#t2" property="display-seq"',
                               'refines="#nie-ma-tego" property="display-seq"')
        result = rebuild(
            rich_book(tmp_path / "orphan.epub", package),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "display-seq" not in package_of(result)
        assert "package.refinements-unanchored" in rules_of(result)

    def test_the_rest_of_the_metadata_is_still_there(self, rebuilt):
        """The guard: a carry that broke the fields the model *does* have would
        be a poor trade."""
        package = package_of(rebuilt)
        for expected in (
            "Tytuł główny",
            "Podtytuł dzieła",
            "Jan Kowalski",
            "Anna Nowak",
            "10.1000/xyz",
            "Powieść",
            "Wszelkie prawa zastrzeżone",
            "<dc:language>en",
        ):
            assert expected in package, expected

    def test_and_the_result_validates(self, rebuilt):
        from epubforge.validate import find_epubcheck, validate

        if find_epubcheck() is None:
            pytest.skip("EPUBCheck is not installed here")
        validate(rebuilt.output_path, rebuilt.report)
        errors = [
            f.detail
            for f in rebuilt.report.findings
            if f.stage == "epubcheck" and f.level.value == "error"
        ]
        assert not errors, errors


class TestTheOutputIsReadBackBeforeItIsCalledDone:
    """K.2 invariant 11, which nothing was checking."""

    def test_an_ordinary_rebuild_reads_back_cleanly(self, rebuilt):
        assert "package.not-readable-again" not in rules_of(rebuilt)
        assert rebuilt.status is Status.SUCCEEDED

    def test_a_file_that_cannot_be_read_back_says_so(self, tmp_path, monkeypatch):
        """Forced, because the whole point of the check is that this program
        does not know how to produce one on purpose. What is being tested is
        that the answer reaches the report and the status rather than being
        computed and dropped."""
        from epubforge import pipeline

        monkeypatch.setattr(pipeline, "_reread", lambda destination: "reader.spine-missing")
        result = rebuild(
            rich_book(tmp_path / "in.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "package.not-readable-again" in rules_of(result)
        assert result.status is Status.SUCCEEDED_WITH_PROBLEMS
        assert result.output_path, "the file is still handed over — this is a warning"

    def test_the_check_reads_the_file_that_was_written(self, tmp_path):
        from epubforge import pipeline

        assert pipeline._reread(str(tmp_path / "nie-ma.epub"))

    def test_and_says_nothing_about_a_good_one(self, tmp_path):
        from epubforge import pipeline

        result = rebuild(
            rich_book(tmp_path / "good.epub"),
            str(tmp_path / "good-out.epub"),
            Policy.preset("preserve"),
        )
        assert pipeline._reread(result.output_path) == ""
