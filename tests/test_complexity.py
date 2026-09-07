"""Złożoność, której nikt nie liczy, rośnie — to jest ten sam kształt co
szerokie `except` (`tests/test_broad_exceptions.py`).

Audyt 2026-09-05 nazwał dług: *„funkcje o złożoności D (22)"*. Do 2026-09-07
było ich **33**, bo między jednym audytem a drugim nikt tej liczby nie
sprawdzał. Ten plik nie każe niczego przepisywać — mówi tylko dwie rzeczy,
których do dziś nie mówił nikt:

1. **nic nie ma prawa być gorsze niż D.** `PdfStage.run` miało E (31): trzy
   niezwiązane roboty w jednej metodzie — znalezienie żywych pagin, pytanie
   i dwie ścieżki odpowiedzi. Rozdzielone na `_running_heads`, `_answer`,
   `_keep` i `_take_out` (przeniesienie, nie przepisanie: sygnatury korpusu
   publicznego przechodzą bez nagrywania czegokolwiek), i to jest granica,
   którą ten test trzyma;
2. **ich liczba może spaść i nie może urosnąć.** Para zapadek jak przy
   katalogu reguł: jedna pilnuje progu, druga pilnuje, żeby próg był
   uczciwy.

Czego ten plik **nie** twierdzi: że D jest wadą. Parser cudzego PDF-a
(`pdf._blocks`, `read_pdf`) czy model kaskady CSS są rozgałęzione, bo
rozgałęziony jest materiał; rozbicie takiej funkcji na pięć nazwanych
kawałków, z których żaden nie znaczy nic osobno, kupuje ładniejszą liczbę
za gorszy kod. Zapadka jest po to, żeby wybór był świadomy, a nie po to,
żeby go wymusić.
"""

from __future__ import annotations

import pathlib

import pytest

radon = pytest.importorskip("radon.complexity", reason="radon nie jest zainstalowany w tym środowisku")

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "epubforge"

#: Ile bloków (funkcji, metod, klas) ma dziś ocenę D. Wolno zejść, nie wolno
#: urosnąć — a kiedy schodzi, ta liczba idzie w dół razem z nim.
COMPLEX_TODAY = 33

#: Najgorsza dopuszczalna ocena. Od `e887252` w pakiecie nie ma ani jednego
#: bloku gorszego niż D; ta stała jest jedyną rzeczą, która pilnuje, żeby
#: następne E ktoś zobaczył.
WORST_ALLOWED = "D"


def _blocks() -> list:
    """`(ocena, złożoność, plik, nazwa)` dla każdego bloku pakietu."""
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for block in radon.cc_visit(path.read_text(encoding="utf-8")):
            name = ".".join(part for part in (getattr(block, "classname", None), block.name) if part)
            found.append((radon.cc_rank(block.complexity), block.complexity,
                          str(path.relative_to(PACKAGE.parent)), name))
    return found


def _hard() -> list:
    return [block for block in _blocks() if block[0] >= WORST_ALLOWED]


class TestNothingIsWorseThanD:
    def test_no_block_is_rated_e_or_worse(self):
        """E to nie „trochę więcej niż D" — to metoda, w której siedzi kilka
        robót naraz i której nikt nie przeczyta w całości."""
        worse = [block for block in _blocks() if block[0] > WORST_ALLOWED]
        assert not worse, "\n".join(
            f"{path}: {name} — {rank} ({score})" for rank, score, path, name in sorted(worse)
        )


class TestTheHardOnesCannotMultiply:
    def test_the_count_may_fall_and_may_not_rise(self):
        count = len(_hard())
        assert count <= COMPLEX_TODAY, (
            f"{count} bloków ma ocenę {WORST_ALLOWED} lub gorszą, wobec {COMPLEX_TODAY}. "
            "Nowa funkcja tej wielkości ma być rozdzielona przy pisaniu, nie przy następnym audycie."
        )

    def test_the_recorded_number_is_honest(self):
        """Jeśli liczba spadła, stała jest nieaktualna i zapadka przestaje
        zapadać."""
        count = len(_hard())
        assert count == COMPLEX_TODAY, (
            f"bloków o ocenie {WORST_ALLOWED} lub gorszej jest teraz {count}; ustaw COMPLEX_TODAY na {count}."
        )
