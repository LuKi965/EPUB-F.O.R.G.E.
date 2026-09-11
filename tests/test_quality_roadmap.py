"""What the conversion still gets wrong, written down as tests.

The quality roadmap of 2026-09-09 (`EPUB-FORGE-QUALITY-ROADMAP`) names four
findings about the converter. Its first iteration asks for two things and is
explicit that they are different: **characterise** Q01 and Q02 without fixing
them, and **fix** Q08.

Where they stand as this file is written, each said once here and argued in
the class that holds it:

* **Q01, the vanishing drawing — closed.** The reader boxes the strokes in
  order to gather the text standing on them, and now renders that box from the
  source (`pdfconv/draw.py`). The tests pass, and skip rather than fail where
  no renderer is installed, because the feature is optional and says so.
* **Q02, the columns read across — did not reproduce.** Five geometries were
  tried and none interleaved. That is the measurement, not a verdict: the page
  it was found on is a private one, denser than anything written here. Kept as
  a passing regression test against `LEGEND` below.
* **Q07, the render gate never looks at the source — closed by A06** of the
  0.4.4 recovery plan, with a measured tolerance (`gate.LOST_SHARE`).

That marker does the two things the package asks for at once — *„Zapisz ich
testy jako jawne znane luki z identyfikatorem i powodem, bez przedstawiania
ich jako zaliczonych"* and *„Nie pozostawiaj nieopisanej awarii głównego
CI"*: pytest reports the gap as `xfailed` rather than `passed`, CI stays
green, and on the day it closes `strict` turns the unexpected pass into a
failure so that somebody has to come back here and say so. What is **not**
done is the thing the package forbids: no golden was updated to the output as
it stands today.

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

from epubforge.pdfconv import draw, service
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
    # A drawing dense enough to *be* one. `reader.DRAWING_DENSITY` asks for a
    # cell to be touched twice on average, and rightly: a single box round a
    # paragraph is not a diagram. Nine strokes did not clear it — measured —
    # so this is line art of the kind the roadmap is about: an outline, its
    # internal divisions, hatching, and leader lines out to the callouts.
    strokes = [
        (150, 560, 450, 560), (150, 560, 150, 700), (450, 560, 450, 700),
        (150, 700, 450, 700), (150, 630, 450, 630), (300, 560, 300, 700),
        (300, 700, 300, 730), (300, 730, 290, 720), (300, 730, 310, 720),
    ]
    # Cross-hatched, because `reader.DRAWING_DENSITY` asks for a cell to be
    # touched twice on average and one direction of hatching gives it one.
    # Measured on the way here: outline alone — not a drawing; hatched one way
    # at 10 pt — not a drawing; cross-hatched at 12 pt — a drawing. That
    # threshold is right, and a fixture has to clear it honestly rather than
    # have it lowered.
    for x in range(150, 451, 12):
        strokes.append((x, 560, x, 700))
    for y in range(560, 701, 12):
        strokes.append((150, y, 450, y))
    for x, y in ((190, 670), (400, 670), (190, 590), (400, 590)):
        strokes.append((x, y, x + 20, y + 20))   # leader lines to the callouts
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
                    title="Rysunek i legenda", language="pl", strokes={0: strokes})


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

    **Closed.** The reader always knew where the drawing was — it boxes the
    curves in order to gather the text standing on them — and had nothing to
    put there. It now puts a picture of that box, drawn from the source PDF at
    a stated scale (`pdfconv/draw.py`), appended to the page's pictures so
    that everything a picture already gets applies: the callouts are gathered
    into it, it is emitted where it stood, it is written as a resource.

    A raster of the region and not an SVG export, deliberately: an export
    needs fonts, clipping, transforms and effects to survive a second engine,
    and the roadmap warns against assuming SVG solves the problem by itself.
    What is asserted below is the requirement — *the drawing arrives* — not
    the technique, so a later vector emitter satisfies it unchanged.

    Skipped rather than failed where no renderer is installed: the feature is
    optional and degrades honestly, and a test machine without it is not a
    defect in the book.
    """

    def test_the_drawing_arrives_as_something_that_can_be_drawn(self, tmp_path):
        if not draw.available():
            pytest.skip(f"brak renderera ({draw.why_not()})")
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
        # And it is a picture of *this* drawing, not an empty box: the page
        # carries no raster of its own, so anything here came from the region,
        # and a region that rendered blank would be a few bytes.
        with zipfile.ZipFile(book) as archive:
            biggest = max(archive.getinfo(name).file_size for name in drawn)
        assert biggest > 500, f"obraz regionu jest pusty ({biggest} B)"

    def test_the_callouts_stay_text_beside_it(self, tmp_path):
        """The drawing arriving must not cost the text that stood on it.

        Every character the PDF draws has to be in the book (K1-PDF), and the
        callouts are now *also* pixels inside the picture — so the risk this
        guards is the opposite of the old one: printing them once as an image
        and calling that carried.
        """
        source = diagram_with_a_legend(tmp_path)
        result = converted(source, tmp_path)
        assert result.published, result.error
        (book,) = result.published_outputs
        said = " ".join(documents_of(book).values())
        for label, _ in LEGEND:
            assert label in said, f"etykieta {label} zniknela z tekstu"

    def test_without_a_renderer_the_book_still_comes_out(self, tmp_path, monkeypatch):
        """Optional means optional. With no renderer the drawing is not
        carried, the report says so in as many words, and the conversion is
        not a failure — which is how it behaved before any of this."""
        # The library itself, not the sentence about it: `available()` reads
        # `_renderer()`, so taking away the renderer is the same thing that
        # happens on a machine where the optional extra was never installed.
        monkeypatch.setattr(draw, "_renderer", lambda: None)
        source = diagram_with_a_legend(tmp_path)
        result = converted(source, tmp_path)
        assert result.published, result.error
        (book,) = result.published_outputs
        drawn = [name for name in resources_of(book) if name.endswith(".png")]
        assert not drawn, "bez renderera nie powinno byc obrazu regionu"
        assert any("drawing-not-carried" in one or "rysunk" in one.lower()
                   for one in result.warnings), result.warnings


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


class TestQ07TheRenderGateLooksAtTheSource:
    """*„`render_gate` uruchamia `render_fidelity.drawn(candidate, …)`:
    kontrolę niepustego renderowania wyniku, bez porównania z PDF."*

    Closed with A06 of the 0.4.4 recovery plan, and closed the way this file
    said it had to be: with a tolerance that was **measured** rather than
    chosen. `gate.LOST_SHARE` carries the seven measurements it stands
    between (D-012). For a fixed book the gate is handed the source and
    compares page for page; for a reflowable one it still measures what
    can be measured — a page that draws blank — and says so.

    What used to be an `xfail(strict=True)` is now the requirement, asserted.
    """

    def test_the_gate_is_handed_the_source(self):
        import inspect

        from epubforge.pdfconv import gate

        taken = list(inspect.signature(gate.render_gate).parameters)
        assert "source" in taken, (
            "brama publikacji dla PDF-a nie dostaje nawet zrodla "
            f"({', '.join(taken)}) — mierzy tylko, czy wynik cokolwiek narysowal"
        )

    def test_the_limit_stands_between_the_measurements_it_records(self):
        """The number is in the code with what it was measured against; this
        keeps the two from drifting apart — a limit moved without moving
        its evidence fails here."""
        from epubforge.pdfconv import gate

        faithful = (0.047, 0.023, 0.028)
        damaged = (0.092, 0.237, 0.490, 0.526)
        assert max(faithful) < gate.LOST_SHARE < min(damaged)
