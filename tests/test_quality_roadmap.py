"""What the conversion still gets wrong, written down as tests.

The quality roadmap of 2026-09-09 (`EPUB-FORGE-QUALITY-ROADMAP`) names four
findings about the converter. Its first iteration asks for two things and is
explicit that they are different: **characterise** Q01 and Q02 without fixing
them, and **fix** Q08.

So the drawing and the columns are here as `xfail(strict=True)`. That marker
does the two things the package asks for at once — *„Zapisz ich testy jako
jawne znane luki z identyfikatorem i powodem, bez przedstawiania ich jako
zaliczonych"* and *„Nie pozostawiaj nieopisanej awarii głównego CI"*: pytest
reports them as `xfailed` rather than `passed`, CI stays green, and on the day
the gap closes `strict` turns the unexpected pass into a failure so that
somebody has to come back here and say so. What is **not** done is the thing
the package forbids: no golden was updated to the output as it stands today.

The fixtures are this file's own, synthetic, and deliberately unlike the
private document the roadmap was written from. They reproduce the *kind* of
construct — a drawing with callouts, a two-column legend, a running head over
independent body text — and carry no brand, no page numbers of anybody's
manual and none of its identifiers. The expected reading order is written out
by hand below, not read back through the same reader the conversion uses:
a golden taken from the reader would freeze the very order that is wrong
(Q02's own warning about K1).
"""

from __future__ import annotations

import pathlib
import zipfile

import pytest

from epubforge.pdfconv import service
from epubforge.pdfconv.models import PdfConversionPlan
from epubforge.pdfconv.settings import PdfSettings
from tests.test_pdf import column, make_pdf

pytest.importorskip("pdfminer.high_level")


# --------------------------------------------------------------------------
# Fixtures: the two constructs, and nothing else on the page.
# --------------------------------------------------------------------------

#: The legend, as a person reads it: the left column top to bottom, then the
#: right one. Written here by hand — this is the *specification* of the order,
#: and the only reason it is trustworthy is that no code produced it.
#: Each entry is its label and the lines its description is set on, written
#: out rather than wrapped by code so that what the page draws is visible here.
LEGEND = (
    ("L1", ("Zbiornik na wode,", "wyjmowany od frontu")),
    ("L2", ("Pokrywa zbiornika", "z wygodnym uchwytem")),
    ("L3", ("Tacka ociekowa", "z krata i plywakiem")),
    ("R1", ("Pojemnik na zuzyte", "fusy, wyjmowany")),
    ("R2", ("Dysza pary", "z oslona przed poparzeniem")),
    ("R3", ("Panel sterowania", "z wyswietlaczem")),
)


def diagram_with_a_legend(tmp_path: pathlib.Path) -> pathlib.Path:
    """One page: a drawing made of strokes, its callouts, and a two-column
    legend underneath.

    No raster image anywhere in the file, on purpose. It is what lets the
    drawing test mean something: if an `img` turns up in the output, the only
    thing it can have come from is the drawing, so the test cannot be satisfied
    by some unrelated picture the page happened to carry — which is the trap
    the package names (*„Test nie może uznać dowolnego img za dowód"*).
    """
    # A box with an arrow and a divider: nine strokes, which no amount of text
    # extraction produces.
    strokes = {0: [
        (150, 560, 450, 560), (150, 560, 150, 700), (450, 560, 450, 700),
        (150, 700, 450, 700),
        (300, 700, 300, 730), (300, 730, 290, 720), (300, 730, 310, 720),
        (150, 630, 450, 630), (300, 560, 300, 700),
    ]}
    lines = [(210, 745, 11.0, "Rysunek 1. Widok od przodu")]
    # The callouts, printed on the drawing the way a manual prints them.
    for label, x, y in (("L1", 170, 670), ("L2", 380, 670),
                        ("L3", 170, 590), ("R1", 380, 590)):
        lines.append((x, y, 9.0, label))
    # The legend below it, in two columns that are read one after the other.
    # Set with the lines *staggered*: the descriptions wrap to different
    # numbers of lines, so no row of the left column sits at the same height as
    # a row of the right one. That is the shape the roadmap describes — a line
    # taken in y order alone lands between two lines of the other column — and
    # a fixture whose columns line up neatly does not reproduce it (measured:
    # with both columns on one pitch the conversion reads them correctly).
    for index, (name, said) in enumerate(LEGEND[:3]):
        y = 500 - index * 46
        lines.append((72, y, 10.0, f"{name}. {said[0]}"))
        lines.append((72, y - 13, 10.0, said[1]))
    for index, (name, said) in enumerate(LEGEND[3:]):
        # Offset by seven points, so no right-hand line shares a baseline with
        # a left-hand one and y order alone interleaves the two columns.
        y = 493 - index * 46
        lines.append((320, y, 10.0, f"{name}. {said[0]}"))
        lines.append((320, y - 13, 10.0, said[1]))
    return make_pdf(tmp_path / "diagram.pdf", [lines],
                    title="Rysunek i legenda", language="pl", strokes=strokes)


def converted(source: pathlib.Path, tmp_path: pathlib.Path, **settings):
    """One document through the production service, gates off — what is being
    measured here is the conversion, not EPUBCheck's availability."""
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    plan = PdfConversionPlan(sources=(source,), destination=out,
                             settings=PdfSettings(**settings),
                             validate="off", render_gate="off")
    (result,) = service.convert(plan)
    return result


def documents_of(epub: pathlib.Path) -> "dict[str, str]":
    with zipfile.ZipFile(epub) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith((".xhtml", ".html", ".svg"))
        }


def resources_of(epub: pathlib.Path) -> "list[str]":
    with zipfile.ZipFile(epub) as archive:
        return archive.namelist()


class TestQ01TheDrawingDoesNotSurviveTheConversion:
    """*„Znikający wektor: input zawiera rysunek; output ma zachować go
    wizualnie, nie tylko nazwy elementów."*

    **Known gap, not fixed in this iteration.** The reader collects a page's
    curves as bounding boxes to find regions with (`reader.Page.drawings`, and
    its own comment says so: *„Not carried into the book — this reader has no
    way to draw them"*), and the fixed emitter writes text and rasters only.
    Nothing between the page and the book can draw a line, so the callouts
    arrive as a row of labels with nothing to label.

    Closing it is a piece of work the roadmap puts behind a decision that is
    the owner's: a page image or an SVG export, each with its own cost in
    accessibility, size and reader support. That decision is not made here.
    """

    @pytest.mark.xfail(strict=True, reason="Q01: rysunki wektorowe nie sa przenoszone")
    def test_the_drawing_arrives_as_something_that_can_be_drawn(self, tmp_path):
        source = diagram_with_a_legend(tmp_path)
        result = converted(source, tmp_path)
        assert result.published, result.error
        (book,) = result.published_outputs
        drawn = [
            name for name in resources_of(book)
            if name.endswith((".svg", ".png", ".jpg", ".jpeg"))
            and "cover" not in name.lower()
        ]
        inline = [text for text in documents_of(book).values() if "<svg" in text]
        assert drawn or inline, (
            "rysunek zniknal: w wyniku nie ma ani grafiki wektorowej, ani obrazu "
            "regionu — same etykiety, ktore nie maja juz czego opisywac"
        )

    def test_and_meanwhile_the_callouts_arrive_without_it(self, tmp_path):
        """The other half of the same fact, and this one passes today.

        It is here so the gap above is not the only record: the labels *are*
        carried, which is precisely why a check that only counts characters
        sees nothing wrong with a page whose drawing is gone.
        """
        source = diagram_with_a_legend(tmp_path)
        result = converted(source, tmp_path)
        assert result.published, result.error
        (book,) = result.published_outputs
        said = " ".join(documents_of(book).values())
        assert "L1" in said and "R1" in said, "etykiety tez zniknely"
        assert result.warnings, "utrata rysunku nie zostala nawet odnotowana"


class TestQ02TheColumnsAreReadAcross:
    """*„Kolumny: opis lewego elementu nie zawiera etykiety/opisu prawego."*

    **Written to reproduce Q02, and it did not.** This is the result, not an
    excuse for one: at `f468d03` the conversion reads a two-column legend
    correctly, and the test below passes rather than being an `xfail` that
    quietly succeeds. Five geometries were tried before saying so — a wide
    gutter with the columns level, gutters at 240 pt and 210 pt, columns of
    unequal length (3 entries against 2), and the legend with the drawing
    above it removed. None interleaved.

    That is consistent with where the finding came from: the roadmap audited a
    snapshot declared 0.4.3, and the column and callout work of the two PDF
    packages that followed it is on this branch. It is **not** a claim that
    Q02 is closed. The page it was found on is a mixed page of a private
    document, longer and denser than anything written here, and it remains the
    acceptance case — a synthetic fixture that fails to provoke a defect is
    weak evidence about a real one.

    The expected order is `LEGEND` above, written by hand. Reading it back
    through the same reader would prove only that the reader agrees with
    itself — the roadmap says so in as many words, and it is why this is not
    a golden file. Kept as a regression test: this order is now something the
    converter is held to.
    """

    def test_no_entry_swallows_the_label_of_another(self, tmp_path):
        source = diagram_with_a_legend(tmp_path)
        result = converted(source, tmp_path)
        assert result.published, result.error
        (book,) = result.published_outputs
        said = " ".join(documents_of(book).values())

        intruded = []
        for name, description in LEGEND:
            start = said.find(f"{name}.")
            if start < 0:
                intruded.append(f"{name}: nie ma go w wyniku")
                continue
            # The entry runs to the next label or to the end of the text.
            ends = [said.find(f"{other}.", start + 1)
                    for other, _ in LEGEND if other != name]
            ends = [end for end in ends if end > start]
            entry = said[start:min(ends)] if ends else said[start:]
            for other, _ in LEGEND:
                if other != name and other in entry:
                    intruded.append(f"{name} niesie w sobie {other}: {entry.strip()[:90]!r}")
        assert not intruded, intruded


class TestQ07TheRenderGateNeverLooksAtTheSource:
    """*„`render_gate` uruchamia `render_fidelity.drawn(candidate, …)`:
    kontrolę niepustego renderowania wyniku, bez porównania z PDF."*

    **Known gap, not fixed in this iteration**, and not for lack of will: the
    comparison needs a renderer, and which one is a licence and distribution
    decision the roadmap explicitly leaves to the owner (`02-TARGET-
    ARCHITECTURE`, „Decyzje zależności i źródła"). Making that choice here to
    turn a test green would be deciding it by the back door.

    What is asserted is the shape of the gate as it stands, so the day the
    comparison arrives, this says where it goes.
    """

    @pytest.mark.xfail(strict=True, reason="Q07: brama nie porownuje wyniku ze zrodlem")
    def test_the_gate_compares_the_output_against_the_source_page(self, tmp_path):
        """What the gate would have to do, asserted against what it does.

        Written this way round on purpose. The first draft asserted the gate's
        *current* shape — which passes, and a passing test is how a gap comes
        to look like a feature. This one states the requirement and is expected
        to fail until somebody meets it.

        A page carrying a drawing and four labels is not blank, so the present
        check is content with it while the drawing is gone. That is Q07 in one
        sentence: „strona z samymi A1–A11 nie jest pusta".
        """
        import inspect

        from epubforge.pdfconv import gate

        # Asked of the signature, not of the prose: an earlier draft looked for
        # the word „source" in the body and passed on the docstring, which is
        # the same mistake as grepping for a name instead of asking what ran.
        # A gate that is not handed the source cannot compare anything to it.
        taken = list(inspect.signature(gate.render_gate).parameters)
        assert "source" in taken, (
            "brama publikacji dla PDF-a nie dostaje nawet zrodla "
            f"({', '.join(taken)}) — mierzy tylko, czy wynik cokolwiek narysowal"
        )
