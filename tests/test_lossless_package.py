"""The last of EF-004: what the package declared and the model could not hold.

Three constructs went missing because the model had no field for them, and a
writer that emits from the model has nothing to emit:

* `<collection>` — an open vocabulary, so there was nothing to model field by
  field and the whole element was dropped, both of them;
* a manifest item whose href is a URL — warned about and discarded, so the
  output no longer declared a resource the source did;
* the second `belongs-to-collection` — the model held one series, so a book
  published inside a boxed set *and* as part of a series kept whichever came
  first.

None of the three produced an error, a warning worth acting on, or an invalid
file. That is the shape of this whole finding: the output was valid, smaller,
and quiet about it.
"""

from __future__ import annotations

import zipfile

import pytest
from lxml import etree

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.reader import read_epub
from epubforge.report import Report

from .kitchen_sink import make_kitchen_sink

OPF = "http://www.idpf.org/2007/opf"


@pytest.fixture(scope="module")
def sink(tmp_path_factory):
    return make_kitchen_sink(str(tmp_path_factory.mktemp("lossless") / "sink.epub"))


@pytest.fixture(params=["preserve", "strict", "minimal"], scope="module")
def rebuilt(request, sink, tmp_path_factory):
    folder = tmp_path_factory.mktemp(f"out-{request.param}")
    result = rebuild(sink, str(folder / "out.epub"), Policy.preset(request.param))
    assert result.output_path, result.report.to_text()
    return result.output_path


def package_of(path: str):
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".opf"))
        return etree.fromstring(archive.read(name)), archive.namelist()


class TestCollections:
    def test_both_of_them_come_back(self, rebuilt):
        root, _ = package_of(rebuilt)
        roles = [c.get("role") for c in root.findall(f"{{{OPF}}}collection")]
        assert roles == [
            "https://example.invalid/roles#notatki",
            "https://example.invalid/roles#dodatki",
        ]

    def test_nesting_comes_back(self, rebuilt):
        root, _ = package_of(rebuilt)
        outer = root.findall(f"{{{OPF}}}collection")[1]
        nested = outer.findall(f"{{{OPF}}}collection")
        assert [c.get("role") for c in nested] == [
            "https://example.invalid/roles#zagniezdzona"
        ]
        assert len(nested[0].findall(f"{{{OPF}}}link")) == 2

    def test_the_links_point_at_the_files_where_they_now_are(self, rebuilt):
        import posixpath

        root, names = package_of(rebuilt)
        with zipfile.ZipFile(rebuilt) as archive:
            opf_name = next(n for n in archive.namelist() if n.endswith(".opf"))
        base = posixpath.dirname(opf_name)

        found = 0
        for collection in root.iter(f"{{{OPF}}}collection"):
            for link in collection.findall(f"{{{OPF}}}link"):
                href = link.get("href")
                resolved = posixpath.normpath(posixpath.join(base, href))
                assert resolved in names, f"{href!r} → {resolved!r} is not in the container"
                found += 1
        assert found == 4

    def test_a_second_pass_does_not_multiply_them(self, rebuilt, tmp_path):
        """Reading our own output back has to give the same thing. A carried
        construct that grows on every pass is a slower kind of corruption."""
        again = rebuild(rebuilt, str(tmp_path / "again.epub"), Policy.preset("preserve"))
        root, _ = package_of(again.output_path)
        assert len(root.findall(f"{{{OPF}}}collection")) == 2
        assert len(list(root.iter(f"{{{OPF}}}collection"))) == 3


class TestRemoteResources:
    def test_the_declaration_survives(self, rebuilt):
        root, _ = package_of(rebuilt)
        hrefs = [
            item.get("href")
            for item in root.iter(f"{{{OPF}}}item")
            if (item.get("href") or "").startswith("http")
        ]
        assert hrefs == ["https://example.invalid/trailer.mp4"]

    def test_nothing_was_fetched_into_the_container(self, rebuilt):
        _, names = package_of(rebuilt)
        assert not [n for n in names if n.endswith(".mp4")]

    def test_the_reader_says_it_carried_one(self, sink):
        report = Report()
        book = read_epub(sink, report)
        assert [r.href for r in book.remote_resources] == [
            "https://example.invalid/trailer.mp4"
        ]
        assert any("hosted elsewhere" in f.message for f in report.findings)


class TestEveryCollectionMembership:
    def test_both_the_set_and_the_series_come_back(self, rebuilt):
        root, _ = package_of(rebuilt)
        names = [
            (m.text or "").strip()
            for m in root.iter(f"{{{OPF}}}meta")
            if m.get("property") == "belongs-to-collection"
        ]
        assert sorted(names) == ["Dzieła zebrane", "Klasyka"]

    def test_each_keeps_its_own_type_and_position(self, rebuilt):
        root, _ = package_of(rebuilt)
        by_id = {m.get("id"): (m.text or "").strip() for m in root.iter(f"{{{OPF}}}meta") if m.get("id")}
        attached: dict[str, dict[str, str]] = {}
        for meta in root.iter(f"{{{OPF}}}meta"):
            refines = (meta.get("refines") or "").lstrip("#")
            if refines in by_id:
                attached.setdefault(by_id[refines], {})[meta.get("property")] = (
                    meta.text or ""
                ).strip()

        assert attached["Dzieła zebrane"]["collection-type"] == "set"
        assert attached["Dzieła zebrane"]["group-position"] == "1"
        assert attached["Klasyka"]["collection-type"] == "series"
        assert attached["Klasyka"]["group-position"] == "7"

    def test_a_second_pass_does_not_multiply_them(self, rebuilt, tmp_path):
        again = rebuild(rebuilt, str(tmp_path / "again.epub"), Policy.preset("preserve"))
        root, _ = package_of(again.output_path)
        names = [
            (m.text or "").strip()
            for m in root.iter(f"{{{OPF}}}meta")
            if m.get("property") == "belongs-to-collection"
        ]
        assert sorted(names) == ["Dzieła zebrane", "Klasyka"]

    def test_a_book_in_no_collection_says_nothing(self, tmp_path):
        """The opposite failure: emitting an empty collection for every book."""
        from .factory import make_modern_epub

        source = make_modern_epub(str(tmp_path / "plain.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        root, _ = package_of(result.output_path)
        assert not [
            m for m in root.iter(f"{{{OPF}}}meta")
            if m.get("property") == "belongs-to-collection"
        ]


class TestAPropertyThatWasNotTrue:
    """Withdrawing a false claim is right; doing it silently is not.

    The kitchen sink declares `scripted` on a document containing no script,
    which EPUBCheck reports as an error against the *source*. Manifest
    properties are derived from the document rather than copied, so it does not
    survive — and until 0.2.3 nothing said so, which meant a publisher got a
    package differing from theirs with no line in the report to explain it.
    """

    def test_the_claim_does_not_survive(self, sink, tmp_path):
        """`minimal` is excluded on purpose: it promises to touch nothing, and
        that promise covers a declaration that is wrong as well as one that is
        right. The report still says the source is invalid."""
        result = rebuild(sink, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        root, _ = package_of(result.output_path)
        scripted = [
            item.get("href")
            for item in root.iter(f"{{{OPF}}}item")
            if "scripted" in (item.get("properties") or "")
        ]
        assert not scripted

    def test_the_withdrawal_is_reported(self, sink, tmp_path):
        result = rebuild(sink, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        withdrawn = [f for f in result.report.findings if "withdrew manifest" in f.message]
        assert withdrawn, [f.message for f in result.report.findings]
        assert "scripted" in withdrawn[0].message

    def test_a_true_claim_is_left_alone(self, tmp_path):
        """The opposite failure would be worse: stripping a property a reading
        system needs in order to allow scripting at all."""
        from .factory import CONTAINER, MODERN_NAV, write_zip

        opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Skrypt</dc:title><dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="ch.xhtml" media-type="application/xhtml+xml" properties="scripted"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        document = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            '<meta charset="utf-8"/><title>S</title></head><body><h1>S</h1>'
            "<p>Tekst.</p><script>void 0;</script></body></html>"
        )
        source = write_zip(
            str(tmp_path / "scripted.epub"),
            {
                "META-INF/container.xml": CONTAINER.replace(
                    "OEBPS/content.opf", "OEBPS/package.opf"
                ),
                "OEBPS/package.opf": opf,
                "OEBPS/nav.xhtml": MODERN_NAV,
                "OEBPS/ch.xhtml": document,
            },
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        root, _ = package_of(result.output_path)
        assert [
            item for item in root.iter(f"{{{OPF}}}item")
            if "scripted" in (item.get("properties") or "")
        ]
        assert not [f for f in result.report.findings if "withdrew manifest" in f.message]
