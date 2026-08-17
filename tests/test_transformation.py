"""Kontrakt kroku transformacji — BA-2026-003, połowa niewidoczna.

Ustalenie mówi: *etapy bezpośrednio mutują `Book`*, a rejestr powstaje **przy**
mutacji, nie przed nią — więc transformacja, która niczego nie zmieniła, i taka,
która zmieniła i zapomniała o wpisie, wyglądają identycznie.

Ten plik sprawdza najmniejszą rzecz, która czyni je rozróżnialnymi, i **nie
udaje**, że jest czymś więcej. Nie ma tu typowanego grafu zależności ani
przepisanego potoku; jest kontrakt, przez który transformacja musi przejść,
żeby dotknąć dokumentu, i który sam zdejmuje jej robotę, gdy warunek końcowy nie
wychodzi.

Przez kontrakt idzie dziś **jedna** transformacja: naprawa kodowania (EF-050).
Wybrana nieprzypadkowo — jest najnowsza, zmienia znaki tekstu i jest
nieodwracalna z samego wyniku.
"""

from __future__ import annotations

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
