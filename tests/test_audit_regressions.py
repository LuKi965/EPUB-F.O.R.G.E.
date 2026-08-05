"""Regressions for defects that survived a full test suite by changing nothing visible.

Both were found by an external audit rather than by the suite, and both share a
shape worth naming: they corrupted *data* while leaving the *shape* of the
output alone — same files, same counts, same validator verdict. The invariant
tests in `test_invariants.py` are the general defence; these pin the specific
behaviours so a future refactor cannot quietly reintroduce them.
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .factory import make_modern_epub

OPF = "EPUB/package.opf"


def package_document(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(OPF).decode()


# ------------------------------------------------------- series numbering
class TestSeriesNumberSurvivesARoundTrip:
    """`group-position` is only ever a refinement, so skipping all refinements
    lost it — but only on the second pass, when the source of the number had
    already moved from `calibre:series_index` to the EPUB 3 spelling."""

    def index_of(self, opf: str) -> str | None:
        match = re.search(r'property="group-position">([^<]*)<', opf)
        return match.group(1) if match else None

    def test_first_pass_writes_the_series_number(self, rebuilt):
        assert self.index_of(package_document(rebuilt.output_path)) == "2"

    def test_second_pass_keeps_it(self, rebuilt, tmp_path):
        again = rebuild(
            rebuilt.output_path, str(tmp_path / "again.epub"), Policy.preset("preserve")
        )
        assert self.index_of(package_document(again.output_path)) == "2"

    def test_series_name_also_survives(self, rebuilt, tmp_path):
        again = rebuild(
            rebuilt.output_path, str(tmp_path / "again.epub"), Policy.preset("preserve")
        )
        assert "Kroniki" in package_document(again.output_path)

    @pytest.mark.parametrize("collection_type", ["series", "set"])
    def test_a_collection_is_carried_whatever_its_type(self, tmp_path, collection_type):
        """Both survive, and the type survives with them.

        This used to assert that a `set` came out *absent*, which read as a
        decision — "a boxed edition is not a series" — but was the model's
        single series field showing through. Not being a series is a reason to
        keep it as a set, not a reason to drop it (EF-004).
        """
        source = make_modern_epub(
            str(tmp_path / "collection.epub"),
            extra_metadata=(
                '    <meta property="belongs-to-collection" id="c">Dzieła zebrane</meta>\n'
                f'    <meta refines="#c" property="collection-type">{collection_type}</meta>'
            ),
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        package = package_document(result.output_path)
        assert "Dzieła zebrane" in package
        assert f">{collection_type}</meta>" in package

    def test_a_set_does_not_become_the_series(self, tmp_path):
        """The half of the old test that was a real decision, kept on its own."""
        from epubforge.reader import read_epub
        from epubforge.report import Report

        source = make_modern_epub(
            str(tmp_path / "set.epub"),
            extra_metadata=(
                '    <meta property="belongs-to-collection" id="c">Dzieła zebrane</meta>\n'
                '    <meta refines="#c" property="collection-type">set</meta>'
            ),
        )
        book = read_epub(source, Report())
        assert book.metadata.series is None
        assert [m.collection_type for m in book.metadata.collection_memberships] == ["set"]


# ------------------------------------------------------------ empty alt text
class TestEmptyAltIsNeverADescription:
    """An empty alt asserts "decorative", and nothing here can verify that.

    The previous code trusted it whenever the current run had not supplied it
    itself — a fact it kept in memory. Send the output back in and that memory
    was gone, so a book with no descriptions at all came out claiming
    `alternativeText`.
    """

    def features(self, path: str) -> set[str]:
        return set(
            re.findall(r'property="schema:accessibilityFeature">([^<]*)<', package_document(path))
        )

    def test_first_pass_withholds_the_claim(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "alternativeText" not in self.features(result.output_path)

    def test_second_pass_withholds_it_too(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        first = rebuild(source, str(tmp_path / "one.epub"), Policy.preset("preserve"))
        second = rebuild(first.output_path, str(tmp_path / "two.epub"), Policy.preset("preserve"))
        assert "alternativeText" not in self.features(second.output_path)

    def test_the_summary_does_not_claim_it_either(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        first = rebuild(source, str(tmp_path / "one.epub"), Policy.preset("preserve"))
        second = rebuild(first.output_path, str(tmp_path / "two.epub"), Policy.preset("preserve"))
        assert "wszystkie ilustracje" not in package_document(second.output_path)

    @pytest.mark.parametrize(
        "image",
        [
            '<img src="picture.png" alt="" role="presentation"/>',
            '<img src="picture.png" alt="" aria-hidden="true"/>',
        ],
    )
    def test_an_explicit_decorative_marking_is_believed(self, tmp_path, image):
        """Because that one *is* a statement somebody deliberately made."""
        source = make_modern_epub(str(tmp_path / "in.epub"), image=image)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "alternativeText" in self.features(result.output_path)

    def test_a_real_description_is_believed(self, tmp_path):
        source = make_modern_epub(
            str(tmp_path / "in.epub"),
            image='<img src="picture.png" alt="Mapa wybrzeża z zaznaczonym portem"/>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "alternativeText" in self.features(result.output_path)

    def test_the_gap_is_reported(self, tmp_path):
        from epubforge.report import Level

        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        warnings = [f.message for f in result.report.findings if f.level is Level.WARN]
        assert any("alt text" in message for message in warnings), warnings


# ------------------------------------------------------- collection numbering
class TestSeriesNumberComesFromTheRightCollection:
    """A book can belong to several collections; the number is not free-floating.

    The 0.8.0 fix separated a boxed `set` from a `series` by name, but the
    number was still taken from whichever `group-position` the document listed
    first. The seventh Chronicle, published inside a boxed set as part one, came
    out as "Chronicles, volume 1".
    """

    BOX_THEN_SERIES = (
        '    <meta property="belongs-to-collection" id="box">Dzieła zebrane</meta>\n'
        '    <meta refines="#box" property="collection-type">set</meta>\n'
        '    <meta refines="#box" property="group-position">1</meta>\n'
        '    <meta property="belongs-to-collection" id="ser">Kroniki</meta>\n'
        '    <meta refines="#ser" property="collection-type">series</meta>\n'
        '    <meta refines="#ser" property="group-position">7</meta>'
    )

    def read(self, tmp_path, extra_metadata):
        from epubforge.reader import read_epub
        from epubforge.report import Report

        source = make_modern_epub(str(tmp_path / "c.epub"), extra_metadata=extra_metadata)
        return read_epub(source, Report(source=source)).metadata

    def test_name_and_number_come_from_the_same_collection(self, tmp_path):
        metadata = self.read(tmp_path, self.BOX_THEN_SERIES)
        assert (metadata.series, metadata.series_index) == ("Kroniki", "7")

    def test_an_untyped_collection_counts_as_a_series(self, tmp_path):
        """EPUB 3 says that is the default, and most books never state it."""
        metadata = self.read(
            tmp_path,
            '    <meta property="belongs-to-collection" id="s">Kroniki</meta>\n'
            '    <meta refines="#s" property="group-position">3</meta>',
        )
        assert (metadata.series, metadata.series_index) == ("Kroniki", "3")

    def test_a_set_alone_yields_no_series_at_all(self, tmp_path):
        metadata = self.read(
            tmp_path,
            '    <meta property="belongs-to-collection" id="b">Pudełko</meta>\n'
            '    <meta refines="#b" property="collection-type">set</meta>\n'
            '    <meta refines="#b" property="group-position">2</meta>',
        )
        assert metadata.series is None and metadata.series_index is None

    def test_it_survives_a_round_trip(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "c.epub"), extra_metadata=self.BOX_THEN_SERIES)
        first = rebuild(source, str(tmp_path / "one.epub"), Policy.preset("preserve"))
        second = rebuild(first.output_path, str(tmp_path / "two.epub"), Policy.preset("preserve"))
        opf = package_document(second.output_path)
        assert "Kroniki" in opf
        assert re.search(r'property="group-position">7<', opf), opf


# ------------------------------------------------- entities from a DTD subset
class TestEntitiesDeclaredByTheDocumentItself:
    """A textbook K11: the file declared something, we threw the declaration
    away, and left the references pointing at nothing.

    EPUB 3 replaces the DOCTYPE with one that declares no entities, so the
    subset has to go. But the references live in the text, and once the
    declaration is gone the ampersand gets escaped: the reader sees `&mypauza;`
    on the page where a dash belongs. Silently, in `preserve` mode, with a
    report entry about something else entirely.
    """

    DOCUMENT = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html [
  <!ENTITY mypauza "&#8212;">
  <!ENTITY wydawca "Wydawnictwo Przyklad">
]>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>R</title></head>
<body><p>Tekst &mypauza; z pauza.</p><p>&wydawca;, Krakow.</p></body>
</html>"""

    EXTERNAL = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html [
  <!ENTITY zewnetrzna SYSTEM "http://example.invalid/secret.txt">
]>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>R</title></head>
<body><p>A &zewnetrzna; B</p></body>
</html>"""

    def build(self, tmp_path, document: str) -> str:
        import zipfile

        from .factory import CONTAINER, MODERN_NAV, MODERN_OPF, png_bytes

        path = str(tmp_path / "dtd.epub")
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
            )
            archive.writestr(
                "OEBPS/package.opf", MODERN_OPF.format(title="T", extra_metadata="")
            )
            archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
            archive.writestr("OEBPS/chapter.xhtml", document)
            archive.writestr("OEBPS/picture.png", png_bytes())
        return path

    def rebuilt_text(self, tmp_path, document: str, name: str = "out.epub"):
        source = self.build(tmp_path, document)
        result = rebuild(source, str(tmp_path / name), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            chapter = next(
                n for n in archive.namelist() if n.endswith(".xhtml") and "nav" not in n
            )
            return archive.read(chapter).decode(), result

    def test_the_entity_becomes_the_character_it_stood_for(self, tmp_path):
        text, _ = self.rebuilt_text(tmp_path, self.DOCUMENT)
        assert "Tekst — z pauza." in text

    def test_no_reference_survives_as_visible_text(self, tmp_path):
        text, _ = self.rebuilt_text(tmp_path, self.DOCUMENT)
        assert "&amp;mypauza;" not in text
        assert "&amp;wydawca;" not in text

    def test_a_text_entity_is_expanded_too(self, tmp_path):
        text, _ = self.rebuilt_text(tmp_path, self.DOCUMENT)
        assert "Wydawnictwo Przyklad, Krakow." in text

    def test_the_change_is_reported(self, tmp_path):
        """K6: it is a change to the text, so it needs an entry of its own."""
        _, result = self.rebuilt_text(tmp_path, self.DOCUMENT)
        assert any("own DTD" in f.message for f in result.report.findings)

    def test_an_external_entity_is_refused_not_fetched(self, tmp_path):
        """The file does not get to make this tool go and read something."""
        from epubforge.report import Level

        _, result = self.rebuilt_text(tmp_path, self.EXTERNAL, name="ext.epub")
        warnings = [f for f in result.report.findings if f.level is Level.WARN]
        assert any("refused to resolve" in f.message for f in warnings), [
            f.message for f in result.report.findings
        ]

    def test_the_text_invariant_holds_across_the_expansion(self, tmp_path):
        """K1 must not report a false difference on a source carrying a subset.

        `lxml.html` cannot find `<body>` past an internal subset and hands back
        the stray `]>`, so the comparison used to fail over punctuation while
        the real damage was identical on both sides and invisible.
        """
        from .test_invariants import body_text

        source = self.build(tmp_path, self.DOCUMENT)
        result = rebuild(source, str(tmp_path / "k1.epub"), Policy.preset("preserve"))
        assert "]>" not in body_text(source)
        assert "Wydawnictwo Przyklad" in body_text(result.output_path)


# ---------------------------------------------- inherited alignment
class TestAlignmentInheritedFromAContainer:
    """Found in a real shop EPUB: the cover was already centred, and the tool
    said it had centred it.

    `body.cover { text-align: center }` wrapping a bare `<div><img/></div>` is
    the ordinary way to build a cover page. Reading only the `<div>` finds no
    alignment at all, concludes nobody chose one, and writes an inline
    declaration that changes nothing — a fix reported for work not done.

    The same blindness has a destructive form, which is the reason this is a
    defect and not a cosmetic complaint: a publisher who aligns a container
    deliberately gets overruled, because the rule naming that container is
    invisible from inside it.
    """

    SHEET = "body {{ text-align: justify; }} p {{ text-indent: 2%; }} {extra}"

    DOCUMENT = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>R</title>
<link rel="stylesheet" href="style.css" type="text/css"/></head>
<body class="{body_class}">
<div class="{wrapper}"><img src="picture.png" alt="okladka"/></div>
</body>
</html>"""

    def build(self, tmp_path, *, body_class: str, wrapper: str, extra: str) -> str:
        import zipfile

        from .factory import CONTAINER, MODERN_NAV, png_bytes

        opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Okladka</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="img" href="picture.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""
        path = str(tmp_path / f"{body_class}-{wrapper}.epub")
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
            )
            archive.writestr("OEBPS/package.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
            archive.writestr(
                "OEBPS/chapter.xhtml",
                self.DOCUMENT.format(body_class=body_class, wrapper=wrapper),
            )
            archive.writestr("OEBPS/style.css", self.SHEET.format(extra=extra))
            archive.writestr("OEBPS/picture.png", png_bytes())
        return path

    def rebuild_with(self, tmp_path, *, body_class="zwykly", wrapper="obraz", extra=""):
        source = self.build(tmp_path, body_class=body_class, wrapper=wrapper, extra=extra)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
            return archive.read(name).decode(), result

    def test_a_centred_container_is_left_alone(self, tmp_path):
        html, result = self.rebuild_with(
            tmp_path,
            body_class="cover",
            extra="body.cover { text-align: center; }",
        )
        assert "text-align: center;" not in html, "it was already centred"
        assert not any("image-only paragraph" in f.message for f in result.report.findings)

    def test_a_deliberately_aligned_container_is_not_overruled(self, tmp_path):
        """`body.prawa { text-align: right }` decides where the image goes.

        The rule names the container, not the image, so nothing inside the
        `<div>` reveals it — which is exactly how it used to get overwritten.
        """
        html, _ = self.rebuild_with(
            tmp_path, body_class="prawa", extra="body.prawa { text-align: right; }"
        )
        assert "text-align: center" not in html

    def test_an_inherited_indent_is_still_removed(self, tmp_path):
        """The alignment was chosen; the indent still leaked in from body text."""
        html, result = self.rebuild_with(
            tmp_path,
            body_class="prawa",
            extra="body.prawa { text-align: right; } html { text-indent: 2em; }",
        )
        assert "text-indent: 0" in html
        assert "text-align: center" not in html
        assert any("running-text indent" in f.message for f in result.report.findings)

    def test_an_image_nobody_aligned_is_still_centred(self, tmp_path):
        """The behaviour this whole repair exists for, unchanged."""
        html, result = self.rebuild_with(tmp_path, extra="body { text-indent: 1em; }")
        assert "text-indent: 0; text-align: center;" in html
        assert any("image-only paragraph" in f.message for f in result.report.findings)


# ------------------------------------------- a comment inside <metadata>
class TestACommentInsideTheMetadata:
    """Three books out of a shelf of 64 died before anything could run.

        ValueError: Input object is not an XML element: lxml.etree._Comment

    A comment is not an element and lxml refuses to walk one. Nothing about
    these books was unusual otherwise; one Polish shop simply writes its order
    number into the package metadata as a comment, and Sigil leaves it there.

    The number is a watermark by any other name, so it survives the rebuild —
    removing those is not something this tool does.
    """

    COMMENT = "Wygenerowane przez sklep dla zamowienia numer 1659"

    def build(self, tmp_path, comment: str) -> str:
        import zipfile

        from .factory import CONTAINER, MODERN_NAV, MODERN_CHAPTER, png_bytes

        opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Z komentarzem</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
    <meta name="x-shop-trans-id" content="75c8dd7346b0aa3f8d164b8a"/><!--{comment}-->
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="picture.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""
        path = str(tmp_path / "komentarz.epub")
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
            )
            archive.writestr("OEBPS/package.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
            archive.writestr(
                "OEBPS/chapter.xhtml",
                MODERN_CHAPTER.format(image='<img src="picture.png" alt="x"/>'),
            )
            archive.writestr("OEBPS/picture.png", png_bytes())
        return path

    def test_the_book_rebuilds_at_all(self, tmp_path):
        source = self.build(tmp_path, self.COMMENT)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.output_path, result.report.to_text()

    def test_the_shop_s_note_survives(self, tmp_path):
        source = self.build(tmp_path, self.COMMENT)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert self.COMMENT in package_document(result.output_path)

    def test_the_title_is_still_read_correctly(self, tmp_path):
        """The comment sits among the elements the loop was reading."""
        source = self.build(tmp_path, self.COMMENT)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "<dc:title" in package_document(result.output_path)
        assert "Z komentarzem" in package_document(result.output_path)

    def test_a_comment_that_cannot_be_written_back_is_dropped_not_mangled(self, tmp_path):
        """`--` has no escape inside an XML comment, and a broken package is
        worse than a lost note."""
        source = self.build(tmp_path, "zamowienie -- numer 1659")
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.output_path
        assert "zamowienie" not in package_document(result.output_path)
