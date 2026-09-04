"""PDF → EPUB (0.5, D-052): the reader, the stage, the gate, and the corpus.

Two kinds of material. The first is written here by hand — a page is a
content stream of positioned text in Helvetica, which is enough to say where
a paragraph, a heading and a running head come from, and nothing but
`pdfminer.six` is needed to read it back. The second is real typesetting: the
six Gutenberg books printed to PDF by the pinned Chromium, so that lines
break where a layout engine broke them. Those run only when the engine is
named (`EPUBFORGE_RENDER_TESTS=1`, `EPUBFORGE_CHROME`), for the reason the
render tests give: an unpinned engine measures the machine.

No PDF is kept in the repository; everything is made in `tmp_path`.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import zipfile
import zlib

import pytest

from epubforge import fidelity, pdf, render
from epubforge.cli import EXIT_OK, main
from epubforge.decisions import Answer
from epubforge.pipeline import Status, rebuild
from epubforge.policy import PDF_RUNNING_HEADS, Policy
from epubforge.report import Report
from epubforge.typography import canonical

# --------------------------------------------------------------------------
# A PDF writer small enough to read: Helvetica, WinAnsi, one content stream
# per page. `pdfminer` reads it like any other.
# --------------------------------------------------------------------------

PAGE = (612.0, 792.0)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: pathlib.Path, pages: list[list[tuple[float, float, float, str]]],
             *, title: str = "", author: str = "", language: str = "",
             images: dict[int, list[tuple]] | None = None,
             outline: list[tuple[str, int]] | None = None) -> pathlib.Path:
    """Write *pages*, each a list of ``(x, y, size, text)`` lines, y from the
    page bottom as PDF counts it. *images* puts Flate-compressed RGB pictures
    on a page (by index): ``(x, y, width, height, pixel_width, pixel_height,
    rgb_bytes)``. *outline* is the PDF's bookmarks: ``(title, page_index)``."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    page_ids: list[int] = []
    for index, lines in enumerate(pages):
        drawn = []
        xobjects = []
        for number, (x, y, width, height, pw, ph, rgb) in enumerate((images or {}).get(index, ()), 1):
            packed = zlib.compress(rgb)
            image = add(
                f"<< /Type /XObject /Subtype /Image /Width {pw} /Height {ph} /ColorSpace /DeviceRGB "
                f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(packed)} >>\nstream\n".encode()
                + packed + b"\nendstream"
            )
            xobjects.append(f"/Im{number} {image} 0 R")
            drawn.append(f"q {width} 0 0 {height} {x} {y} cm /Im{number} Do Q\n")
        stream = ("".join(drawn) + "".join(
            f"BT /F1 {size} Tf {x} {y} Td ({_escape(text)}) Tj ET\n" for x, y, size, text in lines
        )).encode("cp1252")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        resources = f"/Font << /F1 {font} 0 R >>"
        if xobjects:
            resources += f" /XObject << {' '.join(xobjects)} >>"
        page_ids.append(add(
            f"<< /Type /Page /Parent PAGES 0 R /MediaBox [0 0 {PAGE[0]} {PAGE[1]}] "
            f"/Resources << {resources} >> /Contents {content} 0 R >>".encode()
        ))
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    for number in page_ids:
        objects[number - 1] = objects[number - 1].replace(b"PAGES 0 R", f"{pages_id} 0 R".encode())
    lang = f" /Lang ({language})" if language else ""
    outlines = ""
    if outline:
        root_id = len(objects) + 1
        item_ids = [root_id + 1 + i for i in range(len(outline))]
        add(f"<< /Type /Outlines /First {item_ids[0]} 0 R /Last {item_ids[-1]} 0 R /Count {len(outline)} >>".encode())
        for i, (label, page_index) in enumerate(outline):
            links = f" /Prev {item_ids[i - 1]} 0 R" if i else ""
            links += f" /Next {item_ids[i + 1]} 0 R" if i + 1 < len(outline) else ""
            add((f"<< /Title ({_escape(label)}) /Parent {root_id} 0 R{links} "
                 f"/Dest [{page_ids[page_index]} 0 R /XYZ 0 {PAGE[1]} 0] >>").encode("cp1252"))
        outlines = f" /Outlines {root_id} 0 R"
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R{lang}{outlines} >>".encode())
    info = add((
        "<< " + (f"/Title ({_escape(title)}) " if title else "")
        + (f"/Author ({_escape(author)}) " if author else "") + ">>"
    ).encode("cp1252"))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))
    return path


def column(lines: list[str], *, top: float = 700.0, size: float = 12.0, pitch: float = 14.0,
           left: float = 72.0) -> list[tuple[float, float, float, str]]:
    """Lines set one under another at a regular pitch. A line given as
    ``("+", text)``-style marker is not needed: pass an indent by prefixing
    the text with ``">"`` and a wider gap by an empty string."""
    out = []
    y = top
    for text in lines:
        if text == "":
            y -= pitch  # an empty slot is a blank line: a gap of two pitches
            continue
        x = left
        if text.startswith(">"):
            x += pdf.INDENT_POINTS + 4
            text = text[1:]
        out.append((x, y, size, text))
        y -= pitch
    return out


THREE_PARAGRAPHS = [
    "The first paragraph runs across three lines of the page and each",
    "of them is set flush with the left edge of the block, as prose is",
    "when nothing new begins.",
    ">The second paragraph starts with an indent, which is how a printer",
    "says so without leaving a blank line.",
    "",
    "The third comes after a blank line, and the reader takes that gap",
    "for what it is.",
]


class Recorder:
    """An asker that writes down what it was asked and answers nothing."""

    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return None

    def groups(self) -> set:
        return {question.group for question in self.asked}


def rebuilt(source: pathlib.Path, tmp_path: pathlib.Path, *, standing: dict | None = None,
            asker=None, **policy):
    settings = Policy.preset(
        "preserve", validate_before_publish="off", render_gate="off", render_sample=0, **policy
    )
    return rebuild(str(source), str(tmp_path / "out.epub"), settings, standing=standing, asker=asker)


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings if finding.rule}


def documents_of(path: str) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist() if name.endswith(".xhtml")
        }


def prose_of(path: str) -> str:
    return " ".join(
        fidelity.document_text(text.encode("utf-8")) or ""
        for name, text in sorted(documents_of(path).items()) if "/nav" not in name and "cover" not in name
    )


# --------------------------------------------------------------------------
# The reader, on pages written here.
# --------------------------------------------------------------------------


class TestTheReader:
    def test_only_a_pdf_extension_is_a_pdf(self):
        assert pdf.is_pdf("book.pdf") and pdf.is_pdf("BOOK.PDF")
        assert not pdf.is_pdf("book.epub") and not pdf.is_pdf("book.pdf.epub")

    def test_a_gap_an_indent_and_a_short_line_each_start_a_paragraph(self, tmp_path):
        source = make_pdf(tmp_path / "three.pdf", [column(THREE_PARAGRAPHS)], title="Three")
        report = Report()
        book = pdf.read_pdf(str(source), report)
        (document,) = [r for r in book.resources.values() if r.path.endswith(".xhtml")]
        text = document.data.decode("utf-8")
        assert text.count("<p>") == 3, text
        assert report.stats["pdf_layout"]["paragraphs"] == 3
        assert "nothing new begins.</p>" in text
        assert "<p>The second paragraph starts with an indent" in text
        assert "<p>The third comes after a blank line" in text

    def test_no_character_of_the_text_layer_is_lost(self, tmp_path):
        source = make_pdf(tmp_path / "three.pdf", [column(THREE_PARAGRAPHS)])
        book = pdf.read_pdf(str(source), Report())
        (document,) = [r for r in book.resources.values() if r.path.endswith(".xhtml")]
        prose = fidelity.document_text(document.data)
        for line in THREE_PARAGRAPHS:
            assert line.lstrip(">") in prose
        assert fidelity.first_character_lost(canonical(pdf.text_of(str(source))), canonical(prose)) == -1

    def test_a_line_set_larger_than_the_body_is_a_heading(self, tmp_path):
        lines = [(72, 720, 12 * pdf.BODY_RATIO_H1 + 1, "Chapter One")]
        lines += column(["Body text that is the most common size on the page.",
                         "More body text so that twelve points wins the census."], top=690)
        lines += [(72, 650, 12 * pdf.BODY_RATIO_H2 + 0.5, "A section inside it")]
        lines += column(["And body again, twice.", "And once more."], top=630)
        source = make_pdf(tmp_path / "heads.pdf", [lines])
        report = Report()
        book = pdf.read_pdf(str(source), report)
        text = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert "<h1>Chapter One</h1>" in text
        assert "<h2>A section inside it</h2>" in text
        assert report.stats["pdf_layout"]["headings"] == 2
        assert report.stats["pdf_layout"]["body_size"] == 12.0

    def test_a_heading_opens_a_section_and_names_it_in_the_toc(self, tmp_path):
        pages = []
        for number in (1, 2):
            lines = [(72, 720, 20.0, f"Chapter {number}")]
            lines += column([f"Prose of chapter {number}, line one.", "Line two of the same.", "Line three."], top=690)
            pages.append(lines)
        book = pdf.read_pdf(str(make_pdf(tmp_path / "two.pdf", pages)), Report())
        assert [item.path for item in book.spine] == ["text/section-0001.xhtml", "text/section-0002.xhtml"]
        assert [point.label for point in book.toc] == ["Chapter 1", "Chapter 2"]

    def test_the_outline_gives_the_documents_and_the_toc_word_for_word(self, tmp_path):
        pages = [column([f"Page {n} of prose, at the body size only,", "so no heading opens anything."], top=600)
                 for n in range(1, 5)]
        source = make_pdf(tmp_path / "outline.pdf", pages, title="Outlined",
                          outline=[("Part One: The Beginning", 0), ("Part Two", 2)])
        report = Report()
        book = pdf.read_pdf(str(source), report)
        assert [point.label for point in book.toc] == ["Part One: The Beginning", "Part Two"]
        assert len(book.spine) == 2
        second = book.resources[book.spine[1].path].data.decode()
        assert "Page 3 of prose" in second and "Page 2 of prose" not in second
        used = next(f for f in report.findings if f.rule == "pdf.outline-used")
        assert used.values == {"count": 2, "unresolved": 0}
        assert report.stats["pdf_layout"]["headings"] == 0

    def test_running_heads_are_marked_and_kept_not_removed(self, tmp_path):
        pages = []
        for number in range(1, 7):
            lines = [(72, 760, 10.0, "THE BOOK OF PAGES")]
            lines += column([f"Page {number} carries ordinary prose in its body,",
                             "two lines of it, set at the body size."], top=600)
            lines += [(300, 30, 10.0, str(number))]
            pages.append(lines)
        report = Report()
        book = pdf.read_pdf(str(make_pdf(tmp_path / "heads.pdf", pages)), report)
        assert report.stats["pdf_layout"]["running_heads"] == 12
        assert any(f.rule == "pdf.running-heads-found" for f in report.findings)
        text = "".join(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert text.count(f'<p class="{pdf.RUNNING_HEAD_CLASS}">') == 12
        assert "THE BOOK OF PAGES" in text  # kept in the text until somebody answers

    def test_a_head_on_every_left_page_and_another_on_every_right_is_found(self, tmp_path):
        pages = []
        for number in range(1, 11):
            head = "A. WRITER" if number % 2 == 0 else "THE BOOK OF PAGES"
            lines = [(72, 760, 10.0, head)]
            lines += column([f"Page {number} carries ordinary prose in its body,",
                             "two lines of it, set at the body size."], top=600)
            pages.append(lines)
        report = Report()
        pdf.read_pdf(str(make_pdf(tmp_path / "verso-recto.pdf", pages)), report)
        assert report.stats["pdf_layout"]["running_heads"] == 10

    def test_a_line_that_repeats_on_a_few_pages_is_prose(self, tmp_path):
        pages = []
        for number in range(1, 11):
            lines = column([f"Page {number} carries ordinary prose in its body,",
                            "two lines of it, set at the body size."], top=600)
            if number in (2, 5):
                lines.append((72, 760, 10.0, "An epigraph line at the top, twice"))
            pages.append(lines)
        report = Report()
        pdf.read_pdf(str(make_pdf(tmp_path / "twice.pdf", pages)), report)
        assert report.stats["pdf_layout"]["running_heads"] == 0

    def test_metadata_comes_from_the_info_dictionary(self, tmp_path):
        source = make_pdf(tmp_path / "meta.pdf", [column(THREE_PARAGRAPHS)],
                          title="A Title", author="Some Author", language="pl")
        book = pdf.read_pdf(str(source), Report())
        assert book.metadata.title == "A Title"
        assert [creator.name for creator in book.metadata.creators] == ["Some Author"]
        assert book.metadata.language == "pl"
        assert book.metadata.identifiers and book.metadata.identifiers[0].value.startswith("urn:uuid:")
        # The same file names the same book twice.
        again = pdf.read_pdf(str(source), Report())
        assert again.metadata.identifiers[0].value == book.metadata.identifiers[0].value

    def test_an_image_only_pdf_is_refused_with_the_reason(self, tmp_path):
        PIL = pytest.importorskip("PIL.Image")
        source = tmp_path / "scan.pdf"
        PIL.new("RGB", (400, 600), (250, 250, 250)).save(source, "PDF")
        report = Report()
        with pytest.raises(Exception):
            pdf.read_pdf(str(source), report)
        assert [f.rule for f in report.findings] == ["pdf.no-text-layer"]

    def test_a_flate_image_comes_along_as_png_where_it_stood(self, tmp_path):
        pytest.importorskip("PIL.Image")
        red = bytes([200, 30, 30]) * (40 * 30)
        lines = column(["A line above the picture, and another line of prose", "to make a paragraph."], top=700)
        lines += column(["And a paragraph below it."], top=400)
        source = make_pdf(tmp_path / "picture.pdf", [lines], images={0: [(72, 450, 120, 90, 40, 30, red)]})
        report = Report()
        book = pdf.read_pdf(str(source), report)
        pictures = [r for r in book.resources.values() if r.media_type == "image/png"]
        assert len(pictures) == 1 and pictures[0].data.startswith(b"\x89PNG")
        assert report.stats["pdf_layout"]["images"] == 1
        text = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        above = text.index("above the picture")
        image = text.index("<img ")
        below = text.index("below it")
        assert above < image < below
        assert 'alt=""' in text  # nothing invented: the image question decides


# --------------------------------------------------------------------------
# The stage, through the whole pipeline.
# --------------------------------------------------------------------------


def book_with_heads(tmp_path: pathlib.Path) -> pathlib.Path:
    pages = []
    for number in range(1, 7):
        lines = [(72, 760, 10.0, "THE BOOK OF PAGES")]
        lines += column([f"Page {number} carries ordinary prose in its body,",
                         "two lines of it, set at the body size."], top=600)
        lines += [(300, 30, 10.0, str(number))]
        pages.append(lines)
    return make_pdf(tmp_path / "heads.pdf", pages, title="The Book of Pages", author="A. Writer")


class TestThePipeline:
    def test_a_pdf_goes_through_the_pipeline_and_comes_out_an_epub(self, tmp_path):
        result = rebuilt(book_with_heads(tmp_path), tmp_path)
        assert result.status == Status.SUCCEEDED, [f for f in result.report.findings if f.level.name == "ERROR"]
        assert "pdf.converted" in rules_of(result)
        with zipfile.ZipFile(result.output_path) as archive:
            assert archive.read("mimetype") == b"application/epub+zip"
        assert "Page 3 carries ordinary prose" in prose_of(result.output_path)

    def test_without_an_answer_the_running_heads_stay(self, tmp_path):
        recorder = Recorder()
        result = rebuilt(book_with_heads(tmp_path), tmp_path, asker=recorder)
        assert "pdf.running-heads-kept" in rules_of(result)
        assert "pdf.running-heads-removed" not in rules_of(result)
        prose = prose_of(result.output_path)
        assert prose.count("THE BOOK OF PAGES") == 6
        # The page's order, kept: the number, then the next page's head, then
        # the paragraph's second half — as a reader of the PDF meets them.
        assert "at the body size. 1 THE BOOK OF PAGES Page 2 carries" in prose
        markup = "".join(documents_of(result.output_path).values())
        assert pdf.RUNNING_HEAD_CLASS not in markup and pdf.CONTINUED_CLASS not in markup
        assert "pdf:running-heads" in recorder.groups()
        assert result.report.stats["questions_unanswered"] >= 1

    def test_the_answer_remove_takes_them_out_and_the_gate_still_holds(self, tmp_path):
        standing = {"pdf:running-heads": Answer(option="remove")}
        result = rebuilt(book_with_heads(tmp_path), tmp_path, standing=standing)
        assert result.status == Status.SUCCEEDED
        assert "pdf.running-heads-removed" in rules_of(result)
        prose = prose_of(result.output_path)
        assert "THE BOOK OF PAGES" not in prose
        assert "Page 6 carries ordinary prose" in prose
        # The paragraph the heads had cut into six is one paragraph again.
        assert "at the body size. Page 2 carries" in prose
        section = next(text for name, text in documents_of(result.output_path).items() if "section" in name)
        assert section.count("<p") == 1, section
        assert pdf.CONTINUED_CLASS not in section
        removed = [c for c in result.report.changes if c.rule == "pdf.running-heads-removed"]
        assert len(removed) == 1 and not removed[0].reversible

    def test_the_policy_answers_for_a_batch(self, tmp_path):
        assert PDF_RUNNING_HEADS == ("ask", "keep", "remove")
        recorder = Recorder()
        kept = rebuilt(book_with_heads(tmp_path), tmp_path / "keep", pdf_running_heads="keep", asker=recorder)
        assert "pdf.running-heads-kept" in rules_of(kept)
        assert "pdf:running-heads" not in recorder.groups()
        gone = rebuilt(book_with_heads(tmp_path), tmp_path / "remove", pdf_running_heads="remove")
        assert "pdf.running-heads-removed" in rules_of(gone)
        assert "THE BOOK OF PAGES" not in prose_of(gone.output_path)

    def test_the_language_is_proposed_and_applied_only_on_a_word(self, tmp_path):
        source = make_pdf(tmp_path / "en.pdf", [column(THREE_PARAGRAPHS)], title="Three")
        recorder = Recorder()
        asked = rebuilt(source, tmp_path / "asked", asker=recorder)
        question = next(q for q in recorder.asked if q.group == "pdf:language")
        assert question.subject == "en"
        assert "pdf.language-default" in rules_of(asked)
        answered = rebuilt(source, tmp_path / "answered", standing={"pdf:language": Answer(option="set")})
        assert "pdf.language-set" in rules_of(answered)
        assert answered.book.metadata.language == "en"

    def test_a_language_the_pdf_declares_is_not_asked_about(self, tmp_path):
        source = make_pdf(tmp_path / "pl.pdf", [column(THREE_PARAGRAPHS)], language="pl")
        recorder = Recorder()
        result = rebuilt(source, tmp_path, asker=recorder)
        assert "pdf:language" not in recorder.groups()
        assert result.book.metadata.language == "pl"

    def test_the_command_line_takes_a_pdf_and_the_flag(self, tmp_path, capsys):
        source = book_with_heads(tmp_path)
        out = tmp_path / "out"
        code = main([
            "build", str(source), "-o", str(out / "book.epub"), "--gate", "off", "--render-gate", "off",
            "--pdf-running-heads", "remove",
        ])
        assert code == EXIT_OK, capsys.readouterr()
        written = list(out.glob("*.epub"))
        assert len(written) == 1
        assert "THE BOOK OF PAGES" not in prose_of(str(written[0]))

    def test_an_image_only_pdf_is_refused_before_anything_is_written(self, tmp_path):
        PIL = pytest.importorskip("PIL.Image")
        source = tmp_path / "scan.pdf"
        PIL.new("RGB", (400, 600), (250, 250, 250)).save(source, "PDF")
        result = rebuilt(source, tmp_path)
        assert result.status in (Status.FAILED, Status.BLOCKED)
        assert result.output_path is None
        assert "pdf.no-text-layer" in rules_of(result)
        assert not (tmp_path / "out.epub").exists()


# --------------------------------------------------------------------------
# Real typesetting: the Gutenberg corpus printed by the pinned Chromium.
# --------------------------------------------------------------------------

CORPUS = pathlib.Path(__file__).parent / "corpus_gutenberg"
_ASKED_FOR = os.environ.get("EPUBFORGE_RENDER_TESTS") == "1"

# `renders` hands the real browser discovery back (conftest hides it from
# every other test); the skip then asks the same question the render tests ask.
engine = pytest.mark.renders


def _no_engine() -> bool:
    return not _ASKED_FOR or render.find_renderer() is None


def _printer_or_skip() -> pathlib.Path:
    if _no_engine():
        pytest.skip("set EPUBFORGE_RENDER_TESTS=1 and name a Chromium: the corpus PDFs are printed by it")
    return pathlib.Path(render.find_renderer())


def print_to_pdf(epub: pathlib.Path, workdir: pathlib.Path, *, running_heads: bool) -> pathlib.Path:
    """One PDF for the whole book: the spine documents concatenated into one
    page and printed once, so no merging tool is needed on any platform."""
    from epubforge.reader import read_epub

    unpacked = workdir / epub.stem
    with zipfile.ZipFile(epub) as archive:
        archive.extractall(unpacked)
    book = read_epub(str(epub), Report())
    # Spine paths are archive paths; the combined page sits beside the first
    # document so the book's own stylesheet and image links still resolve.
    root = unpacked / posixpath_dir(book.spine[0].path)
    bodies = []
    for item in book.spine:
        document = (unpacked / item.path).read_text("utf-8")
        start = document.find("<body")
        start = document.find(">", start) + 1
        end = document.rfind("</body>")
        bodies.append(f'<div style="page-break-before: always">{document[start:end]}</div>')
    combined = root / "__all__.xhtml"
    combined.write_text(
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/>'
        f"<title>{epub.stem}</title></head><body>{''.join(bodies)}</body></html>", "utf-8"
    )
    target = workdir / f"{epub.stem}{'-heads' if running_heads else ''}.pdf"
    command = [
        str(_printer_or_skip()), "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--print-to-pdf={target}", combined.resolve().as_uri(),
    ]
    if not running_heads:
        command.insert(4, "--no-pdf-header-footer")
    subprocess.run(command, check=True, capture_output=True, timeout=600)
    assert target.exists()
    return target


def posixpath_dir(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def folded(text: str) -> str:
    """What the two sides are compared in. Chromium writes `text-transform`
    into the text layer, so case is folded; a line break in the PDF is a
    space, and a space is a space."""
    return " ".join(canonical(text).casefold().split())


@engine
@pytest.mark.parametrize("epub", sorted(CORPUS.glob("*.epub")), ids=lambda p: p.stem)
def test_the_corpus_survives_the_printer_and_comes_back(epub, tmp_path):
    source = print_to_pdf(epub, tmp_path, running_heads=False)
    result = rebuilt(source, tmp_path)
    assert result.status == Status.SUCCEEDED, [f for f in result.report.findings if f.level.name == "ERROR"]
    assert "pdf.converted" in rules_of(result)
    original = folded(fidelity.spine_text_of(epub))
    converted = folded(prose_of(result.output_path))
    lost = fidelity.first_character_lost(original.replace(" ", ""), converted.replace(" ", ""))
    assert lost == -1, f"first character lost at {lost}: {original[max(0, lost - 40):lost + 40]!r}"
    layout = result.report.stats["pdf_layout"]
    assert layout["paragraphs"] > 100
    assert layout["headings"] >= 1


@engine
def test_chromiums_own_running_heads_are_found_and_removed_on_the_answer(tmp_path):
    epub = CORPUS / "king-arthur-and-the-knights-of-the-r.epub"
    source = print_to_pdf(epub, tmp_path, running_heads=True)
    result = rebuilt(source, tmp_path, standing={"pdf:running-heads": Answer(option="remove")})
    assert result.status == Status.SUCCEEDED
    layout = result.report.stats["pdf_layout"]
    assert layout["running_heads"] >= 2 * layout["pages"] * pdf.RUNNING_HEAD_SHARE
    assert "pdf.running-heads-removed" in rules_of(result)
    prose = prose_of(result.output_path)
    assert "file://" not in prose
    original = folded(fidelity.spine_text_of(epub)).replace(" ", "")
    assert fidelity.first_character_lost(original, folded(prose).replace(" ", "")) == -1
