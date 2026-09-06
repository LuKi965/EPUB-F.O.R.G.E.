"""K3 on a rebuild of a rebuild: the second pass changes nothing.

EF-088. The independent audit of 2026-09-05 found six of sixty shelf books
changing on a second rebuild; measured on the whole shelf it was fifteen of a
hundred and sixty, in six distinct mechanisms. Every mechanism had the same
shape — a decision taken from evidence the rebuild itself then changed — and
each one here is a synthetic book that showed it, rebuilt twice, compared
member by member. The package document is compared too, with only
`dcterms:modified` normalised, because leaving it out of the comparison was
the auditor's other remark and a fair one.
"""

from __future__ import annotations

import pathlib
import re
import zipfile

import pytest

from epubforge import decisions, pipeline
from epubforge.policy import Policy

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
    'version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

PARAGRAPH = (
    "Zdanie na tyle długie, żeby profil książki uznał je za tekst główny, i "
    "jeszcze jedno zdanie po nim, bo jedno to za mało na akapit. "
)


def document(title: str, body: str, head_extra: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        f"<title>{title}</title>{head_extra}</head>"
        f"<body>{body}</body></html>"
    )


def chapter(title: str, extra: str = "", head_extra: str = "") -> str:
    return document(
        title, f"<h1>{title}</h1><p>{PARAGRAPH * 3}</p><p>{PARAGRAPH * 2}</p>{extra}", head_extra
    )


def nav(entries: list[tuple[str, str]], synthesised_mark: bool = False) -> str:
    items = "".join(f'<li><a href="{href}">{label}</a></li>' for label, href in entries)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Spis</title></head>'
        f'<body><nav epub:type="toc"><h1>Spis treści</h1><ol>{items}</ol></nav></body></html>'
    )


def book(
    path: pathlib.Path,
    documents: dict[str, str],
    spine: list[str],
    *,
    nav_doc: str | None = None,
    styles: dict[str, str] | None = None,
    extra_manifest: dict[str, str] | None = None,
    language: str = "pl",
) -> str:
    """One EPUB 3 with the documents given; `nav_doc` of `None` means no
    contents at all — the case the program synthesises them for."""
    manifest = []
    for name in documents:
        manifest.append(
            f'<item id="{name.split(".")[0]}" href="{name}" media-type="application/xhtml+xml"/>'
        )
    for name in styles or {}:
        manifest.append(f'<item id="{name.split(".")[0]}" href="{name}" media-type="text/css"/>')
    if nav_doc is not None:
        manifest.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
    for name, media in (extra_manifest or {}).items():
        manifest.append(f'<item id="{name.split(".")[0]}" href="{name}" media-type="{media}"/>')
    itemrefs = "".join(f'<itemref idref="{name.split(".")[0]}"/>' for name in spine)
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:identifier id=\"uid\">urn:uuid:k3-test</dc:identifier>"
        "<dc:title>Książka K3</dc:title><dc:creator>Autor</dc:creator>"
        f"<dc:language>{language}</dc:language>"
        '<meta property="dcterms:modified">2024-01-01T00:00:00Z</meta>'
        "</metadata>"
        f"<manifest>{''.join(manifest)}</manifest>"
        f"<spine>{itemrefs}</spine></package>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/content.opf", opf)
        for name, text in documents.items():
            archive.writestr(f"OEBPS/{name}", text)
        for name, text in (styles or {}).items():
            archive.writestr(f"OEBPS/{name}", text)
        if nav_doc is not None:
            archive.writestr("OEBPS/nav.xhtml", nav_doc)
    return str(path)


class Recommended:
    """Whoever is asked answers with the recommended option, for the whole group."""

    def ask(self, question):
        return decisions.Answer(option=question.recommended, apply_to_group=True)


def members(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


_MODIFIED = re.compile(rb'(<meta property="dcterms:modified">)[^<]*(</meta>)')


def normalised(name: str, data: bytes) -> bytes:
    if name.endswith(".opf"):
        return _MODIFIED.sub(rb"\1X\2", data)
    return data


def twice(source: str, tmp_path: pathlib.Path, mode: str = "preserve"):
    """Rebuild, rebuild the result, and hand back both archives' members."""
    policy = Policy.preset(mode, render_gate="off", validate_before_publish="off")
    policy.reproducible = True
    first = pipeline.rebuild(source, str(tmp_path / "first.epub"), policy, asker=Recommended(), standing={})
    assert first.output_path, first.report.to_text()
    second = pipeline.rebuild(
        first.output_path, str(tmp_path / "second.epub"), policy, asker=Recommended(), standing={}
    )
    assert second.output_path, second.report.to_text()
    return first, second


def assert_stable(first, second) -> None:
    a, b = members(first.output_path), members(second.output_path)
    differing = sorted(
        name for name in set(a) | set(b)
        if normalised(name, a.get(name, b"")) != normalised(name, b.get(name, b""))
    )
    assert not differing, f"the second rebuild changed: {differing}"


class TestADocumentTheNavigationReachesIsNamedOnce:
    """Four shelf books: a contents page outside the spine, put into it by the
    navigation stage *after* the structure stage had numbered the files, so the
    second rebuild found it in the reading order and numbered it."""

    def test_the_contents_page_keeps_its_name_on_the_second_rebuild(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            {
                "c1.xhtml": chapter("Rozdział pierwszy"),
                "toc.xhtml": document("Spis", '<h1>Spis</h1><p><a href="c1.xhtml">Rozdział pierwszy</a></p>'),
                "c2.xhtml": chapter("Rozdział drugi"),
            },
            ["c1.xhtml", "c2.xhtml"],
            nav_doc=nav([("Spis", "toc.xhtml"), ("Rozdział pierwszy", "c1.xhtml"), ("Rozdział drugi", "c2.xhtml")]),
        )
        first, second = twice(source, tmp_path)
        assert "nav.unspined-target-added" in {f.rule for f in first.report.findings}
        names = [n for n in members(first.output_path) if "toc" in n.lower() and n.endswith(".xhtml") and "nav" not in n]
        assert names and re.search(r"/\d{4}-", names[0]), f"numbered in the first pass already: {names}"
        assert_stable(first, second)

    def test_an_out_of_flow_document_is_not_a_chapter(self, tmp_path):
        """Being spined before the naming must not turn a colophon into
        `chapter-02` and push the real chapter two along."""
        source = book(
            tmp_path / "in.epub",
            {
                "c1.xhtml": chapter("Rozdział pierwszy"),
                "kolofon.xhtml": document("Kolofon", "<p>Skład i druk.</p>"),
                "c2.xhtml": chapter("Rozdział drugi"),
            },
            ["c1.xhtml", "c2.xhtml"],
            nav_doc=nav([("Rozdział pierwszy", "c1.xhtml"), ("Kolofon", "kolofon.xhtml"), ("Rozdział drugi", "c2.xhtml")]),
        )
        first, second = twice(source, tmp_path)
        names = sorted(n for n in members(first.output_path) if n.endswith(".xhtml"))
        assert any(n.endswith("-kolofon.xhtml") for n in names), names
        assert any(n.endswith("chapter-02.xhtml") for n in names), names
        assert not any(n.endswith("chapter-03.xhtml") for n in names), names
        assert_stable(first, second)


class TestSynthesisedContentsAreNotEvidence:
    """Two shelf books: a book with no contents got them from the navigation
    stage, after the naming; the second rebuild read them back as the
    publisher's word and named the documents by them."""

    def test_the_names_are_the_same_on_both_passes(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            {"okladka.xhtml": document("Okładka", "<p>Okładka</p>"), "tekst.xhtml": chapter("Het aapje")},
            ["okladka.xhtml", "tekst.xhtml"],
            nav_doc=None,
        )
        first, second = twice(source, tmp_path)
        assert "nav.toc-synthesised" in {f.rule for f in first.report.findings}
        assert_stable(first, second)

    def test_the_synthesised_contents_carry_the_marker_and_name_no_chapter(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            {"okladka.xhtml": document("Okładka", "<p>Okładka</p>"), "tekst.xhtml": chapter("Het aapje")},
            ["okladka.xhtml", "tekst.xhtml"],
            nav_doc=None,
        )
        first, _ = twice(source, tmp_path)
        out = members(first.output_path)
        written_nav = next(data for name, data in out.items() if name.endswith("nav.xhtml"))
        assert b"EPUB-Forge: contents synthesised" in written_nav
        # Contents this program invented say where the documents are, not
        # where the chapters begin: the text document keeps its own stem.
        assert any(n.endswith("-tekst.xhtml") for n in out), sorted(out)
        assert not any("chapter-" in n for n in out), sorted(out)


class TestTheHeadIsSerialisedTheSameWayTwice:
    """Two shelf books, twenty-four documents: the charset declaration went out
    with its tail and came back without one, so the whitespace between it and
    the next element was the difference between the passes."""

    def test_dead_links_removed_leave_a_stable_head(self, tmp_path):
        # The shelf shape: the publisher's own charset declaration first, the
        # dead links right after it, each on its own line.
        page = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>\n'
            '    <meta charset="utf-8"/>\n'
            '    <link rel="stylesheet" href="missing-a.css"/>\n'
            '    <link rel="stylesheet" href="missing-b.css"/>\n'
            '    <link rel="stylesheet" href="missing-c.css"/>\n'
            '    <link rel="stylesheet" href="style.css"/>\n'
            '    <title>Rozdział</title>\n  </head>'
            f"<body><h1>Rozdział</h1><p>{PARAGRAPH * 3}</p><p>{PARAGRAPH * 2}</p></body></html>"
        )
        source = book(
            tmp_path / "in.epub",
            {"c1.xhtml": page},
            ["c1.xhtml"],
            nav_doc=nav([("Rozdział", "c1.xhtml")]),
            styles={"style.css": "p { margin: 0 }"},
        )
        first, second = twice(source, tmp_path)
        assert "xhtml.dead-link-removed" in {f.rule for f in first.report.findings}
        assert_stable(first, second)


class TestAnEmptyRuleForAClassInUseIsKept:
    """One shelf book: `.sans { }` in the linked sheet was swept as noise, so the
    class became orphaned, and the second rebuild restored a real `.sans` rule
    from another rendition's sheet into a page the publisher left plain."""

    def test_the_class_stays_defined_where_the_document_can_reach_it(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            {"c1.xhtml": chapter("Rozdział", extra='<p class="sans">Mała czcionka.</p>',
                                 head_extra='<link rel="stylesheet" href="linked.css"/>')},
            ["c1.xhtml"],
            nav_doc=nav([("Rozdział", "c1.xhtml")]),
            styles={"linked.css": "p { margin: 0 }\n.sans { }\n", "other.css": ".sans { font-size: 0.8em }\n"},
        )
        first, second = twice(source, tmp_path, mode="strict")
        out = members(first.output_path)
        sheet = next(data for name, data in out.items() if name.endswith("linked.css"))
        assert b".sans" in sheet, sheet
        assert "xhtml.orphaned-styling-restored" not in {f.rule for f in first.report.findings}
        assert_stable(first, second)


class TestAPagePinnedToTheFootIsRepairedOnce:
    """One shelf book: the repair read the class rule, never the element's own
    style attribute, and so appended `position: static; margin-top: auto` a
    second time and a second style block with it."""

    PAGE = document(
        "Dedykacja",
        '<div class="dol"><p>Dla A.</p></div>',
        '<link rel="stylesheet" href="style.css"/>',
    )

    def test_the_second_rebuild_changes_nothing(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            {"c1.xhtml": chapter("Rozdział"), "ded.xhtml": self.PAGE},
            ["c1.xhtml", "ded.xhtml"],
            nav_doc=nav([("Rozdział", "c1.xhtml"), ("Dedykacja", "ded.xhtml")]),
            styles={"style.css": ".dol { position: absolute; bottom: 0; width: 100% }"},
        )
        first, second = twice(source, tmp_path)
        assert "xhtml.position-pinned-in-flow" in {f.rule for f in first.report.findings}
        page = next(data for name, data in members(first.output_path).items() if b'class="dol"' in data)
        assert page.count(b"margin-top: auto") == 1, page
        assert_stable(first, second)

    def test_an_element_already_static_inline_is_left_alone(self, tmp_path):
        page = document(
            "Dedykacja",
            '<div class="dol" style="position: static"><p>Dla A.</p></div>',
            '<link rel="stylesheet" href="style.css"/>',
        )
        source = book(
            tmp_path / "in.epub",
            {"c1.xhtml": chapter("Rozdział"), "ded.xhtml": page},
            ["c1.xhtml", "ded.xhtml"],
            nav_doc=nav([("Rozdział", "c1.xhtml"), ("Dedykacja", "ded.xhtml")]),
            styles={"style.css": ".dol { position: absolute; bottom: 0; width: 100% }"},
        )
        first, _ = twice(source, tmp_path)
        assert "xhtml.position-pinned-in-flow" not in {f.rule for f in first.report.findings}


class TestAStyleBlockIsWrittenAsCss:
    """Three shelf books: `>` inside a document's `<style>` went out as `&gt;`,
    which an HTML parser reads literally — and this program, reading its own
    output, found a selector matching nothing and swept the publisher's list
    styling on the second pass."""

    def test_the_child_combinator_survives_serialisation(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            {"c1.xhtml": chapter("Rozdział", extra='<ol class="lst"><li>a</li></ol>',
                                 head_extra="<style>ol.lst > li { color: red }</style>")},
            ["c1.xhtml"],
            nav_doc=nav([("Rozdział", "c1.xhtml")]),
        )
        first, second = twice(source, tmp_path)
        page = next(data for name, data in members(first.output_path).items() if name.endswith(".xhtml") and b"ol.lst" in data)
        assert b"&gt;" not in page
        assert b"ol.lst > li" in page or b"ol.lst>li" in page, page
        assert_stable(first, second)


class TestJoiningAHyphenTouchesOnlyThatWord:
    """One shelf book: joining `pick-up` also rewrote `pick-uptruck` into
    `pickuptruck` — a word nobody had been asked about — and the second rebuild
    then found the book "writing it joined elsewhere" and joined the rest."""

    def test_a_longer_word_starting_with_the_candidate_is_untouched(self, tmp_path):
        text = (
            "Wsiadł do pick-up i pojechał. Stary pickup stał pod domem, a pickup "
            "sąsiada nie. Ten pick-uptruck był czerwony, a tamten pick-uptruck niebieski. "
        )
        source = book(
            tmp_path / "in.epub",
            {"c1.xhtml": chapter("Rozdział", extra=f"<p>{text}{PARAGRAPH}</p>")},
            ["c1.xhtml"],
            nav_doc=nav([("Rozdział", "c1.xhtml")]),
        )
        first, second = twice(source, tmp_path)
        page = b"".join(data for name, data in members(first.output_path).items() if name.endswith(".xhtml"))
        assert b"pick-uptruck" in page, "the longer word must keep its hyphen"
        assert_stable(first, second)
