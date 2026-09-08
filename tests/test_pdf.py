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

import math
import os
import pathlib
import re
import subprocess
import zipfile
import zlib

import pytest

from epubforge import fidelity, pdf, render
from epubforge.cli import EXIT_OK, main
from epubforge.decisions import Answer
from epubforge.pipeline import Status, rebuild
from epubforge.policy import PDF_RUNNING_HEADS, Policy
from epubforge.report import Level, Report
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
             outline: list[tuple[str, int]] | None = None,
             forms: dict[int, list[list[tuple[float, float, float, str]]]] | None = None,
             strokes: dict[int, list[tuple[float, float, float, str]]] | None = None) -> pathlib.Path:
    """Write *pages*, each a list of ``(x, y, size, text)`` lines, y from the
    page bottom as PDF counts it. *images* puts Flate-compressed RGB pictures
    on a page (by index): ``(x, y, width, height, pixel_width, pixel_height,
    rgb_bytes)``. *outline* is the PDF's bookmarks: ``(title, page_index)``.
    *strokes* draws lines on a page: ``(x0, y0, x1, y1)`` each — vector artwork,
    which the reader sees as a drawing and cannot carry."""
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
        # *forms*: lines drawn through a Form XObject — a list of forms per
        # page, each a list of ``(x, y, size, text)``. The construct of EF-087,
        # where a reader walking lines saw nothing at all.
        for number, form_lines in enumerate((forms or {}).get(index, ()), 1):
            body = "".join(
                f"BT /F1 {size} Tf {x} {y} Td ({_escape(text)}) Tj ET\n"
                for x, y, size, text in form_lines
            ).encode("cp1252")
            form = add(
                f"<< /Type /XObject /Subtype /Form /BBox [0 0 {PAGE[0]} {PAGE[1]}] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> /Length {len(body)} >>\nstream\n".encode()
                + body + b"\nendstream"
            )
            xobjects.append(f"/Fm{number} {form} 0 R")
            drawn.append(f"q /Fm{number} Do Q\n")
        painted = "".join(
            f"{x0} {y0} m {x1} {y1} l S\n" for x0, y0, x1, y1 in (strokes or {}).get(index, ())
        )
        stream = ("".join(drawn) + painted + "".join(
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
        # An entry is ``(title, page_index)`` at the top level, or
        # ``(title, page_index, level)`` — the levels build the real tree of
        # `/First`, `/Last` and `/Parent` that a publisher's outline has.
        items = [(entry[0], entry[1], entry[2] if len(entry) > 2 else 1) for entry in outline]
        root_id = len(objects) + 1
        item_ids = [root_id + 1 + i for i in range(len(items))]
        parents: list[int | None] = []
        open_at: list[int] = []
        for index, (_, _, level) in enumerate(items):
            while open_at and items[open_at[-1]][2] >= level:
                open_at.pop()
            parents.append(open_at[-1] if open_at else None)
            open_at.append(index)
        family: dict = {}
        for index, parent in enumerate(parents):
            family.setdefault(parent, []).append(index)
        roots = family[None]
        add(f"<< /Type /Outlines /First {item_ids[roots[0]]} 0 R "
            f"/Last {item_ids[roots[-1]]} 0 R /Count {len(items)} >>".encode())
        for index, (label, page_index, _) in enumerate(items):
            siblings = family[parents[index]]
            at = siblings.index(index)
            links = f" /Prev {item_ids[siblings[at - 1]]} 0 R" if at else ""
            links += f" /Next {item_ids[siblings[at + 1]]} 0 R" if at + 1 < len(siblings) else ""
            mine = family.get(index, [])
            if mine:
                links += (f" /First {item_ids[mine[0]]} 0 R /Last {item_ids[mine[-1]]} 0 R "
                          f"/Count {len(mine)}")
            parent_id = root_id if parents[index] is None else item_ids[parents[index]]
            add((f"<< /Title ({_escape(label)}) /Parent {parent_id} 0 R{links} "
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


def _spiral(x: float, y: float, size: float) -> list:
    """Strokes enough to be a drawing: many short ones, piled on one another,
    which is what artwork lays down and a rule under a heading does not."""
    out = []
    for step in range(200):
        angle = step / 8.0
        radius = size * step / 200.0
        out.append((x, y, x + radius * math.cos(angle), y + radius * math.sin(angle)))
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


class Recommending:
    """An asker that takes the recommended option every time."""

    def ask(self, question):
        return Answer(option=question.recommended)


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

    def test_a_word_broken_at_a_line_end_comes_back_with_its_hyphen_and_no_space(self, tmp_path):
        """The typesetter's line-end hyphen: `prze-` at the end of a line and
        `konaniem` at the start of the next is one word broken, not two
        words. Joined with a space it would never reach the hyphen stage,
        whose candidates are hyphens *inside* a word; joined without one it
        is exactly the shape a converter leaves in an EPUB, and the stage
        asks about it with its dictionary. The hyphen itself stays here —
        removing it is that stage's question (D-052). An en dash at a line
        end is dialogue, not a broken word, and keeps its space."""
        lines = column(["Nieprawdopodobne prze-", "konaniem doborowym wspominal —",
                        "powiedzial. Czarno-", "czerwone flagi."])
        source = make_pdf(tmp_path / "hyphen.pdf", [lines])
        book = pdf.read_pdf(str(source), Report())
        prose = fidelity.document_text(next(r.data for r in book.resources.values() if r.path.endswith(".xhtml")))
        assert "prze-konaniem" in prose
        assert "wspominal — powiedzial" in prose
        assert "Czarno-czerwone" in prose
        assert "prze-konaniem" in pdf.text_of(str(source))
        assert fidelity.first_character_lost(canonical(pdf.text_of(str(source))), canonical(prose)) == -1

    @pytest.mark.skipif(not __import__("epubforge.dictionaries", fromlist=["available"]).available("pl_PL"),
                        reason="needs the pl_PL dictionary (dictionaries/ is not in git)")
    def test_a_line_end_break_is_evidence_the_hyphen_stage_uses(self, tmp_path):
        """`nie-` is a word, so `nie-prawdopodobne` inside an EPUB could be a
        compound and stays a question nobody recommends joining. At a PDF
        line end the reader knows the typesetter broke it, and the joined
        form is in the dictionary: confirmed, recommended to join. Measured
        on the corpus typeset with pyphen: without this, 22–30 % of the
        breaks in the Polish books stayed in the text."""
        lines = column(["Zdarzenie zupelnie nie-", "prawdopodobne i ciekawe.", "Drugie zdanie o czyms innym."])
        source = make_pdf(tmp_path / "break.pdf", [lines], language="pl")
        report = Report()
        pdf.read_pdf(str(source), report)
        assert "nie-prawdopodobne" in report.stats["pdf_line_end_words"]
        result = rebuilt(source, tmp_path, asker=Recommending())
        assert result.output_path
        prose = prose_of(result.output_path)
        assert "nieprawdopodobne" in prose and "nie-prawdopodobne" not in prose
        assert "hyphens.joined" in rules_of(result)

    @pytest.mark.skipif(not __import__("epubforge.dictionaries", fromlist=["available"]).available("en_US"),
                        reason="needs the en_US dictionary (dictionaries/ is not in git)")
    def test_the_authors_own_hyphen_survives_a_line_break_at_it(self, tmp_path):
        """DROGA 6.12. `to-day` is how a book from 1890 spells it, and the
        typesetter breaking a line there does not make the hyphen a
        converter's — but the dictionary knows `today`, so it was joined,
        and the acceptance measurement lost the same word in every run.

        The reader now counts the breaks: this page breaks `to-day` once and
        writes it twice more mid-line, so the book itself says the hyphen is
        the author's. `remem-brance` on the same page, broken once and never
        written whole, is still joined — the count is what separates them,
        not the shape."""
        lines = column([
            "He came to-day and said that to-",
            "day was the day of it all, and remem-",
            "brance of it stayed with him to-day.",
        ])
        source = make_pdf(tmp_path / "today.pdf", [lines], language="en")
        report = Report()
        pdf.read_pdf(str(source), report)
        breaks = report.stats["pdf_line_end_words"]
        assert breaks["to-day"] == 1 and breaks["remem-brance"] == 1
        result = rebuilt(source, tmp_path, asker=Recommending())
        assert result.output_path
        prose = prose_of(result.output_path)
        assert prose.count("to-day") == 3, prose
        assert "today" not in prose.replace("to-day", "")
        assert "remembrance" in prose and "remem-brance" not in prose

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

    def test_the_whole_outline_becomes_the_table_of_contents(self, tmp_path):
        """The documents come from the outline's top level, because a document
        is what a reading system loads whole. The table of contents does not:
        the owner's manual has 125 outline entries, all of them resolving to a
        page, and used to arrive with **ten** nav points — the other 115 were
        the ones a person uses to find "6.6.4 Odkamienianie" without reading
        the chapter.
        """
        pages = [column([f"Page {n} of prose, at the body size only,", "so no heading opens anything."], top=600)
                 for n in range(1, 7)]
        source = make_pdf(tmp_path / "deep.pdf", pages, title="Deep", outline=[
            ("1 First part", 0, 1),
            ("1.1 Its first section", 0, 2),
            ("1.2 Its second section", 1, 2),
            ("1.2.1 A subsection", 2, 3),
            ("2 Second part", 3, 1),
            ("2.1 One section of it", 4, 2),
        ])
        report = Report()
        book = pdf.read_pdf(str(source), report)
        assert [point.label for point in book.toc] == ["1 First part", "2 Second part"]
        assert [child.label for child in book.toc[0].children] == ["1.1 Its first section", "1.2 Its second section"]
        assert [deep.label for deep in book.toc[0].children[1].children] == ["1.2.1 A subsection"]
        assert report.stats["pdf_layout"]["navigation_entries"] == 6
        # Every entry lands on an element, not on the top of a document.
        assert all("#" in point.target for root in book.toc for point in root.walk())
        deepest = book.toc[0].children[1].children[0]
        document = book.resources[deepest.target_path].data.decode()
        assert deepest.target.split("#", 1)[1] in document
        # These six pages of prose run into one paragraph each side of the
        # section break, so the entries for pages 2 and 3 point at the
        # paragraph their page begins in. That is what is true of them.
        assert deepest.target == "text/section-0001.xhtml#pdf-page-0001"
        assert book.toc[1].target == "text/section-0002.xhtml#pdf-page-0004"

    def test_a_line_of_figures_set_large_is_not_a_heading(self, tmp_path):
        """Measured on the owner's manual: "set larger than the body" promoted
        74 lines there and not one was a heading — a legend's markers, a
        table's ticks and figures, a quantity. A title is mostly letters; those
        are not, and a roman numeral standing alone still is."""
        lines = [(72, 740, 20.0, "I."), (72, 715, 20.0, "Rozdzial pierwszy")]
        lines += [(72, 690, 14.0, "A6."), (200, 690, 14.0, "B1."),
                  (72, 665, 14.0, "0,5 L"), (200, 665, 14.0, "3 1 4"), (330, 665, 14.0, "+")]
        lines += column(["Prose of the chapter at the body size, which is", "ten points here."], top=630, size=10)
        book = pdf.read_pdf(str(make_pdf(tmp_path / "shapes.pdf", [lines])), Report())
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert re.findall(r"<h[12][^>]*>(.*?)</h[12]>", markup) == ["I. Rozdzial pierwszy"]
        # Demoted, not dropped: every one of them is still in the text.
        text = fidelity.document_text(markup.encode("utf-8"))
        for furniture in ("A6.", "B1.", "0,5 L", "3 1 4", "+"):
            assert furniture in text

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

    def test_two_columns_are_read_column_by_column_and_reported(self, tmp_path):
        """Not re-flowed — read in order. Taken in page order, the columns
        interleaved and every line-end hyphen joined the wrong word."""
        left = column([f"Left {n} ends the line here" for n in range(1, 6)], top=700, left=72)
        # The right-hand column starts past the middle of the page, as a
        # real one does; a column whose lines reach across the gutter's
        # midpoint is not one (the title-page test below).
        right = column([f"Right {n} ends the line here" for n in range(1, 6)], top=700, left=380)
        source = make_pdf(tmp_path / "columns.pdf", [left + right])
        report = Report()
        book = pdf.read_pdf(str(source), report)
        text = fidelity.document_text(next(r.data for r in book.resources.values() if r.path.endswith(".xhtml")))
        assert text.index("Left 5") < text.index("Right 1"), text
        assert "pdf.columns" in {f.rule for f in report.findings}
        # Flush lines in both columns: one paragraph, not one per right-hand
        # line — the indent is measured against the column's edge, not the page's.
        assert report.stats["pdf_layout"]["paragraphs"] == 1
        assert pdf.text_of(str(source)).index("Left 5") < pdf.text_of(str(source)).index("Right 1")

    def test_two_things_side_by_side_are_read_one_after_the_other(self, tmp_path):
        """Not every page with two stacks of text is *set* in two columns —
        a manual puts a figure number in the margin, a note beside a step, a
        message table's meaning beside its message. Read straight down, those
        land in the middle of the sentence next to them.

        The cut that separates them is the same one a table must never suffer,
        so what decides is whether the lines it would separate are a grid's
        cells. Here they are not: the right-hand block has one line where the
        left has three.
        """
        lines = column(["A sentence of prose that runs along the left of the",
                        "page and goes on for a second line, and a third."], top=700, left=60)
        lines += [(360.0, 694.0, 10.0, "rys. 18")]
        lines += column(["It carries on under the number and finishes here."], top=660, left=60)
        source = make_pdf(tmp_path / "beside.pdf", [lines])
        report = Report()
        book = pdf.read_pdf(str(source), report)
        text = fidelity.document_text(
            next(r.data for r in book.resources.values() if r.path.endswith(".xhtml")))
        # The number stands on its own and not inside the sentence.
        assert "second line, and a third. It carries on" in " ".join(text.split())
        assert "pdf.columns" not in {f.rule for f in report.findings}

    def test_a_centred_title_page_is_not_two_columns(self, tmp_path):
        """Many short lines at many left edges — a title page — passed the
        first column test and came back in the wrong order once columns
        were read column by column (Chromium print of one corpus book)."""
        texts = ["A Title", "by", "Somebody Or Other", "with pictures", "printed", "in the year", "of our lord", "for the publisher", "and sold", "everywhere"]
        lines = [(306 - 3 * len(t), 700 - 16 * i, 12.0, t) for i, t in enumerate(texts)]
        report = Report()
        book = pdf.read_pdf(str(make_pdf(tmp_path / "title.pdf", [lines])), report)
        assert "pdf.columns" not in {f.rule for f in report.findings}
        text = fidelity.document_text(next(r.data for r in book.resources.values() if r.path.endswith(".xhtml")))
        assert text.index("A Title") < text.index("Somebody") < text.index("everywhere")

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

    def test_a_label_standing_on_a_drawing_goes_under_it_and_is_not_lost(self, tmp_path):
        """A callout on the artwork is not a paragraph of the book — and it is
        not nothing either. It is moved out of the flow and printed under the
        picture it stands on; every character the PDF draws has to arrive
        somewhere. Moved and not printed, 1 097 of them went missing on the
        owner's manual and `pdf.characters-unplaced` said so."""
        pytest.importorskip("PIL.Image")
        red = bytes([200, 30, 30]) * (40 * 30)
        lines = column(["A line above the picture, and another line of prose", "to make a paragraph."], top=700)
        # Inside the picture's box (x 72..192, y 450..540), as a callout is.
        lines += [(100.0, 500.0, 9.0, "A16")]
        lines += column(["And a paragraph below it."], top=400)
        source = make_pdf(tmp_path / "callout.pdf", [lines], images={0: [(72, 450, 120, 90, 40, 30, red)]})
        report = Report(source=str(source))
        book = pdf.read_pdf(str(source), report)
        text = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert f'<p class="{pdf.LABEL_CLASS}">A16</p>' in text
        assert text.index("<img ") < text.index("A16") < text.index("below it")
        # Not left in the flow as a one-word paragraph of its own.
        assert "<p>A16</p>" not in text
        assert "pdf.characters-unplaced" not in {f.rule for f in report.findings}
        assert report.stats["pdf_characters_unplaced"] == 0

    def test_a_grid_of_cells_comes_back_a_table(self, tmp_path):
        """A table read line by line is a heap: every cell a paragraph of a
        word or two. The owner's manual has 73 of them and 484 such cells —
        beverage tables, compatibility ticks, its own table of contents.

        Nothing moves to make one. The cells were already read left to right
        along each row, so recognising the grid changes the markup and not one
        character of the order.
        """
        rows = [("Americano", "tak", "tak"), ("Cappuccino", "tak", "nie"), ("Cold Brew", "nie", "tak")]
        lines = column(["A sentence of prose standing over the table."], top=700)
        for index, (name, hot, cold) in enumerate(rows):
            y = 660.0 - index * 16
            lines += [(72.0, y, 10.0, name), (220.0, y, 10.0, hot), (300.0, y, 10.0, cold)]
        lines += column(["And a sentence of prose standing under it."], top=580)
        source = make_pdf(tmp_path / "grid.pdf", [lines], title="Grid")
        report = Report(source=str(source))
        book = pdf.read_pdf(str(source), report)
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert markup.count("<tr>") == 3 and markup.count("<td>") == 9
        assert "<td>Americano</td>" in markup and "<td>nie</td>" in markup
        # A cell is not a paragraph, and the prose around it still is.
        assert "<p>Americano</p>" not in markup
        assert "<p>A sentence of prose standing over the table.</p>" in markup
        assert "<p>And a sentence of prose standing under it.</p>" in markup
        said = next(f for f in report.findings if f.rule == "pdf.tables-rebuilt")
        assert said.values == {"count": 1, "cells": 9}
        # The order is untouched: what K1 reads on the source's side is what
        # the document carries, cell for cell.
        text = fidelity.document_text(markup.encode("utf-8"))
        assert fidelity.first_character_lost(pdf.text_of(str(source)), text) == -1
        assert text.index("Americano") < text.index("Cappuccino") < text.index("Cold Brew")

    def test_a_procedure_comes_back_a_list_with_its_own_numbers(self, tmp_path):
        """A manual is mostly procedures, and a procedure read as loose
        paragraphs is a list no reading system can see. The markers are text
        the source drew — every one of them is kept — so the list is told to
        set none of its own, which is the one thing the stylesheet says.
        """
        lines = column(["Postepuj nastepujaco:"], top=700)
        # As a manual sets one: the marker at the edge, the sentence beside it,
        # and what does not fit wrapped under the sentence, not under the
        # marker. That hanging indent is what says the area is a list.
        steps = [
            (72.0, 680.0, 10.0, "1."), (90.0, 680.0, 10.0, "Ustaw kubek pod wylewka napojow"),
            (90.0, 666.0, 10.0, "i zamknij pokrywe;"),
            (72.0, 652.0, 10.0, "2."), (90.0, 652.0, 10.0, "Wcisnij pasek personalizacji"),
            (90.0, 638.0, 10.0, "u dolu obrazka;"),
            (72.0, 624.0, 10.0, "3."), (90.0, 624.0, 10.0, "Wytwarzanie zostanie przerwane."),
        ]
        source = make_pdf(tmp_path / "steps.pdf", [lines + steps])
        report = Report(source=str(source))
        book = pdf.read_pdf(str(source), report)
        document = next(r for r in book.resources.values() if r.path.endswith(".xhtml"))
        markup = document.data.decode()
        assert markup.count("<li>") == 3 and f'<ul class="{pdf.LIST_CLASS}">' in markup
        assert "<li>1. Ustaw kubek pod wylewka napojow i zamknij pokrywe;</li>" in markup
        # The marker is in the text, so the list must not draw its own.
        sheet = book.resources[pdf.STYLESHEET_PATH]
        assert sheet.media_type == "text/css"
        assert "list-style: none" in sheet.data.decode()
        assert f'href="../{pdf.STYLESHEET_PATH}"' in markup
        assert report.stats["pdf_layout"]["lists"] == 1

    def test_a_column_of_bullets_is_a_list_and_not_a_table(self, tmp_path):
        """A note set as "•" at the left edge and the sentence beside it makes
        rows of two cells that line up as neatly as any table's. Read as one it
        came out a column of bullets beside a column of prose."""
        rows = []
        for index, text in enumerate(["Aby recznie przerwac wytwarzanie, wcisnij Stop.",
                                      "Po zakonczeniu mozesz zwiekszyc ilosc napoju.",
                                      "Funkcje goracej wody mozna uzyc do podgrzania filizanki."]):
            y = 700.0 - index * 16
            rows += [(72.0, y, 10.0, "•"), (90.0, y, 10.0, text)]
        report = Report()
        book = pdf.read_pdf(str(make_pdf(tmp_path / "note.pdf", [rows])), report)
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert "<table" not in markup
        assert markup.count("<li>") == 3
        assert "<li>• Aby recznie przerwac wytwarzanie, wcisnij Stop.</li>" in markup
        assert report.stats["pdf_layout"]["tables"] == 0

    def test_prose_is_not_a_table_however_it_falls(self, tmp_path):
        """Measured on the Gutenberg corpus: over four prose books and one
        verse play this finds nothing at all. A line of prose is one cell, and
        one cell is not a row."""
        pages = [column(THREE_PARAGRAPHS) for _ in range(3)]
        report = Report()
        pdf.read_pdf(str(make_pdf(tmp_path / "prose.pdf", pages)), report)
        assert report.stats["pdf_layout"]["tables"] == 0
        assert "pdf.tables-rebuilt" not in {f.rule for f in report.findings}

    def test_the_grid_the_table_is_measured_on_is_recorded(self):
        """`D-012`: the numbers that decide what a table is say where they came
        from — a sweep over the manual and a count over the corpus."""
        source = pathlib.Path("epubforge/pdf.py").read_text(encoding="utf-8")
        column_slack = source[source.index("#: How far a cell may sit from the one above"):]
        assert "6 pt finds 72" in column_slack and "24 pt finds 75" in column_slack
        rows = source[source.index("#: Two rows standing on one grid are a table."):]
        assert "nothing at all" in rows[:400]

    def test_a_name_written_under_a_picture_becomes_its_caption(self, tmp_path):
        """"Americano" under the icon of it is the picture's name, not a
        one-word paragraph between two others. Seven of them in the owner's
        manual. A bullet also stands under a figure and is not its name, so a
        caption has to read as words."""
        pytest.importorskip("PIL.Image")
        blue = bytes([30, 60, 200]) * (40 * 30)
        # The picture's box is x 72..132, y 600..640; the name sits under it.
        lines = [(84.0, 592.0, 9.0, "Americano")]
        lines += column(["A paragraph of prose that has nothing to do with", "the picture at all."], top=560)
        source = make_pdf(tmp_path / "caption.pdf", [lines] * 2,
                          images={index: [(72, 600, 60, 40, 40, 30, blue)] for index in range(2)})
        report = Report(source=str(source))
        book = pdf.read_pdf(str(source), report)
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert "<figcaption>Americano</figcaption>" in markup
        assert "<p>Americano</p>" not in markup
        assert report.stats["pdf_characters_unplaced"] == 0
        # The prose below is a paragraph, not a second caption.
        assert "A paragraph of prose that has nothing to do with the picture at all." in markup

    def test_a_callout_on_a_drawing_leaves_the_legend_alone(self, tmp_path):
        """The manual's other drawing shape, and the one a picture cannot fix:
        the artwork is *drawn*, in curves, so there is no picture to put the
        callouts on and they stayed in the prose. A single `A15` standing
        between the two lines of an entry was read into it —

            A16. Wskaznik poziomu wody w tacce A15 na skropliny

        — the very damage the area model exists to undo, done by one stray
        word. What says `A15` is a callout is the document itself: a legend
        entry elsewhere opens with that marker and names a part.
        """
        legend = [
            (242.0, 260.0, 10.0, "A12. Pojemnik na fusy"),
            (242.0, 247.0, 10.0, "A13. Wspornik pojemnika na fusy"),
            (242.0, 233.0, 10.0, "A14. Podstawka na filizanki"),
            (242.0, 220.0, 10.0, "A15. Kratka tacki"),
            (242.0, 206.0, 10.0, "A16. Wskaznik poziomu wody w tacce"),
            (270.0, 193.0, 10.0, "na skropliny"),
            (242.0, 181.0, 10.0, "A17. Drzwiczki dostepu do zespolu"),
        ]
        # The callouts, on the artwork to the *left* of the legend.
        drawing = [(63.0, 258.0, 9.0, "A12"), (149.0, 224.0, 9.0, "A13"),
                   (63.0, 225.0, 9.0, "A14"), (149.0, 198.0, 9.0, "A15"),
                   (65.0, 189.0, 9.0, "A16")]
        source = make_pdf(tmp_path / "callouts.pdf", [legend + drawing] * 4, title="Opis", language="pl")
        report = Report(source=str(source))
        book = pdf.read_pdf(str(source), report)
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert "<li>A16. Wskaznik poziomu wody w tacce na skropliny</li>" in markup
        assert "<li>A15. Kratka tacki</li>" in markup
        # A legend is a list, and comes back one.
        assert f'<ul class="{pdf.LIST_CLASS}">' in markup
        # Gathered, not dropped: every callout is in the book, in one place.
        assert f'<p class="{pdf.LABEL_CLASS}">A12 A14 A13 A15 A16</p>' in markup
        assert report.stats["pdf_characters_unplaced"] == 0
        assert report.stats["pdf_layout"]["labelled_drawings"] == 4

    def test_a_block_set_in_from_the_margin_is_not_a_paragraph_a_line(self, tmp_path):
        """An indent is a line set in from the ones *around* it, not a whole
        block set in from the page. A manual's list of teas stands forty points
        inside the body's edge, every line of it, so every line looked indented
        and eight lines came out as eight paragraphs.

        Measured when this was fixed: torn paragraphs fell on every book of the
        Gutenberg corpus at once — 35 to 23, 51 to 39, 22 to 10, 18 to 4, 16 to
        4, 32 to 20 — because prose set in a narrower measure had the same
        thing happen to it.
        """
        lines = column(["A paragraph of ordinary prose at the body's own left", "edge, running to a second line."], top=700)
        # The block: set in forty points, two lines to a pair, a wider gap
        # between pairs than inside one.
        inset = []
        for index, (name, note) in enumerate([("Herbata Biala", "czas parzenia 1-3 minuty"),
                                              ("Herbata Zielona", "czas parzenia 1-2 minuty")]):
            top = 640.0 - index * 60
            inset += [(112.0, top, 10.0, name), (112.0, top - 12, 10.0, note)]
        source = make_pdf(tmp_path / "inset.pdf", [lines + inset])
        book = pdf.read_pdf(str(source), Report())
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert "<p>Herbata Biala czas parzenia 1-3 minuty</p>" in markup
        assert "<p>Herbata Zielona czas parzenia 1-2 minuty</p>" in markup
        # And a real indent still opens a paragraph: the second of
        # THREE_PARAGRAPHS is marked by one and nothing else.
        prose = pdf.read_pdf(str(make_pdf(tmp_path / "prose.pdf", [column(THREE_PARAGRAPHS)])), Report())
        text = next(r.data.decode() for r in prose.resources.values() if r.path.endswith(".xhtml"))
        assert text.count("<p>") == 3

    def test_a_marker_beside_its_entry_is_one_line_of_the_page(self, tmp_path):
        """A legend that sets `A6.` at the left edge and `Tacka na skropliny`
        a word's width away has written one entry, not two paragraphs. Far
        apart on the same baseline it would be two columns instead — which is
        what the gap measures."""
        lines = [(56.7, 300.0, 10.0, "A6."), (84.7, 300.0, 10.0, "Tacka na skropliny")]
        lines += [(56.7, 286.0, 10.0, "A7."), (84.7, 286.0, 10.0, "Kabel zasilajacy")]
        lines += column(["Prose under the legend, which is a paragraph of its own", "and stays one."], top=250)
        book = pdf.read_pdf(str(make_pdf(tmp_path / "legend.pdf", [lines])), Report())
        markup = next(r.data.decode() for r in book.resources.values() if r.path.endswith(".xhtml"))
        assert "<li>A6. Tacka na skropliny</li>" in markup
        assert "<li>A7. Kabel zasilajacy</li>" in markup
        assert "<p>A6.</p>" not in markup

    def test_a_drawing_this_reader_cannot_carry_is_reported(self, tmp_path):
        """A book that quietly lacks every diagram its source had is not an
        honest rebuild. This reader carries pictures and cannot draw, so it
        says which pages had a drawing on them."""
        lines = column(["A page of prose with a diagram drawn on it in curves,",
                        "which this reader has no way to carry."], top=700)
        source = make_pdf(tmp_path / "drawn.pdf", [lines], strokes={0: _spiral(120, 420, 60)})
        report = Report(source=str(source))
        pdf.read_pdf(str(source), report)
        said = next(f for f in report.findings if f.rule == "pdf.drawing-not-carried")
        assert said.level is Level.WARN
        assert said.values["pages"] == 1
        # And a page with nothing but a rule under its heading has no drawing.
        plain = make_pdf(tmp_path / "plain.pdf", [lines], strokes={0: [(72, 690, 340, 690)]})
        quiet = Report(source=str(plain))
        pdf.read_pdf(str(plain), quiet)
        assert "pdf.drawing-not-carried" not in {f.rule for f in quiet.findings}

    def test_the_left_side_of_k1_reads_the_page_the_way_the_reader_does(self, tmp_path):
        """`text_of` is the source side of K1 and `read_pdf` is the output
        side. Both are this module reading one file, and the gate between them
        is a subsequence test — so they have to agree about what order the
        source is in, or each is answering a different question.

        They stopped agreeing the day the reader began cutting pages into
        areas: `text_of` was still reading the lines straight down the page,
        and the owner's 105-page manual was refused for text "lost" that was
        only somewhere else. Nothing was lost; the gate had two sources.
        """
        pytest.importorskip("PIL.Image")
        red = bytes([200, 30, 30]) * (40 * 30)
        # A drawing with a callout on it, beside a legend that wraps: the page
        # whose reading order the areas changed.
        lines = [(100.0, 500.0, 9.0, "A16")]
        lines += column(["A16. Wskaznik poziomu wody w tacce", "na skropliny"], top=470, left=242)
        source = make_pdf(tmp_path / "k1.pdf", [lines] * 4,
                          images={index: [(72, 450, 120, 90, 40, 30, red)] for index in range(4)})
        book = pdf.read_pdf(str(source), Report())
        rebuilt_text = " ".join(
            fidelity.document_text(book.resources[item.path].data) for item in book.spine
        )
        assert fidelity.first_character_lost(pdf.text_of(str(source)), rebuilt_text) == -1
        # And it is the areas' order both sides carry, not the page's.
        assert pdf.text_of(str(source)).index("A16 ") < pdf.text_of(str(source)).index("A16.")


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


class TestTheReaderSaysHowWellItWent:
    """The reader has always reported what it *did* and never how it went.

    On prose those are the same question. On a document laid out in blocks
    they are not: the owner's first real PDF — a 105-page appliance manual —
    came out as 1 857 paragraphs, which is a fine number, and 489 of them were
    one sentence cut in half, which is the whole story. Nothing in the report
    said so, so he had to read the book to find out.
    """

    def test_a_sentence_split_across_two_paragraphs_is_counted(self):
        blocks = [
            pdf.Block(kind="p", lines=[pdf.Line("Wskaźnik poziomu wody w tacce", 0, 1, 0, 1, 10, 1)]),
            pdf.Block(kind="p", lines=[pdf.Line("na skropliny", 0, 1, 0, 1, 10, 1)]),
        ]
        quality = pdf.measure_quality(blocks)
        assert quality.paragraphs == 2
        assert quality.torn == 1
        assert quality.torn_share == 0.5

    def test_a_finished_sentence_followed_by_a_new_one_is_not(self):
        blocks = [
            pdf.Block(kind="p", lines=[pdf.Line("Woda jest gorąca.", 0, 1, 0, 1, 10, 1)]),
            pdf.Block(kind="p", lines=[pdf.Line("Ekspres jest gotowy.", 0, 1, 0, 1, 10, 1)]),
        ]
        assert pdf.measure_quality(blocks).torn == 0

    def test_a_label_torn_off_a_diagram_counts_as_a_fragment(self):
        blocks = [
            pdf.Block(kind="p", lines=[pdf.Line("Americano", 0, 1, 0, 1, 10, 1)]),
            pdf.Block(kind="p", lines=[pdf.Line("Kawa mielona", 0, 1, 0, 1, 10, 1)]),
            pdf.Block(kind="p", lines=[pdf.Line("Uwaga!", 0, 1, 0, 1, 10, 1)]),
        ]
        quality = pdf.measure_quality(blocks)
        # "Uwaga!" is a sentence of one word; the other two are labels.
        assert quality.fragments == 2

    def test_prose_is_reported_and_not_warned_about(self, tmp_path):
        report = Report(source="x")
        pdf.read_pdf(str(book_with_heads(tmp_path)), report)
        said = [f for f in report.findings if (f.rule or "").startswith("pdf.reading")]
        assert [f.rule for f in said] == ["pdf.reading-quality"]
        assert said[0].level is not Level.WARN
        assert said[0].values["torn"] == 0

    def test_a_legend_beside_a_drawing_is_read_whole(self, tmp_path):
        """The shape the manual is full of, reproduced from its own geometry.

        A legend stands in a column at a fixed x; the same labels are also
        printed *on the drawing* beside it, at whatever x the artwork puts
        them. Read top to bottom across the whole page, the drawing's labels
        fall between the legend's lines — so a legend entry that wraps was cut
        in half by a label that belongs to a picture:

            A16. Wskaznik poziomu wody w tacce   (legend, x242)
            A15                                  (on the drawing, x149)
            na skropliny                         (the legend line, continued)

        which is where a quarter of that book's paragraphs came from. The
        labels go onto the drawing they stand on (`_lift_labels`) and the entry
        is one paragraph again. On the owner's own 105-page manual this took the
        torn share from 26 % to 2 %.
        """
        pytest.importorskip("PIL.Image")
        grey = bytes([220, 220, 220]) * (40 * 30)
        # The drawing itself: x 55..200, y 180..270, which is where the labels
        # stand and where the legend at x242 does not.
        artwork = {index: [(55, 180, 145, 90, 40, 30, grey)] for index in range(4)}
        pages = []
        for _ in range(4):
            lines = [
                (242.0, 260.0, 12.0, "A12. Pojemnik na fusy"),
                (100.0, 260.0, 9.0, "A12"),
                (242.0, 247.0, 12.0, "A13. Wspornik pojemnika na fusy"),
                (168.0, 224.0, 9.0, "A13"),
                (242.0, 233.0, 12.0, "A14. Podstawka na filizanki"),
                (63.0, 225.0, 9.0, "A14"),
                (242.0, 220.0, 12.0, "A15. Kratka tacki"),
                (242.0, 206.0, 12.0, "A16. Wskaznik poziomu wody w tacce"),
                (149.0, 198.0, 9.0, "A15"),
                (270.0, 193.0, 10.0, "na skropliny"),
                (65.0, 189.0, 9.0, "A16"),
                (242.0, 181.0, 12.0, "A17. Drzwiczki dostepu do zespolu"),
            ]
            pages.append(lines)
        source = make_pdf(tmp_path / "legenda.pdf", pages, title="Opis", language="pl", images=artwork)
        report = Report(source=str(source))
        book = pdf.read_pdf(str(source), report)
        markup = next(r.data for r in book.resources.values() if r.path.endswith(".xhtml")).decode("utf-8")
        assert "<li>A16. Wskaznik poziomu wody w tacce na skropliny</li>" in markup
        # Nothing was dropped to get there: the labels are printed under the
        # drawing they stand on, and not one of them is left in the legend.
        assert f'class="{pdf.LABEL_CLASS}">A12 A14 A13 A15 A16</p>' in markup
        assert "<p>A16</p>" not in markup
        said = next(f for f in report.findings if (f.rule or "").startswith("pdf.reading"))
        assert said.rule == "pdf.reading-quality", said.values
        assert said.values["torn"] == 0

    def test_a_document_read_badly_is_warned_about(self):
        """The warning has to be reachable, or it says nothing when it is
        silent. Ten torn paragraphs in ninety is over the measured share."""
        def document(torn):
            """`torn` sentences cut in two, in ninety paragraphs."""
            blocks = []
            for _ in range(torn):
                blocks += [pdf.Block(kind="p", lines=[pdf.Line("Wskaźnik poziomu wody w tacce", 0, 1, 0, 1, 10, 1)]),
                           pdf.Block(kind="p", lines=[pdf.Line("na skropliny", 0, 1, 0, 1, 10, 1)])]
            while len(blocks) < 90:
                blocks.append(pdf.Block(kind="p", lines=[pdf.Line("Zdanie, które kończy się kropką.", 0, 1, 0, 1, 10, 1)]))
            return pdf.measure_quality(blocks)

        quality = document(torn=10)
        assert quality.paragraphs == 90 and quality.torn == 10
        assert quality.torn_share >= pdf.TORN_SHARE_WARN
        assert quality.poor is True
        # And one under the share is not poor: the threshold is a threshold.
        assert document(torn=8).poor is False

    def test_the_share_that_raises_it_is_a_measured_number_with_its_evidence(self):
        """`D-012`: a threshold in this program says where it came from."""
        source = pathlib.Path("epubforge/pdf.py").read_text(encoding="utf-8")
        where = source.index("TORN_SHARE_WARN")
        preamble = source[max(0, where - 700):where]
        assert "24 %" in preamble and "measured" in preamble.lower()


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

    def test_a_word_broken_across_a_running_head_is_whole_again_when_the_head_goes(self, tmp_path):
        """The foot of one page ends `prze-`, the next page opens with its
        running head and then `konaniem`. With the head removed the halves
        are joined the way the reader joins any line end — no space — so the
        hyphen stage meets `prze-konaniem`, not `prze- konaniem`."""
        pages = []
        for number in range(1, 7):
            lines = [(72, 760, 10.0, "THE BOOK OF PAGES")]
            if number == 3:
                lines += column(["A sentence that runs to the foot of the page with prze-"], top=600)
            elif number == 4:
                lines += column(["konaniem and goes on from there.", "And a second line."], top=600)
            else:
                lines += column([f"Page {number} carries ordinary prose in its body,",
                                 "two lines of it, set at the body size."], top=600)
            lines += [(300, 30, 10.0, str(number))]
            pages.append(lines)
        source = make_pdf(tmp_path / "split.pdf", pages, title="The Book of Pages")
        result = rebuilt(source, tmp_path, standing={"pdf:running-heads": Answer(option="remove")})
        assert result.output_path
        assert "prze-konaniem" in prose_of(result.output_path)

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
