"""Constitutional tests — whole-output properties, not individual behaviours.

Kept in their own file because they are a different category from the rest of
the suite. A behaviour test says "this defect is repaired"; these say "whatever
you add next, the output still has this property". They are the tests that are
allowed to veto a feature.

The properties are stated in `CONTRIBUTING.md`; the identifiers below (K1…) are
the ones used there.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import unicodedata
import zipfile

import lxml.html

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

MODIFIED_RE = re.compile(rb"<meta property=\"dcterms:modified\">[^<]*</meta>")


# --------------------------------------------------------------------- helpers
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"


def _local(tag: str) -> str:
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def spine_documents(archive: zipfile.ZipFile) -> list[str]:
    """Content documents in spine order, navigation excluded.

    Not chosen by file extension, and not filtered by looking for "nav" in the
    name. Neither is a fact about an EPUB: the specification says a content
    document is whatever the manifest declares as `application/xhtml+xml`, the
    name may be anything, and `.xml` and `.xhtm` both occur in the wild. Both
    guesses fail silently and in the same direction — a chapter named
    `navigare-necesse-est.xhtml` simply stops being compared, and the invariant
    passes with a narrower scope than anyone intended. On the fixtures in this
    repository that can never show up, because we chose the names; on a corpus
    of real books it would happen constantly and quietly.

    So the documents come from where a reader gets them: container.xml, to the
    package document, to the manifest and the spine.
    """
    from lxml import etree

    try:
        container = etree.fromstring(archive.read("META-INF/container.xml"))
        opf_path = container.find(f".//{{{CONTAINER_NS}}}rootfile").get("full-path")
        package = etree.fromstring(archive.read(opf_path))
    except Exception:
        # Last resort for a source too broken to navigate. Deliberately *wider*
        # than the real answer: a false failure is recoverable, a silently
        # narrowed invariant is the thing this function exists to avoid.
        return sorted(
            n for n in archive.namelist() if n.endswith((".xhtml", ".html", ".htm", ".xml"))
        )
    base = opf_path.rpartition("/")[0]

    manifest: dict[str, tuple[str, set[str]]] = {}
    for item in package.iter():
        if _local(item.tag) != "item":
            continue
        item_id, href = item.get("id"), item.get("href")
        if not item_id or not href:
            continue
        properties = set((item.get("properties") or "").split())
        manifest[item_id] = (href, properties)

    def resolve(href: str) -> str:
        from urllib.parse import unquote

        joined = f"{base}/{unquote(href)}" if base else unquote(href)
        parts: list[str] = []
        for piece in joined.split("/"):
            if piece == ".." and parts:
                parts.pop()
            elif piece not in ("", ".", ".."):
                parts.append(piece)
        return "/".join(parts)

    ordered_ids = [
        ref.get("idref")
        for ref in package.iter()
        if _local(ref.tag) == "itemref" and ref.get("idref")
    ]
    # A book with no usable spine still has content worth comparing.
    if not ordered_ids:
        ordered_ids = list(manifest)

    # No media-type filter on purpose. The fixture declares one chapter as
    # `text/html` and the rebuild corrects that to `application/xhtml+xml`;
    # filtering on the declared type would drop the chapter from one side of
    # the comparison and not the other, and K1 would fail on a book that lost
    # nothing. Anything in the spine is a content document by definition.
    documents: list[str] = []
    names = set(archive.namelist())
    for item_id in ordered_ids:
        entry = manifest.get(item_id)
        if entry is None:
            continue
        href, properties = entry
        if "nav" in properties:
            continue
        path = resolve(href)
        if path in names:
            documents.append(path)
    return documents


def body_text(path: str) -> str:
    """Every readable character in the book, in spine order, whitespace-folded.

    Deliberately scoped to `<body>`. An earlier version compared whole documents
    and reported false differences, because `text_content()` pulls in `<title>`
    from the head — and the rebuild writes the chapter title there.
    """
    from epubforge import xhtml as xhtml_module

    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in spine_documents(archive):
            # The DOCTYPE goes first. `lxml.html` loses its footing on an
            # internal subset: it fails to find `<body>` and hands back the
            # stray `]>` as text, so a source document carrying one compares
            # unequal to its own rebuild over punctuation rather than content.
            document = lxml.html.fromstring(xhtml_module.strip_doctype(archive.read(name)))
            body = document.xpath('//*[local-name()="body"]')
            parts.append((body[0] if body else document).text_content())
    folded = re.sub(r"\s+", " ", " ".join(parts))
    return unicodedata.normalize("NFC", folded).strip()


def block_count(path: str) -> int:
    """How many text blocks the book is divided into.

    K1 compares a stream of characters, so it cannot see two paragraphs merged
    into one or one split into two — the characters are all still there, in
    order. That is fine today because nothing does it, and it stops being fine
    at the typography stage, where joining paragraphs broken by a PDF
    conversion is on the list and is one of the riskiest things this tool could
    ever do. Counting blocks gives that change somewhere to show up.
    """
    total = 0
    with zipfile.ZipFile(path) as archive:
        for name in spine_documents(archive):
            document = lxml.html.fromstring(archive.read(name))
            total += len(
                document.xpath(
                    '//*[local-name()="p" or local-name()="div" or local-name()="li"'
                    ' or local-name()="h1" or local-name()="h2" or local-name()="h3"'
                    ' or local-name()="h4" or local-name()="h5" or local-name()="h6"'
                    ' or local-name()="blockquote" or local-name()="td" or local-name()="th"]'
                )
            )
    return total


def entries(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def without_modified(opf: bytes) -> bytes:
    """The package document with the one field that is *meant* to change removed."""
    return MODIFIED_RE.sub(b"", opf)


def digest(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ------------------------------------------------------------------------ K1
def test_rebuild_preserves_every_readable_character(legacy_epub, tmp_path):
    """K1. No stage may lose, gain or reorder a character of the book's text."""
    result = rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    assert result.output_path, result.report.to_text()
    assert body_text(result.output_path) == body_text(legacy_epub)


def test_strict_mode_also_preserves_every_readable_character(legacy_epub, tmp_path):
    """K1 is not relaxed by --strict. Conformance may move markup, never text."""
    result = rebuild(legacy_epub, str(tmp_path / "strict.epub"), Policy.preset("strict"))
    assert result.output_path, result.report.to_text()
    assert body_text(result.output_path) == body_text(legacy_epub)


# ------------------------------------------------------------------------ K2
def test_output_is_byte_reproducible(legacy_epub, tmp_path):
    """K2. Two runs on the same input differ only in `dcterms:modified`."""
    one = rebuild(legacy_epub, str(tmp_path / "one.epub"), Policy.preset("preserve"))
    two = rebuild(legacy_epub, str(tmp_path / "two.epub"), Policy.preset("preserve"))

    first, second = entries(one.output_path), entries(two.output_path)
    assert set(first) == set(second)
    differing = {name for name in first if first[name] != second[name]}
    assert differing <= {"EPUB/package.opf"}, differing
    assert without_modified(first["EPUB/package.opf"]) == without_modified(
        second["EPUB/package.opf"]
    )


def test_zip_entries_carry_no_wall_clock_timestamp(legacy_epub, tmp_path):
    """A timestamp from the clock is the usual reason K2 quietly stops holding."""
    result = rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    with zipfile.ZipFile(result.output_path) as archive:
        stamps = {info.filename: info.date_time for info in archive.infolist()}
    assert set(stamps.values()) == {(1980, 1, 1, 0, 0, 0)}, stamps


def test_frozen_modified_makes_the_whole_file_reproducible(legacy_epub, tmp_path):
    """With the one moving part pinned, the output hashes identically."""
    policy = Policy.preset("preserve", modified_override="2020-01-01T00:00:00Z")
    one = rebuild(legacy_epub, str(tmp_path / "one.epub"), policy)
    two = rebuild(legacy_epub, str(tmp_path / "two.epub"), policy)
    assert digest(one.output_path) == digest(two.output_path)


# ------------------------------------------------------------------------ K3
def test_second_pass_changes_nothing_but_the_timestamp(legacy_epub, tmp_path):
    """K3. Idempotence at the level of file *contents*, not of file names.

    The weaker version of this test — comparing the set of names — passed while
    two separate defects silently changed the data: the series number was lost
    on the second pass, and an auto-supplied empty alt was promoted into an
    `alternativeText` claim.
    """
    first = rebuild(legacy_epub, str(tmp_path / "first.epub"), Policy.preset("preserve"))
    second = rebuild(first.output_path, str(tmp_path / "second.epub"), Policy.preset("preserve"))
    assert second.output_path, second.report.to_text()

    one, two = entries(first.output_path), entries(second.output_path)
    assert set(one) == set(two)
    differing = {name for name in one if one[name] != two[name]}
    assert differing <= {"EPUB/package.opf"}, differing
    assert without_modified(one["EPUB/package.opf"]) == without_modified(
        two["EPUB/package.opf"]
    )


def test_second_pass_reports_no_errors(legacy_epub, tmp_path):
    from epubforge.report import Level

    first = rebuild(legacy_epub, str(tmp_path / "first.epub"), Policy.preset("preserve"))
    second = rebuild(first.output_path, str(tmp_path / "second.epub"), Policy.preset("preserve"))
    assert second.report.count(Level.ERROR) == 0, second.report.to_text()


# ----------------------------------------------- the helper the invariants use
class TestDocumentSelection:
    """If this narrows silently, K1 passes while the book loses text.

    Both of the guesses this replaced — file extension, and "nav" appearing in
    the name — fail in the same direction: they *exclude* real content, so the
    comparison quietly covers less of the book and still reports success. That
    can never show up on fixtures whose names we chose ourselves.
    """

    OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title><dc:language>pl</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="spis.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="a" href="navigare-necesse-est.xhtml" media-type="application/xhtml+xml"/>
    <item id="b" href="chapter.xml" media-type="application/xhtml+xml"/>
    <item id="c" href="rozdzial-o-nawigacji.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="a"/><itemref idref="b"/><itemref idref="c"/></spine>
</package>
"""
    DOCUMENT = (
        b'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
        b"<body><p>%s</p></body></html>"
    )

    def build(self, path) -> str:
        with zipfile.ZipFile(path, "w") as handle:
            handle.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" '
                f'xmlns="{CONTAINER_NS}"><rootfiles><rootfile full-path="OEBPS/p.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            handle.writestr("OEBPS/p.opf", self.OPF)
            handle.writestr("OEBPS/spis.xhtml", self.DOCUMENT % b"NAWIGACJA")
            handle.writestr("OEBPS/navigare-necesse-est.xhtml", self.DOCUMENT % b"ALFA")
            handle.writestr("OEBPS/chapter.xml", self.DOCUMENT % b"BETA")
            handle.writestr("OEBPS/rozdzial-o-nawigacji.xhtml", self.DOCUMENT % b"GAMMA")
        return str(path)

    def test_a_chapter_whose_name_contains_nav_is_still_compared(self, tmp_path):
        assert "ALFA" in body_text(self.build(tmp_path / "book.epub"))

    def test_a_content_document_named_xml_is_still_compared(self, tmp_path):
        assert "BETA" in body_text(self.build(tmp_path / "book.epub"))

    def test_the_real_navigation_document_is_excluded(self, tmp_path):
        """Recognised by properties="nav", which is what actually marks it."""
        assert "NAWIGACJA" not in body_text(self.build(tmp_path / "book.epub"))

    def test_documents_come_back_in_spine_order(self, tmp_path):
        assert body_text(self.build(tmp_path / "book.epub")) == "ALFA BETA GAMMA"

    def test_an_unnavigable_archive_falls_back_to_a_wider_set(self, tmp_path):
        """Wider, never narrower: a false failure beats a silent pass."""
        path = tmp_path / "broken.epub"
        with zipfile.ZipFile(path, "w") as handle:
            handle.writestr("OEBPS/ch.xhtml", self.DOCUMENT % b"DELTA")
        assert "DELTA" in body_text(str(path))


# ------------------------------------------------------------------ the source
class TestTheSourceIsNeverDestroyed:
    """The one file the tool must not be able to ruin.

    Everything it writes can be produced again from the source; the source
    cannot. The guard lives in `rebuild()` rather than only in the CLI and the
    window, so a library caller gets it too — and so this can be asserted once
    instead of once per front end.
    """

    def test_writing_over_the_source_is_refused(self, legacy_epub):
        from epubforge.report import Level

        before = pathlib.Path(legacy_epub).read_bytes()
        result = rebuild(legacy_epub, legacy_epub, Policy.preset("preserve"))

        assert result.output_path is None
        assert pathlib.Path(legacy_epub).read_bytes() == before
        assert any(
            f.level is Level.ERROR and "source" in f.message for f in result.report.findings
        )

    def test_an_equivalent_path_is_refused_too(self, legacy_epub, tmp_path):
        """Same file, spelled differently, is still the same file."""
        indirect = str(pathlib.Path(legacy_epub).parent / "." / pathlib.Path(legacy_epub).name)
        before = pathlib.Path(legacy_epub).read_bytes()
        result = rebuild(legacy_epub, indirect, Policy.preset("preserve"))

        assert result.output_path is None
        assert pathlib.Path(legacy_epub).read_bytes() == before

    def test_an_ordinary_rebuild_leaves_the_source_untouched(self, legacy_epub, tmp_path):
        before = pathlib.Path(legacy_epub).read_bytes()
        rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert pathlib.Path(legacy_epub).read_bytes() == before
