"""F-028: the gate that looks at a rendered page.

Every structural check this program has passes on a book that comes out
cropped, stretched, blank or with the dedication pushed off the bottom. So the
acceptance criterion for this finding is not "it agrees with me about a real
book" — it is that **deliberate damage is caught**, which is what this file is.

Four mutations, each a shape the audit names, applied to the *output* side of a
comparison whose source is known good. If the gate cannot see these, it is
decoration.

The other half is the one that took three attempts to get right and is at the
bottom: a repair must not read as damage. Both mandatory fixture books pass the
gate with zero problems, and on one of them the cover, both title pages and the
dedication all change materially — because the rebuild makes an oversized cover
fit the page. A gate that called that a defect would be switched off within a
week, and the audit's own risk note for this finding is exactly that.
"""

from __future__ import annotations

import inspect
import pathlib

import pytest

from epubforge import render, render_fidelity
from tests.factory import write_zip

import os

#: These tests measure a *browser*, not this program, and the numbers they
#: assert — how many pixels move, how much ink a page keeps — belong to one
#: engine. Run against whatever browser a machine happens to have, they measure
#: the machine: on the Windows runner they found Edge, took the suite from 200
#: seconds to 961, reported an empty engine version, and disagreed with Chromium
#: about three of the four damage shapes.
#:
#: That is the same defect as BA-2026-004 and as `find_renderer` searching only
#: `PATH`, arriving a third time, and the audit already named the fix: a
#: *pinned* renderer. So these run when somebody says which engine they mean —
#: `EPUBFORGE_RENDER_TESTS=1`, with `EPUBFORGE_CHROME` pointing at it if it is
#: not the one on `PATH` — and skip loudly otherwise rather than measuring
#: whatever turned up. They are run here before every release against
#: Chromium 141.
_ASKED_FOR = os.environ.get("EPUBFORGE_RENDER_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not _ASKED_FOR or render.find_renderer() is None,
    reason=(
        "set EPUBFORGE_RENDER_TESTS=1 and have a Chromium-based browser: these "
        "measure an engine, and an unpinned one measures the machine"
    ),
)

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

PACKAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title>'
    "<dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
    '<manifest><item id="c" href="r.xhtml" media-type="application/xhtml+xml"/>'
    "{extra}</manifest>"
    '<spine><itemref idref="c"/></spine></package>'
)

#: Enough text that losing half of it is visible as a drop in coverage.
PARAGRAPHS = "".join(
    f"<p>Akapit numer {n}, z sensowną długością i polskimi znakami: ąćęłńóśźż. "
    f"Tekst ma zajmować miejsce na stronie, żeby dało się zmierzyć, ile go jest.</p>"
    for n in range(1, 13)
)


def page(body: str, style: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
        '<meta charset="utf-8"/><title>R</title>'
        f"<style>body{{margin:0;background:#fff;font:14px serif}}p{{margin:8px}}{style}</style>"
        f"</head><body>{body}</body></html>"
    ).encode()


def book(path, body: str, style: str = "", extra_manifest: str = "", files=None) -> str:
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": PACKAGE.format(extra=extra_manifest).encode(),
        "OEBPS/r.xhtml": page(body, style),
    }
    entries.update(files or {})
    return write_zip(str(path), entries)


def gate(source, output, **kwargs):
    return render_fidelity.compare(
        source, output, viewports=((600, 800),), sample=0, **kwargs
    )


def problems_of(result) -> str:
    return " | ".join("; ".join(page.problems) for page in result.pages if page.problems)


class TestTheFourShapesOfDamage:
    """Each one applied deliberately to the output side."""

    def test_a_page_that_came_out_blank(self, tmp_path):
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        output = book(tmp_path / "b.epub", "")
        result = gate(source, output)
        assert not result.ok
        assert "pusta" in problems_of(result)

    def test_a_page_that_lost_half_its_text(self, tmp_path):
        """The crop case in the form it actually reaches a reader: the page is
        still there, still valid, and half of it is gone."""
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        keep = "".join(PARAGRAPHS.split("</p>")[:4]) + "</p>"
        output = book(tmp_path / "b.epub", keep)
        result = gate(source, output)
        assert not result.ok
        assert "mniej treści" in problems_of(result)

    #: Ile tekstu ma zostać zepchnięte poza dolną krawędź. Ułamki, nie piksele,
    #: i to jest cała nauka z EF-055.
    #:
    #: Stały tu wcześniej `620, 640, 660, 680` — piksele zmierzone na pełnym
    #: Chromium z podręcznego katalogu. Na `chrome-headless-shell`, czyli na
    #: silniku, który wozi instalator, trzy z nich **nie spychają niczego**:
    #: tekst ma około 134 px, więc przy 620 kończy się na 0,954 wysokości strony.
    #: Brama mówiła wtedy „nic nie ubyło" i **miała rację** — to test twierdził
    #: uszkodzenie, którego nie było, i oskarżał bramę o przeoczenie.
    #:
    #: Liczba pikseli jest własnością silnika. Ułamek zepchniętego tekstu jest
    #: własnością uszkodzenia, o które w tym teście chodzi.
    PUSHED_OFF = [0.25, 0.50, 0.75]

    @pytest.mark.parametrize("fraction", PUSHED_OFF)
    def test_content_pushed_off_the_bottom_of_the_page(self, tmp_path, fraction):
        """A dedication composed against the bottom edge, shoved past it.

        Odsunięcie **wyliczane z pomiaru tego silnika**, nie wpisane z pamięci:
        strona źródłowa jest najpierw rysowana i mierzona, a dopiero z tego
        wychodzi, o ile przesunąć tekst, żeby zniknął zadany ułamek. Dzięki temu
        ten sam test opisuje to samo uszkodzenie na silniku, który rysuje
        inaczej — a nie cudzą przeglądarkę sprzed roku.
        """
        dedication = "".join(
            f"<p>Wiersz dedykacji numer {n}, dla tych, którzy zostali.</p>"
            for n in range(1, 7)
        )
        source = book(tmp_path / "a.epub", dedication, style="body{padding-top:500px}")

        # Gdzie ten silnik naprawdę stawia tekst. Bez tego kroku każda liczba
        # niżej jest zgadywaniem o cudzej maszynie.
        measured = render_fidelity.compare(source, source, viewports=((600, 800),), sample=0)
        ink = next(page.source_ink for page in measured.pages if page.source_ink)
        height, top = (ink.bottom - ink.top) * 800, ink.top * 800

        # Ile dołożyć do 500, żeby zniknął zadany ułamek tekstu — z geometrii,
        # a potem sprawdzone. Przewidywanie zakłada, że silnik po prostu
        # przesuwa treść w dół; pełne Chromium przycina o jakieś 80 px wcześniej,
        # więc pierwsze trafienie potrafi zepchnąć **całość**. Trzy próby wstecz
        # po ćwierci wysokości tekstu wystarczają na obu silnikach, a jeżeli nie
        # wystarczą, test powie o **swoim** założeniu, nie o bramie.
        padding = round(500 + (800 - top) - height * (1 - fraction))
        for _ in range(3):
            output = book(
                tmp_path / "b.epub", dedication, style=f"body{{padding-top:{padding}px}}"
            )
            result = gate(source, output)
            widoczne = next(
                (p.output_ink.coverage for p in result.pages if p.output_ink), 0
            )
            if widoczne > 0:
                break
            padding -= round(height / 4)

        # Założenie testu, sprawdzane zamiast zakładane. Test twierdzący
        # uszkodzenie tam, gdzie na tym silniku nic nie ubywa, oskarża bramę
        # o przeoczenie czegoś, czego nie ma — i tak wyglądało EF-055.
        page = next(p for p in result.pages if p.source_ink and p.output_ink)
        before, after = page.source_ink.coverage, page.output_ink.coverage
        assert before > after > 0, (
            f"odsunięcie {padding} px (cel: {fraction:.0%} poza stroną) daje na "
            f"tym silniku ({render.version()}) tusz {before:.4f} → {after:.4f}. "
            "To jest złe założenie testu, nie przeoczenie bramy."
        )

        assert not result.ok
        assert "mniej treści" in problems_of(result)

    def test_a_picture_squashed_out_of_shape(self, tmp_path):
        """A full-page illustration stretched to fit, which is the one shape of
        this that a structural check has no hope of seeing: the file is byte for
        byte the same picture."""
        from tests.factory import png_bytes

        picture = png_bytes()
        files = {"OEBPS/rys.png": picture}
        manifest = '<item id="p" href="rys.png" media-type="image/png"/>'
        source = book(
            tmp_path / "a.epub",
            '<p><img src="rys.png" alt="rysunek"/></p>',
            style="img{width:400px;height:400px}",
            extra_manifest=manifest,
            files=files,
        )
        output = book(
            tmp_path / "b.epub",
            '<p><img src="rys.png" alt="rysunek"/></p>',
            style="img{width:400px;height:80px}",
            extra_manifest=manifest,
            files=files,
        )
        result = gate(source, output)
        assert not result.ok
        assert "mniej treści" in problems_of(result)


class TestAnIdenticalBookIsSilent:
    def test_the_same_bytes_twice(self, tmp_path):
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        output = tmp_path / "b.epub"
        output.write_bytes(pathlib.Path(source).read_bytes())
        result = gate(source, str(output))
        assert result.ok
        assert all(page.difference == 0 for page in result.pages)

    def test_a_page_that_gained_content_is_not_a_defect(self, tmp_path):
        """The rule the real books forced. This program legitimately makes a
        page show *more* — an oversized cover fitted to the viewport is the
        commonest case — and that is a repair, not a regression."""
        keep = "".join(PARAGRAPHS.split("</p>")[:4]) + "</p>"
        source = book(tmp_path / "a.epub", keep)
        output = book(tmp_path / "b.epub", PARAGRAPHS)
        result = gate(source, output)
        assert result.ok, problems_of(result)
        assert any(page.notes for page in result.pages)


class TestTheEngineIsRecordedRatherThanAssumed:
    def test_the_version_travels_with_the_result(self, tmp_path):
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        result = gate(source, source)
        assert result.engine
        assert result.engine in result.summary()

    def test_two_engines_are_not_comparable(self):
        assert render.engine_matches("Chromium 141.0.7390.37", "Chromium 141.0.9999.1")
        assert not render.engine_matches("Chromium 141.0.7390.37", "Chromium 140.0.1.1")
        assert not render.engine_matches("", "Chromium 141.0.7390.37")


class TestWhenThereIsNoRenderer:
    def test_it_says_what_is_missing_rather_than_failing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "find_renderer", lambda: None)
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        result = render_fidelity.compare(source, source)
        assert not result.available
        assert not result.ok
        # Sentences somebody can act on, naming the variable that overrides it.
        assert render.ENV_BROWSER in result.reason
        assert len(result.reason) > 100


class TestWhichPagesAreLookedAt:
    def test_the_first_three_are_always_rendered(self):
        """Not a heuristic: the fixture profile for this finding names the cover
        and two title pages, and those are the pages whose full-bleed images
        crop and stretch."""
        chosen = render_fidelity._sample(50, 6)
        assert chosen[:3] == [0, 1, 2]
        assert len(chosen) <= 6

    def test_a_short_book_is_rendered_whole(self):
        assert render_fidelity._sample(4, 12) == [0, 1, 2, 3]

    def test_a_sample_of_zero_means_everything(self, tmp_path):
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        assert len(gate(source, source).pages) == 1


class TestReadingTheSpines:
    def test_the_pairing_follows_the_reading_order(self, tmp_path):
        """Measured on a real book before this was trusted: 29 documents to 29,
        name for name, with the output's renamed files landing opposite the
        source's originals. A comparison that paired the wrong pages would
        report nonsense with total confidence."""
        source = book(tmp_path / "a.epub", PARAGRAPHS)
        root = render_fidelity._extract(source, tmp_path / "x")
        spine = render_fidelity._spine_of(root)
        assert [p.name for p in spine] == ["r.xhtml"]

    def test_a_book_with_no_container_is_not_a_crash(self, tmp_path):
        broken = tmp_path / "broken.epub"
        write_zip(str(broken), {"nic.txt": b"nic"})
        assert render_fidelity._spine_of(
            render_fidelity._extract(broken, tmp_path / "y")
        ) == []


class TestMeasuringOnePage:
    def test_ink_finds_where_the_content_is(self, tmp_path):
        html = tmp_path / "p.html"
        html.write_bytes(page("<p>Tekst u góry.</p>"))
        shot = render.shoot(html, tmp_path / "p.png", viewport=(600, 800))
        ink = render.ink_of(shot)
        assert not ink.blank
        assert ink.top < 0.2, "text at the top of the page measured lower down"

    def test_an_empty_page_is_blank(self, tmp_path):
        html = tmp_path / "p.html"
        html.write_bytes(page(""))
        assert render.ink_of(render.shoot(html, tmp_path / "p.png")).blank

    def test_the_screenshot_is_the_viewport_and_not_the_whole_page(self, tmp_path):
        """Relied on by every measurement here. A full-page capture would make
        `Ink` fractions mean something different on each side of a comparison."""
        from PIL import Image

        html = tmp_path / "p.html"
        html.write_bytes(page(PARAGRAPHS * 4))
        shot = render.shoot(html, tmp_path / "p.png", viewport=(600, 400))
        with Image.open(shot) as image:
            assert image.size == (600, 400)


class TestNothingIsLookedForOnTheMachine:
    """This class used to assert the opposite, and the class it replaces is the
    point of the change.

    It held `windows_installs` to finding Edge under Program Files — added
    because a release build failed for want of a browser that was sitting right
    there on the disk. That was the correct fix for 0.2.25, when this program
    carried no engine. It stopped being correct the moment 0.2.26 put one in
    the installer, and the owner said so: *we have Chromium built in, what do we
    need an "optional" Edge for.*

    So the search is gone — `PATH`, Program Files, Playwright, the lot — and
    what is asserted now is its absence. A test that only checked the new path
    would leave the old one free to come back.
    """

    def test_the_search_apparatus_is_gone(self):
        for name in (
            "windows_installs", "_machine_candidates", "_NAMES",
            "_WINDOWS_PROGRAMS", "_PLAYWRIGHT", "ENV_BROWSER_WINS",
        ):
            assert not hasattr(render, name), (
                f"{name} is browser-hunting, and this program ships its own engine"
            )

    def test_the_source_does_not_reach_for_path_or_program_files(self):
        source = inspect.getsource(render)
        body = "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        for reached in ("shutil.which", "PROGRAMFILES", "PLAYWRIGHT_BROWSERS_PATH"):
            assert reached not in body, reached

    def test_what_we_carry_is_the_only_engine_when_we_carry_one(
        self, monkeypatch, tmp_path
    ):
        from epubforge import resources

        carried = tmp_path / "chrome-headless-shell"
        carried.write_text("", encoding="utf-8")
        carried.chmod(0o755)
        elsewhere = tmp_path / "msedge.exe"
        elsewhere.write_text("", encoding="utf-8")
        elsewhere.chmod(0o755)

        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)
        monkeypatch.setenv(render.ENV_BROWSER, str(elsewhere))
        assert render.chosen().path == carried
        assert render._candidates()[0] == carried

    def test_a_checkout_still_has_one_way_to_name_an_engine(
        self, monkeypatch, tmp_path
    ):
        """The one thing that is not removed, and the reason it is not: this
        project's own render tests, a `pip` install and a working copy all carry
        no engine, and with nothing to name them the check could never run
        anywhere but a release."""
        from epubforge import resources

        mine = tmp_path / "chrome-headless-shell"
        mine.write_text("", encoding="utf-8")
        mine.chmod(0o755)
        monkeypatch.setattr(resources, "bundled_renderer", lambda: None)
        monkeypatch.setenv(render.ENV_BROWSER, str(mine))

        picked = render.chosen()
        assert picked.path == mine
        assert picked.origin == "named"

