"""Kontrakt kroku transformacji — BA-2026-003, połowa niewidoczna.

Ustalenie mówi: *etapy bezpośrednio mutują `Book`*, a rejestr powstaje **przy**
mutacji, nie przed nią — więc transformacja, która niczego nie zmieniła, i taka,
która zmieniła i zapomniała o wpisie, wyglądają identycznie.

Ten plik sprawdza najmniejszą rzecz, która czyni je rozróżnialnymi, i **nie
udaje**, że jest czymś więcej. Nie ma tu typowanego grafu zależności ani
przepisanego potoku; jest kontrakt, przez który transformacja musi przejść,
żeby dotknąć dokumentu, i który sam zdejmuje jej robotę, gdy warunek końcowy nie
wychodzi.

Przez kontrakt idą **wszystkie** transformacje, które zmieniają znaki tekstu:
naprawa kodowania (EF-050), łączenie przeniesień, usuwanie zdań księgarni oraz
przeniesienie i usunięcie znaku wodnego. To nie jest wybór wygodnych — to jest
zamknięta klasa, i ostatnia klasa w tym pliku pilnuje, żeby **nic z niej nie
zostało na zewnątrz**. Migracja ma być liczbą w teście, a nie zdaniem w notatce.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge.transformation import (
    PostconditionFailed,
    Transformation,
    carry_out,
)


def krok(*, przed=lambda: True, po=lambda: True) -> Transformation:
    return Transformation(
        rule="test.rule",
        target="OEBPS/rozdzial.xhtml",
        precondition=przed,
        postcondition=po,
    )


class TestThePreconditionIsAQuestionAndNotAnAlarm:
    """Fałsz przy warunku wstępnym znaczy „ta książka tego nie ma" — czyli
    zwykłą odpowiedź, a nie usterkę. Traktowanie go jak błędu zamieniłoby każdą
    zdrową książkę w ostrzeżenie."""

    def test_nothing_runs_and_nothing_is_reported(self):
        slady = []
        wynik = carry_out(
            krok(przed=lambda: False),
            snapshot=lambda: slady.append("zdjecie") or b"",
            restore=lambda data: slady.append("odlozenie"),
            mutate=lambda: slady.append("mutacja") or 1,
        )
        assert wynik == 0
        assert slady == [], "coś się wydarzyło mimo niespełnionego warunku"


class TestThePostconditionCostsTheTransformationItsWork:
    def test_the_document_comes_back_byte_for_byte(self):
        """Zdjęcie przez odłożenie bajtów, a nie przez operację odwrotną:
        odwracanie zmiany wymaga wiedzy o tym, co się zmieniło — czyli
        dokładnie tego, czego brak jest tutaj defektem."""
        stan = {"dane": b"<html>oryginal</html>"}

        def mutuj() -> int:
            stan["dane"] = b"<html>polowicznie zmienione</html>"
            return 3

        with pytest.raises(PostconditionFailed):
            carry_out(
                krok(po=lambda: False),
                snapshot=lambda: stan["dane"],
                restore=lambda data: stan.__setitem__("dane", data),
                mutate=mutuj,
            )
        assert stan["dane"] == b"<html>oryginal</html>"

    def test_and_it_says_which_rule_and_where(self):
        with pytest.raises(PostconditionFailed) as podniesione:
            carry_out(
                krok(po=lambda: False),
                snapshot=lambda: b"",
                restore=lambda data: None,
                mutate=lambda: 1,
            )
        powiedziane = str(podniesione.value)
        assert "test.rule" in powiedziane
        assert "OEBPS/rozdzial.xhtml" in powiedziane


class TestASatisfiedContractIsInvisible:
    """Kontrakt, który zmienia zachowanie zdrowej transformacji, jest kosztem
    bez pokrycia. Ta ma wyjść tak, jakby go nie było."""

    def test_the_count_is_the_mutation_s_own(self):
        assert (
            carry_out(
                krok(),
                snapshot=lambda: b"",
                restore=lambda data: None,
                mutate=lambda: 17,
            )
            == 17
        )

    def test_nothing_is_restored(self):
        odlozone = []
        carry_out(
            krok(),
            snapshot=lambda: b"cokolwiek",
            restore=lambda data: odlozone.append(data),
            mutate=lambda: 1,
        )
        assert not odlozone


class TestTheEncodingRepairGoesThroughIt:
    """Dowód, że kontrakt jest podłączony do czegoś prawdziwego, a nie stoi
    obok programu jako ładny plik."""

    def test_the_stage_builds_a_transformation(self):
        import pathlib

        source = (
            pathlib.Path(__file__).parent.parent
            / "epubforge" / "stages" / "content.py"
        ).read_text(encoding="utf-8")
        assert "carry_out(" in source
        assert "Transformation(" in source

    def test_the_postcondition_demands_every_character(self):
        """Słabszy warunek — „nie wywróciło się" — przepuściłby tłumaczenie,
        które ominęło połowę drzewa, a to jest ta cicha połowiczna zmiana,
        przed którą ustalenie ostrzega."""
        import pathlib

        source = (
            pathlib.Path(__file__).parent.parent
            / "epubforge" / "stages" / "content.py"
        ).read_text(encoding="utf-8")
        assert "postcondition=lambda: not mojibake.census(root)" in source

    def test_a_reverted_repair_has_a_rule_of_its_own(self):
        """Zdjęta naprawa nie może być ciszą: człowiek odpowiedział „napraw"
        i ma prawo wiedzieć, że nie naprawiono."""
        from epubforge import rules

        for language in ("pl", "en"):
            assert "xhtml.mojibake-reverted" in rules.CATALOGUES[language]


class TestTheMigrationIsVisibleAndCannotQuietlyStop:
    """BA-2026-003 jest **migracją**, nie jedną poprawką, więc jej stan ma być
    liczbą w teście, a nie zdaniem w notatce.

    Kolejność przenoszenia nie jest dowolna: idą najpierw te, które zmieniają
    **znaki tekstu** i są nieodwracalne z samego wyniku, bo tam pomyłka kosztuje
    czytelnika, a nie walidator.
    """

    #: Ile **miejsc wywołania** kontraktu jest dziś w kodzie. Nie to samo, co
    #: liczba reguł niżej: przeniesienie i usunięcie znaku wodnego to jedna
    #: funkcja i jedno wywołanie, a dwie reguły — bo różnią się tylko tym, czy
    #: token ląduje w nagłówku, czy nigdzie. Rozdzielenie ich na dwa wywołania
    #: byłoby powtórzeniem tego samego warunku końcowego dwa razy.
    #:
    #: **Opuszczenie tej liczby znaczy, że któraś wypadła** — a to jest dokładnie
    #: ten cichy krok wstecz, przed którym ten plik istnieje.
    ON_THE_CONTRACT = 4

    #: Reguły, które przez niego idą. Wypisane, żeby błąd mówił **która**
    #: wypadła, a nie tylko że jest ich mniej.
    MIGRATED = (
        "xhtml.mojibake-translated",
        "hyphens.joined",
        "xhtml.shop-notice-removed",
        "xhtml.watermark-relocated",
        "xhtml.watermark-removed",
    )

    def call_sites(self) -> str:
        root = pathlib.Path(__file__).parent.parent / "epubforge"
        return "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*.py"))
            if path.name != "transformation.py"
        )

    def test_the_count_has_not_fallen(self):
        source = self.call_sites()
        found = source.count("carry_out(")
        assert found >= self.ON_THE_CONTRACT, (
            f"{found} wywołań kontraktu, było {self.ON_THE_CONTRACT} — "
            "któreś wypadło"
        )

    def test_and_the_number_is_honest(self):
        source = self.call_sites()
        found = source.count("carry_out(")
        assert found == self.ON_THE_CONTRACT, (
            f"{found} wywołań kontraktu; ustaw ON_THE_CONTRACT na {found}"
        )

    def test_each_named_rule_is_still_there(self):
        source = self.call_sites()
        for rule in self.MIGRATED:
            assert rule in source, f"{rule} zeszła z kontraktu"

    def test_nothing_that_changes_text_is_left_off_it(self):
        """To jest właściwe kryterium zamknięcia dla tej połowy BA-2026-003,
        i dlatego jest tu zapisane jako pusty zbiór, a nie jako lista wyjątków.

        Transformacja zmieniająca **znaki tekstu** jest jedyną klasą, w której
        pomyłkę widzi czytelnik, a nie walidator. Dopóki którakolwiek z nich
        mutuje książkę wprost, nie da się odróżnić transformacji, która niczego
        nie zmieniła, od takiej, która zmieniła i zapomniała o wpisie — czyli
        dokładnie tego, o czym mówi ustalenie.

        Gdy ten test zacznie padać, znaczy to, że doszła nowa transformacja
        kasująca albo zmieniająca tekst i **nie została przepuszczona przez
        kontrakt**. Odpowiedzią jest przepuścić ją, nie dopisać do wyjątków.
        """
        from epubforge.pipeline import REMOVES_TEXT_ON_PURPOSE

        zmieniajace_tekst = set(REMOVES_TEXT_ON_PURPOSE) | {"xhtml.mojibake-translated"}
        zostale = zmieniajace_tekst - set(self.MIGRATED)
        assert not zostale, f"zmieniają tekst i nie są na kontrakcie: {sorted(zostale)}"

    def test_the_revert_says_so_in_both_languages(self):
        """Zdjęta transformacja ma zostawić ślad, i to w obu katalogach —
        cicha rezygnacja wygląda w raporcie tak samo jak brak powodu do zmiany.
        """
        from epubforge import rules

        for language in rules.CATALOGUES:
            assert "xhtml.watermark-reverted" in rules.CATALOGUES[language]

    def test_each_of_them_is_in_the_machine_readable_ledger(self):
        """Druga połowa kryterium zamknięcia BA-2026-003, i ta, o którą było
        łatwiej się potknąć.

        Ustalenie prosi o **bilans, który da się zsumować**, nie o zdanie
        w raporcie. Trzy transformacje zabierające czytelnikowi znaki z oczu —
        zdanie księgarni i znak wodny w obu trybach — miały zdanie i nie miały
        wpisu w bilansie. Czyli akurat te, dla których to ustalenie powstało,
        były poza rejestrem, który miał być jego odpowiedzią.

        Sprawdzane przez składnię, nie wyrażeniem regularnym: identyfikator
        bywa trzecim argumentem pozycyjnym, a wyrażenie po `rule=` bywa
        wyliczane.
        """
        import ast

        root = pathlib.Path(__file__).parent.parent / "epubforge"
        w_bilansie: set[str] = set()
        for path in sorted(root.rglob("*.py")):
            drzewo = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(drzewo):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "attr", getattr(node.func, "id", None)) != "changed":
                    continue
                nazwa = {k.arg: k.value for k in node.keywords}.get("rule")
                if isinstance(nazwa, ast.Constant) and isinstance(nazwa.value, str):
                    w_bilansie.add(nazwa.value)

        brakujace = sorted(set(self.MIGRATED) - w_bilansie)
        assert not brakujace, (
            f"zmieniają tekst i nie ma ich w bilansie zmian: {brakujace}"
        )
