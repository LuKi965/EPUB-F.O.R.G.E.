"""K1 in the gate that decides whether a book is published.

WP-11 / EF-027. Two halves of one finding, and the second is the one that
matters.

**The count was never taken.** `balance.Side.text_characters` is declared,
serialised into every report and never assigned — it reads `0` in every balance
this program has ever produced. The field that says *how much text went in and
how much came out* has been answering zero since the day it was written.

**The check was never at the gate.** `fidelity.text_survives` is K1 measured,
and it was reachable only from a separate command and from the corpus. So the
publication gate — the thing that decides whether somebody's book is written to
disk — asked EPUBCheck whether the file is valid and asked the renderer whether
the pages still look the same, and did not ask whether the *text* was still
there. A book can lose a paragraph and be perfectly valid; it can lose one and
draw almost the same, because the sampled pages are not the page that lost it.

The invariant gate in front of the writer does catch a document that vanishes.
It does not catch a paragraph, and a paragraph is what a converter drops.

The first test here injects exactly that — one paragraph removed by a stage
that says nothing — and requires the book not to be published. Before this
commit it was published, and reported as a success.
"""

from __future__ import annotations

import time

import pytest

from epubforge import balance, typography
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.stages import DEFAULT_STAGES
from epubforge.stages.base import Stage
from epubforge.xhtml import local_name, parse
from tests.factory import make_legacy_epub, make_modern_epub


class DropsAParagraph(Stage):
    """One paragraph, quietly. No ledger entry, no finding, nothing.

    Deliberately the quietest loss there is: the document survives, so the
    invariant gate sees nothing missing; the resource count is unchanged, so the
    balance's resource arm closes; and the page it came from may not even be
    among the ones the render check samples.

    Injected into a book with **no watermark**, deliberately. The legacy fixture
    carries one, and removing or gathering a watermark is a text change the
    owner asked for — so the gate excuses it, and the injected loss would be
    forgiven for a reason that has nothing to do with the injected loss.
    """

    name = "test-drop-paragraph"
    mutates = True

    def run(self, ctx):
        for resource in ctx.book.resources.values():
            if not resource.is_content_doc:
                continue
            root, _mode = parse(resource.data)
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                if local_name(element).lower() != "p":
                    continue
                if not (element.text or "").strip():
                    continue
                parent = element.getparent()
                if parent is None:
                    continue
                parent.remove(element)
                from lxml import etree

                resource.data = etree.tostring(
                    root.getroottree(), xml_declaration=True, encoding="utf-8"
                )
                return


class TestAParagraphMayNotVanishQuietly:
    def test_the_book_is_not_published(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
            stages=(*DEFAULT_STAGES, DropsAParagraph),
        )
        assert not result.status.wrote_a_file, (
            "a paragraph left the book and nothing said so:\n"
            + result.report.to_text()
        )

    def test_and_the_report_says_what_went(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in2.epub"))
        result = rebuild(
            source,
            str(tmp_path / "out2.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
            stages=(*DEFAULT_STAGES, DropsAParagraph),
        )
        rules = {finding.rule for finding in result.report.findings if finding.rule}
        assert "package.text-lost" in rules, sorted(rules)
        said = result.report.to_text()
        assert "K1" in said or "tekst" in said.lower() or "text" in said.lower()

    def test_nothing_is_left_at_the_destination(self, tmp_path):
        """The refusal has to happen before `os.replace`, like every other gate,
        or the book that was already at that name is gone."""
        destination = tmp_path / "istnieje.epub"
        destination.write_bytes(b"stara ksiazka" * 40)
        source = make_modern_epub(str(tmp_path / "in3.epub"))
        rebuild(
            source,
            str(destination),
            Policy.preset("preserve", validate_before_publish="off"),
            stages=(*DEFAULT_STAGES, DropsAParagraph),
        )
        assert destination.read_bytes() == b"stara ksiazka" * 40


class TestAnOrdinaryBookIsNotRefusedByThis:
    """The other half, and the one that keeps the gate from being a rule against
    rebuilding anything. A rebuild legitimately changes spacing, generates a
    navigation document and in strict may unwrap an element — none of which is
    a word leaving the book."""

    @pytest.mark.parametrize("mode", ["minimal", "preserve", "strict"])
    def test_a_clean_book_publishes(self, tmp_path, mode):
        source = make_modern_epub(str(tmp_path / f"{mode}-in.epub"))
        result = rebuild(
            source,
            str(tmp_path / f"{mode}-out.epub"),
            Policy.preset(mode, validate_before_publish="off"),
        )
        assert result.status.wrote_a_file, result.report.to_text()

    def test_a_legacy_book_publishes_too(self, tmp_path, legacy_epub):
        result = rebuild(
            legacy_epub,
            str(tmp_path / "legacy.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert result.status.wrote_a_file, result.report.to_text()


class TestACharacterXmlCannotWriteIsNotTextThatCanBeLost:
    """Znaleziona na prawdziwej książce z półki właściciela, po tym jak brama
    K1 została uszczelniona.

    Book 8 z półki właściciela (odcisk `ed66165ab304a4f6`) niesie po jednym
    znaku sterującym w dwóch rozdziałach — przyszły ze źródła.
    Etap treści je usuwa — nie są tekstem, XML 1.1 wymaga dla nich escapowania
    a walidator zgłasza je na dokumentach treści — i mówi o tym w raporcie
    z liczbą i nazwą dokumentu. Do dnia uszczelnienia bramy
    książka wychodziła z ostrzeżeniem; po uszczelnieniu została **odmówiona** —
    zgodnie z literą K1 i wbrew jej celowi, bo z 776 555 znaków jej tekstu nie
    zginął ani jeden.

    Poprawka nie dopisuje kolejnej nazwy do listy reguł, którym wolno usuwać
    tekst. Ta lista ma dokładnie tę wadę, przez którą brama była rozbrojona:
    obecność reguły gdziekolwiek w raporcie usprawiedliwia stratę gdziekolwiek
    indziej. Zamiast tego K1 porównuje **tekst, który poprawny EPUB może
    unieść** — i znak bez reprezentacji do tego zbioru nie należy po żadnej ze
    stron.
    """

    def _book_with_a_control_character(self, path: str, character: bytes = b"\xc2\x8f") -> str:
        import zipfile

        source = make_modern_epub(path + ".clean")
        entries: dict[str, bytes] = {}
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if name == "mimetype":
                    continue  # write_zip kładzie go sam, pierwszy i bez kompresji
                entries[name] = archive.read(name)
        chapter = next(
            name for name in entries if name.endswith(".xhtml") and b"<p>" in entries[name]
        )
        # U+008F, dokładnie ten, który niesie prawdziwa książka. Należy do
        # bloku C1: XML 1.0 wpuszcza go do drzewa, więc parser go **zachowuje** —
        # i dlatego dochodzi do etapu treści, w przeciwieństwie do 0x0B, na
        # którym lxml podnosi wyjątek i sprawa kończy się przed bramą.
        marked = entries[chapter].replace(b"<p>", b"<p>" + character, 1)
        assert marked != entries[chapter], "fixture przestał mieć akapit"
        entries[chapter] = marked
        from tests.factory import write_zip

        return write_zip(path, entries)

    def test_the_book_is_still_published(self, tmp_path):
        source = self._book_with_a_control_character(str(tmp_path / "sterujacy.epub"))
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert result.status.wrote_a_file, result.report.to_text()

    def test_and_the_report_still_says_the_character_went(self, tmp_path):
        """Cichej straty tu nie ma i nie może być: brama przestaje pytać o ten
        znak dokładnie dlatego, że mówi o nim etap treści."""
        source = self._book_with_a_control_character(str(tmp_path / "sterujacy.epub"))
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        rules = {finding.rule for finding in result.report.findings}
        assert "xhtml.forbidden-characters-removed" in rules, sorted(rules)

    def test_a_windows_quotation_mark_is_not_a_control_character(self, tmp_path):
        """Kontrola, przez której brak przepuściłem książkę gubiącą 18 545 znaków.

        Pierwsza wersja tej poprawki składała K1 przez `xmlchars.legal`, czyli
        przez zbiór, który obejmuje **cały** blok C1. Na kolekcji właściciela
        siedzi książka z 18 545 znakami `0x93`, `0x94`, `0x92` i `0x97` — to są
        „ ” ‘ i —, cudzysłowy i myślniki zapisane w Windows-1252 i odczytane jak
        Latin-1. K1 słusznie odmawiało tej książki; po złożeniu przestało.

        Zbiór do porównań nazywa się dlatego `NEVER_TEXT` i jest węższy: zostają
        w nim tylko pozycje, których cp1252 **nie definiuje**. Za resztą stoi
        znak przestankowy, a znak przestankowy jest treścią (S-03).
        """
        source = self._book_with_a_control_character(
            str(tmp_path / "cudzyslow.epub"), character=b"\xc2\x93"
        )
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert not result.status.wrote_a_file, (
            "cudzysłów z Windows-1252 zniknął i nikt tego nie zatrzymał:\n"
            + result.report.to_text()
        )

    def test_a_real_paragraph_still_stops_the_book(self, tmp_path):
        """Kontrola przeciwna. Zwinięcie K1 do „tekstu, który da się zapisać"
        byłoby warte tyle, ile jego zdolność do dalszego odmawiania — więc ta
        sama książka, z tym samym znakiem sterującym, **plus** etapem gubiącym
        akapit, ma zostać odmówiona."""
        source = self._book_with_a_control_character(str(tmp_path / "sterujacy.epub"))
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
            stages=[*DEFAULT_STAGES, DropsAParagraph],
        )
        assert not result.status.wrote_a_file, result.report.to_text()


class TestTheCharactersAreActuallyCounted:
    """EF-027's first half. The field was declared, serialised and never
    assigned, so every balance this program has produced says the book contains
    zero characters."""

    def test_the_count_is_not_zero(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "znaki.epub"))
        result = rebuild(
            source,
            str(tmp_path / "znaki-out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        recorded = result.report.balance.as_dict()
        assert recorded["before"]["text_characters"] > 0, recorded
        assert recorded["after"]["text_characters"] > 0, recorded

    def test_the_two_sides_agree_on_an_ordinary_rebuild(self, tmp_path, legacy_epub):
        result = rebuild(
            legacy_epub,
            str(tmp_path / "zgoda.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        recorded = result.report.balance.as_dict()
        before = recorded["before"]["text_characters"]
        after = recorded["after"]["text_characters"]
        assert after >= before, recorded

    def test_it_counts_after_normalising(self):
        """Counted through `typography.canonical`, so that a rebuild which
        collapses two spaces into one does not read as two characters lost.

        The specification named `typography.fold`; there is no such function.
        `canonical` is the normalisation this module actually has and the one
        every other comparison in the program already goes through, so using it
        keeps one definition of "the same text" rather than adding a second.
        """
        assert balance.characters_in("a  b\n\nc") == len(typography.canonical("a  b\n\nc"))

    def test_a_book_with_no_text_counts_zero_rather_than_failing(self):
        from epubforge.model import Book, Metadata

        empty = Book(metadata=Metadata(titles=["T"], language="pl"))
        assert balance.Side.of(empty).text_characters == 0


class TestTheGateDoesNotCostTheBook:
    """The acceptance asks for a number rather than an impression: the rebuild
    may not get more than a fifth slower for this.

    Measured on the suite's own legacy fixture rather than on a real book,
    because a real book is on the owner's disk and this test runs everywhere.
    The shape of the cost is the same — one pass over every document's text on
    each side, plus `text_survives` reading both archives once.
    """

    def test_the_rebuild_does_not_get_a_fifth_slower(self, tmp_path):
        source = make_legacy_epub(str(tmp_path / "czas.epub"))
        policy = Policy.preset("preserve", validate_before_publish="off")

        started = time.perf_counter()
        for run in range(3):
            rebuild(source, str(tmp_path / f"czas-{run}.epub"), policy)
        with_gate = (time.perf_counter() - started) / 3

        # Not a comparison against a stored number, which would rot: against the
        # same rebuild with the text gate switched off, measured in the same
        # process on the same machine in the same second.
        bare = Policy.preset(
            "preserve", validate_before_publish="off", verify_text_survives=False
        )
        started = time.perf_counter()
        for run in range(3):
            rebuild(source, str(tmp_path / f"bez-{run}.epub"), bare)
        without_gate = (time.perf_counter() - started) / 3

        assert with_gate < without_gate * 1.20 + 0.05, (
            f"z bramką {with_gate:.3f}s, bez {without_gate:.3f}s"
        )

    def test_and_it_can_be_switched_off(self):
        """Every gate in this program can be, and this one is no different —
        `Policy` is where the owner's choices live, not a constant in the code.
        """
        assert Policy.preset("preserve").verify_text_survives is True
        assert (
            Policy.preset("preserve", verify_text_survives=False).verify_text_survives
            is False
        )


class TestTheCounterCountsTextAndOnlyText:
    """Dwa defekty licznika znaków, oba znalezione przy EF-041 i oba takie, że
    ukrywały się nawzajem.

    Test „obie strony się zgadzają" przechodził **przez przypadek**: wstrzykiwany
    blok CSS dokładał do wyniku mniej więcej tyle znaków, ile gubiła nieodkodowana
    encja po stronie źródła. Naprawa jednego z nich odsłoniła drugi — a naprawa
    obu daje liczbę, która wreszcie znaczy to, co obiecuje.
    """

    def test_css_in_a_style_block_is_not_the_books_text(self):
        """`<style>` siedzi w dokumencie i nie czyta go nikt. Zdejmowanie samych
        znaczników zostawiało jego **zawartość**, więc im bliżej program podszedł
        do dokumentu, tym więcej „tekstu" książka pozornie zyskiwała."""
        from epubforge.balance import _characters_of

        book = _one_document(
            "<html><head><style>body { color: red; margin: 0 }</style></head>"
            "<body><p>Tekst</p></body></html>"
        )
        assert _characters_of(book) == len("Tekst")

    def test_a_script_is_not_the_books_text_either(self):
        from epubforge.balance import _characters_of

        book = _one_document(
            "<html><body><script>var x = 1; alert('nie tekst');</script>"
            "<p>Tekst</p></body></html>"
        )
        assert _characters_of(book) == len("Tekst")

    def test_an_entity_counts_as_the_character_it_stands_for(self):
        """`Rozdzia&#322;` i `Rozdział` to to samo słowo. Licznik porównywał
        stronę zakodowaną z odkodowaną i różnicę nazywał utraconym tekstem —
        na książkach legacy, czyli tych, dla których ten program powstał."""
        from epubforge.balance import _characters_of

        encoded = _one_document("<html><body><p>Rozdzia&#322;</p></body></html>")
        decoded = _one_document("<html><body><p>Rozdział</p></body></html>")
        assert _characters_of(encoded) == _characters_of(decoded) == len("Rozdział")

    def test_a_named_entity_too(self):
        from epubforge.balance import _characters_of

        assert _characters_of(
            _one_document("<html><body><p>a&nbsp;b&amp;c</p></body></html>")
        ) == _characters_of(_one_document("<html><body><p>a b&c</p></body></html>"))

    def test_and_escaped_markup_in_the_text_stays_text(self):
        """`&lt;p&gt;` w czyimś tekście jest tekstem. Odkodowanie **przed**
        zdjęciem znaczników zrobiłoby z niego znacznik do zjedzenia."""
        from epubforge.balance import _characters_of

        book = _one_document("<html><body><p>pisz &lt;p&gt; tak</p></body></html>")
        assert _characters_of(book) == len("pisz <p> tak")


def _one_document(markup: str):
    """Najmniejsza atrapa, jaką `_characters_of` umie policzyć: jeden dokument
    w grzbiecie."""
    class Resource:
        is_content_doc = True
        def __init__(self, data): self.data = data

    class Item:
        path = "a.xhtml"

    class Book:
        spine = [Item()]
        def get(self, path): return Resource(markup.encode("utf-8"))

    return Book()


class TestOnlyRulesThatActuallyRemoveTextExcuseALoss:
    """Znalezione na półce 93 książek, wydanie 0.2.28.

    Bramka K1 pyta, czy w raporcie jest **jakakolwiek** reguła ze zgodą — nie
    czy ta reguła tłumaczy stratę. Dopóki na liście stała konsolidacja znaku
    wodnego, która **niczego nie usuwa** i jest domyślnym trybem, bramka była
    rozbrojona na każdej książce niosącej znacznik: książka, która
    skonsolidowała znak wodny i zgubiła dwa znaki gdzie indziej, dostawała
    ostrzeżenie i była zapisywana, cokolwiek te znaki zjadło.

    Jedna książka wyszła `-2` z `text_invariant: False`, usprawiedliwiona
    konsolidacją, która nie zabrała ani jednego znaku.
    """

    def test_consolidation_is_not_a_licence_to_lose_text(self):
        from epubforge.pipeline import REMOVES_TEXT_ON_PURPOSE

        assert "xhtml.watermark-consolidated" not in REMOVES_TEXT_ON_PURPOSE

    def test_the_modes_that_do_move_the_token_are_still_there(self):
        """Druga strona: `gather` i `remove` naprawdę wyjmują token z przepływu,
        więc bez nich bramka odmawiałaby książki, o którą ktoś poprosił."""
        from epubforge.pipeline import REMOVES_TEXT_ON_PURPOSE

        assert "xhtml.watermark-relocated" in REMOVES_TEXT_ON_PURPOSE
        assert "xhtml.watermark-removed" in REMOVES_TEXT_ON_PURPOSE

    def test_every_excusing_rule_belongs_to_a_stage_that_can_remove_text(self):
        """Reguła, której kod nigdy nie usuwa ani nie przenosi tekstu, nie ma
        prawa usprawiedliwiać straty. Sprawdzane przez nazwę etapu, bo to
        jedyne, co da się sprawdzić bez uruchomienia przebudowy."""
        from epubforge.pipeline import REMOVES_TEXT_ON_PURPOSE

        for rule in REMOVES_TEXT_ON_PURPOSE:
            assert any(
                word in rule
                for word in ("removed", "relocated", "joined", "notice")
            ), f"{rule}: nazwa nie mówi, że cokolwiek ubywa albo się przenosi"

    def test_consolidation_really_does_leave_the_token_alone(self):
        """Dowód na to, na czym stoi cała ta poprawka — czytany z kodu, bo
        gdyby konsolidacja kiedyś zaczęła ruszać tekst, jej nieobecność na
        liście stałaby się defektem w drugą stronę."""
        import pathlib
        import re

        source = (
            pathlib.Path(__file__).parent.parent
            / "epubforge" / "stages" / "content.py"
        ).read_text(encoding="utf-8")
        branch = re.search(
            r'if mode == "consolidate":(.*?)\n            else:', source, re.S
        )
        assert branch, "gałąź konsolidacji zmieniła kształt — sprawdź ręcznie"
        body = branch.group(1)
        for forbidden in (".text", ".tail", "remove(", "displaced"):
            assert forbidden not in body, (
                f"konsolidacja rusza teraz tekst ({forbidden}) — jeśli tak ma "
                "być, musi wrócić na listę REMOVES_TEXT_ON_PURPOSE"
            )
