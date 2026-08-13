"""The findings of the 0.2.19 engineering audit, one test each.

An outside audit of commit `003d254` returned thirty findings against this
program. Nine were checkable here in an afternoon; **nine of nine reproduced
exactly as written**, including one this project had argued itself into on
purpose — the reader skipping an unreadable archive entry and rebuilding the
rest. That one is the reason this file exists rather than a changelog entry:
the failure it produced is the failure this whole program is against, and it
shipped for nineteen releases behind a status nobody reads.

Each test below is a finding. The comment above each says what was measured on
0.2.19, so that a future change which brings it back has something to fail
against rather than a rule to re-derive. The audit's own second step asked for
exactly this before any fix, and the fixes came after.

Findings not answered here are open and named in `docs/ROADMAP.md`: F-002
(typed paths), F-003 (standalone SVG on relayout), F-004 (parse modes), F-006
(a full pre-commit gate — this file closes its first half), F-017 and F-028
(the fidelity harness).
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from epubforge.pipeline import Status, rebuild
from epubforge.policy import CORE_IMAGE_TYPES, Policy

CONTAINER = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    b'<rootfiles><rootfile full-path="OEBPS/package.opf" '
    b'media-type="application/oebps-package+xml"/></rootfiles></container>'
)


def opf(manifest: str, spine: str, metadata: str = "", identifier: str | None = None) -> bytes:
    pid = identifier or "urn:uuid:00000000-0000-4000-8000-000000000000"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="pid">{pid}</dc:identifier>
<dc:title>T</dc:title><dc:language>en</dc:language>
<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>{metadata}
</metadata>
<manifest>{manifest}</manifest>
<spine>{spine}</spine>
</package>""".encode()


def page(body: str, lang: str = "en") -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" '
        f'lang="{lang}" xml:lang="{lang}">'
        "<head><meta charset=\"utf-8\"/><title>t</title></head>"
        f"<body>{body}</body></html>"
    ).encode()


NAV = page('<nav epub:type="toc"><ol><li><a href="chapter.xhtml">c</a></li></ol></nav>')
CHAPTER_ITEM = '<item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
NAV_ITEM = '<item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'


def build(path, entries: dict) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        for name, data in entries.items():
            archive.writestr(name, data)
    return str(path)


def simple(path, *, body: str = "<p>x</p>", lang: str = "en", metadata: str = "",
           identifier: str | None = None) -> str:
    return build(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>',
                                 metadata, identifier),
        "OEBPS/nav.xhtml": NAV,
        "OEBPS/chapter.xhtml": page(body, lang),
    })


def read(path: str, ending: str) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(ending))
        return archive.read(name).decode("utf-8", "replace")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestF001AnUnreadableEntryStopsTheRebuild:
    """**Measured on 0.2.19:** an EPUB whose only chapter exceeded the per-entry
    limit produced `status = succeeded-with-problems`, a file on disk, and no
    chapter in it. The archive held `mimetype`, `container.xml`, the package,
    the nav and the NCX — a complete, openable, empty book.

    The reader had the argument written down beside the archive-wide limit and
    reached the opposite conclusion there: *for a tool whose first rule is that
    no character is lost, half a book is a worse outcome than a refusal.* Both
    cannot be right.
    """

    @pytest.fixture
    def tiny_limit(self, monkeypatch):
        monkeypatch.setattr("epubforge.reader.MAX_ENTRY_BYTES", 1024)

    @pytest.fixture
    def source(self, tmp_path):
        return simple(tmp_path / "in.epub", body="<p>" + "TRESC " * 500 + "</p>")

    def test_nothing_is_written(self, tiny_limit, source, tmp_path):
        out = tmp_path / "out.epub"
        result = rebuild(source, str(out), Policy.preset("preserve"))
        assert result.status is Status.BLOCKED
        assert result.output_path is None
        assert not out.exists(), "a book with the chapter missing must not reach the disk"

    def test_the_report_names_what_went_missing(self, tiny_limit, source, tmp_path):
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        finding = next(
            f for f in result.report.findings if f.rule == "package.input-incomplete"
        )
        assert "chapter.xhtml" in finding.values["names"]

    def test_the_person_holding_the_book_can_still_say_go_on(self, tiny_limit, source, tmp_path):
        """The owner's standing rule, applied to a refusal instead of a
        deletion. It does not make the loss quiet."""
        policy = Policy.preset("preserve", allow_incomplete=True)
        result = rebuild(source, str(tmp_path / "out.epub"), policy)
        assert result.output_path is not None
        assert "package.input-incomplete-allowed" in rules_of(result)

    def test_a_book_that_reads_completely_is_untouched_by_any_of_this(self, source, tmp_path):
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.SUCCEEDED
        assert "TRESC" in read(result.output_path, "chapter.xhtml")


class TestF013TwoManifestItemsWithOneId:
    """**Measured on 0.2.19:** a manifest with two `id="dup"` items and a spine
    naming it produced a book reading the *second* document, with no finding of
    any kind. The output's ids are unique, so nothing downstream could see that
    the question had been asked.

    Last-one-wins is a decision and it is not this program's to make.
    """

    @pytest.fixture
    def source(self, tmp_path):
        return build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(
                '<item id="dup" href="first.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="dup" href="second.xhtml" media-type="application/xhtml+xml"/>'
                + NAV_ITEM,
                '<itemref idref="dup"/>'),
            "OEBPS/nav.xhtml": page(
                '<nav epub:type="toc"><ol><li><a href="first.xhtml">c</a></li></ol></nav>'),
            "OEBPS/first.xhtml": page("<p>PIERWSZY</p>"),
            "OEBPS/second.xhtml": page("<p>DRUGI</p>"),
        })

    def test_the_ambiguity_stops_the_rebuild(self, source, tmp_path):
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.BLOCKED
        assert result.output_path is None

    def test_both_candidates_are_named(self, source, tmp_path):
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        finding = next(
            f for f in result.report.findings if f.rule == "reader.manifest-id-duplicated"
        )
        assert finding.values["id"] == "dup"
        assert "first.xhtml" in finding.values["first"]
        assert "second.xhtml" in finding.values["second"]


class TestF014ARemoteItemWithABadFallback:
    """**Measured on 0.2.19:** `AttributeError: 'RemoteResource' object has no
    attribute 'path'`, raised out of the reader. A traceback where a finding
    belonged, and in a batch, the end of the batch."""

    def test_it_is_a_finding_and_not_a_traceback(self, tmp_path):
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(
                '<item id="r" href="https://example.test/a.mp4" media-type="video/mp4" '
                'fallback="nope"/>' + CHAPTER_ITEM + NAV_ITEM,
                '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": page("<p>x</p>"),
        })
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.SUCCEEDED
        assert "reader.dangling-reference" in rules_of(result)


class TestF009ADocumentKeepsItsOwnLanguage:
    """**Measured on 0.2.19:** a chapter declaring `lang="fr"` in a book whose
    package says `en` came out declaring `en`, on both spellings. With it went
    the hyphenation, the speech synthesiser's accent and the dictionary.

    A bilingual edition is not an error to be tidied.
    """

    def test_the_document_is_believed(self, tmp_path):
        result = rebuild(simple(tmp_path / "in.epub", body="<p>Bonjour</p>", lang="fr"),
                         str(tmp_path / "out.epub"), Policy.preset("preserve"))
        found = re.findall(r'\b(?:xml:)?lang="([^"]+)"', read(result.output_path, "chapter.xhtml"))
        assert set(found[:2]) == {"fr"}
        assert "xhtml.document-language-kept" in rules_of(result)

    def test_a_document_that_says_nothing_takes_the_publications_language(self, tmp_path):
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml">'
                "<head><title>t</title></head><body><p>x</p></body></html>"
            ).encode(),
        })
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert 'lang="en"' in read(result.output_path, "chapter.xhtml")
        assert "xhtml.document-language-kept" not in rules_of(result)

    def test_the_two_spellings_are_made_to_agree(self, tmp_path):
        """A document saying `lang="fr" xml:lang="en"` is one each reading
        system resolves by picking, and they do not all pick the same."""
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="fr" xml:lang="de">'
                "<head><title>t</title></head><body><p>x</p></body></html>"
            ).encode(),
        })
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        found = re.findall(r'\b(?:xml:)?lang="([^"]+)"', read(result.output_path, "chapter.xhtml"))
        assert len(set(found[:2])) == 1


class TestF005APackagePathThisMayNotWrite:
    """**Measured on 0.2.19:** `content_dir='../evil&dir'` and
    `package_name='p"q.opf'` produced four archive members beginning `../`, a
    `container.xml` lxml refuses to parse, and an internal verifier that
    pronounced the archive good.

    `Policy` is public API. Nothing in the CLI or the GUI can reach this, and
    that is not a reason to accept it.
    """

    def test_the_policy_refuses_at_construction(self):
        with pytest.raises(ValueError, match="content_dir"):
            Policy(content_dir="../evil")
        with pytest.raises(ValueError, match="package_name"):
            Policy(package_name='p"q.opf')

    def test_the_writer_refuses_a_field_set_afterwards(self, tmp_path):
        """A dataclass field assigned after construction never sees
        `__post_init__`, and that is the ordinary way a caller adjusts one
        setting — it is how the original reproduction was written."""
        policy = Policy.preset("preserve")
        policy.content_dir = "../evil&dir"
        with pytest.raises(ValueError):
            rebuild(simple(tmp_path / "in.epub"), str(tmp_path / "out.epub"), policy)

    def test_an_ordinary_layout_still_passes(self):
        Policy(content_dir="OEBPS", package_name="content.opf")
        Policy(content_dir="", package_name="content.opf")

    def test_the_verifier_now_reads_the_container_it_wrote(self, tmp_path):
        """"Has a container.xml" was the whole check. It has to parse, and the
        rootfile it names has to be in the archive."""
        from epubforge.writer import _verify_container

        broken = tmp_path / "broken.epub"
        with zipfile.ZipFile(broken, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr("META-INF/container.xml", CONTAINER.replace(b"OEBPS", b"a&b"))
        with pytest.raises(OSError, match="well-formed|missing rootfile"):
            _verify_container(str(broken))


class TestF008WebPIsACoreMediaType:
    """**Measured on 0.2.19:** a two-frame animated WebP came out a one-frame
    PNG. Two defects in one: EPUB 3.3 lists `image/webp` among the core media
    types, so nothing needed converting; and the conversion that was not needed
    decoded one frame and saved it.

    Not a reading of the prose. The EPUBCheck this repository ships validates a
    book holding a bare `image/webp` with no fallback and reports zero errors
    under EPUB 3.3 rules — and a foreign resource used without a fallback is an
    error, so the validator saying nothing is the validator saying it is core.
    """

    def test_webp_is_in_the_core_set(self):
        assert "image/webp" in CORE_IMAGE_TYPES

    @staticmethod
    def _animated(fmt: str) -> bytes:
        Image = pytest.importorskip("PIL.Image")
        frames = [Image.new("RGB", (8, 8), colour) for colour in ("red", "blue")]
        buffer = io.BytesIO()
        frames[0].save(buffer, format=fmt, save_all=True, append_images=frames[1:],
                       duration=200, loop=0)
        return buffer.getvalue()

    def book_with(self, tmp_path, name: str, media_type: str, data: bytes) -> str:
        return build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(
                CHAPTER_ITEM + NAV_ITEM
                + f'<item id="i" href="{name}" media-type="{media_type}"/>',
                '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": page(f'<p><img src="{name}" alt="a"/></p>'),
            f"OEBPS/{name}": data,
        })

    def test_an_animated_webp_comes_out_animated(self, tmp_path):
        Image = pytest.importorskip("PIL.Image")
        source = self.book_with(tmp_path, "anim.webp", "image/webp", self._animated("WEBP"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if "anim" in n)
            assert name.endswith(".webp"), "a core media type is not transcoded"
            image = Image.open(io.BytesIO(archive.read(name)))
            assert getattr(image, "n_frames", 1) == 2

    def test_an_animation_in_a_foreign_format_is_kept_rather_than_flattened(self, tmp_path):
        """A moving picture cannot be converted to a still one and called
        converted. TIFF is not core, so this is the transcode path saying no."""
        Image = pytest.importorskip("PIL.Image")
        source = self.book_with(tmp_path, "anim.tiff", "image/tiff", self._animated("TIFF"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "image.animation-kept" in rules_of(result)
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if "anim" in n)
            assert Image.open(io.BytesIO(archive.read(name))).n_frames == 2

    def test_a_still_foreign_image_is_still_converted(self, tmp_path):
        Image = pytest.importorskip("PIL.Image")
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(buffer, format="BMP")
        source = self.book_with(tmp_path, "still.bmp", "image/bmp", buffer.getvalue())
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "image.transcoded" in rules_of(result)


class TestF011EveryTitleSurvives:
    """**Measured on 0.2.19:** a package with three untagged `dc:title` elements
    came out with two. The first stayed, the second became the subtitle, the
    third stopped existing — and the finding said "3 collapsed", which reads
    like an accounting of where they went."""

    def test_the_third_title_is_still_there(self, tmp_path):
        result = rebuild(
            simple(tmp_path / "in.epub", metadata="<dc:title>Drugi</dc:title><dc:title>Trzeci</dc:title>"),
            str(tmp_path / "out.epub"), Policy.preset("preserve"))
        titles = re.findall(r"<dc:title[^>]*>([^<]*)</dc:title>", read(result.output_path, ".opf"))
        assert titles == ["T", "Drugi", "Trzeci"]

    def test_the_first_two_still_mean_what_they_meant(self, tmp_path):
        result = rebuild(
            simple(tmp_path / "in.epub", metadata="<dc:title>Drugi</dc:title><dc:title>Trzeci</dc:title>"),
            str(tmp_path / "out.epub"), Policy.preset("preserve"))
        opf_text = read(result.output_path, ".opf")
        assert '<meta refines="#title" property="title-type">main</meta>' in opf_text
        assert '<meta refines="#subtitle" property="title-type">subtitle</meta>' in opf_text


class TestF023TheOnixCodeIsACode:
    """**Measured on 0.2.19:** `scheme="onix:codelist5">ISBN<`. The attribute
    announces ONIX Code List 5, whose members are two-digit codes, and then says
    something that is not in it. Valid XML, valid EPUB, and unreadable by the
    only kind of software that asks the question."""

    def code_for(self, tmp_path, identifier: str) -> str:
        result = rebuild(simple(tmp_path / "in.epub", identifier=identifier),
                         str(tmp_path / "out.epub"), Policy.preset("preserve"))
        found = re.search(
            r'property="identifier-type"[^>]*scheme="([^"]+)"[^>]*>([^<]*)<',
            read(result.output_path, ".opf"))
        assert found, "no identifier-type refinement was emitted"
        return f"{found.group(1)}:{found.group(2)}"

    def test_isbn_13(self, tmp_path):
        assert self.code_for(tmp_path, "urn:isbn:9788324631766") == "onix:codelist5:15"

    def test_isbn_10_is_a_different_code_in_the_same_list(self, tmp_path):
        assert self.code_for(tmp_path, "urn:isbn:8324631763") == "onix:codelist5:02"

    def test_a_uuid_claims_no_vocabulary_at_all(self, tmp_path):
        result = rebuild(simple(tmp_path / "in.epub"), str(tmp_path / "out.epub"),
                         Policy.preset("preserve"))
        assert "identifier-type" not in read(result.output_path, ".opf")


class TestF009TheTextStillGetsAVote:
    """The other half of F-009, and the public corpus taught it within the hour
    of the fix landing.

    "Believe the document" is not the rule either. Three Polish Project
    Gutenberg books wrap Polish text in `<html lang="en">` because the
    boilerplate says `en` and nobody edits it — and believing that hands a
    text-to-speech engine an English voice for *Pan Tadeusz*.

    So the rule is the one this program already applies to the package's own
    declaration, one level down: the text decides. Measured on the six public
    books, it separates them exactly — a 233 946-character Polish novel
    declaring `en` is corrected, and the 18 726-character English Gutenberg
    licence sitting beside it in the same book keeps `en`.
    """

    POLISH = "Litwo, ojczyzno moja, ty jesteś jak zdrowie, ile cię trzeba cenić. " * 20
    ENGLISH = "The Project Gutenberg licence applies to copying and distributing. " * 20

    def language_of(self, tmp_path, body: str, declared: str) -> str:
        result = rebuild(simple(tmp_path / "in.epub", body=body, lang=declared),
                         str(tmp_path / "out.epub"), Policy.preset("preserve"))
        return re.search(r'<html[^>]*\blang="([^"]+)"',
                         read(result.output_path, "chapter.xhtml")).group(1)

    def test_polish_prose_declaring_english_is_corrected(self, tmp_path):
        assert self.language_of(tmp_path, f"<p>{self.POLISH}</p>", "en") == "pl"

    def test_english_prose_in_a_polish_book_keeps_english(self, tmp_path):
        assert self.language_of(tmp_path, f"<p>{self.ENGLISH}</p>", "en") == "en"

    def test_a_language_with_no_test_for_it_is_believed(self, tmp_path):
        """There is no letter-frequency proof for French against English, and
        that asymmetry is honest rather than provisional: a wrong `fr` costs a
        reader far less than a wrong `en` on Polish text costs a listener."""
        assert self.language_of(tmp_path, "<p>Bonjour, monsieur. </p>" * 40, "fr") == "fr"

    def test_a_short_page_is_arithmetic_and_not_evidence(self, tmp_path):
        """A 90-character wrapper page is what those three Gutenberg books
        actually declare `en` on."""
        assert self.language_of(tmp_path, "<p>Litwo, ojczyzno moja</p>", "en") == "en"
