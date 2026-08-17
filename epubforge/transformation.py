"""Warunek wstępny → mutacja → warunek końcowy, jako dane, nie jako zwyczaj.

BA-2026-003, połowa niewidoczna. Widoczną — plan wypisany przed zapisem — robi
`--plan`; ta odpowiada na drugie zdanie ustalenia: *etapy bezpośrednio mutują
`Book`*, a rejestr powstaje **przy** mutacji, nie przed nią. Skutek jest taki,
że dwa przypadki wyglądają identycznie:

* transformacja niczego nie zmieniła,
* transformacja coś zmieniła i zapomniała o wpisie.

**Czym ten plik nie jest.** Nie jest typowanym grafem zależności ani przepisaniem
potoku, których chciał audyt zewnętrzny. Jest najmniejszą rzeczą, która czyni
tamte dwa przypadki rozróżnialnymi: kontrakt, przez który transformacja
**musi** przejść, żeby dotknąć dokumentu, i który sam zdejmuje jej robotę, gdy
warunek końcowy nie wychodzi.

**Dlaczego zdjęcie jest bajtowe, a nie „odwrotna operacja".** Odwracanie zmiany
wymaga wiedzy o tym, co się zmieniło — czyli dokładnie tego, czego brak jest
tutaj defektem. Zdjęcie przez odłożenie oryginalnych bajtów działa niezależnie
od tego, co transformacja zrobiła, i jest sprawdzalne porównaniem: dokument po
wycofaniu ma być **bajt w bajt** tym, czym był.

**Zakres na dziś, i to jest uczciwa granica:** przez ten kontrakt idzie naprawa
kodowania (EF-050) — najnowsza i jedyna nieodwracalna zmiana znaków tekstu,
jaką ten program wykonuje sam z siebie. Reszta etapów mutuje jak dotąd. Pakiet
jest migracją, nie przepisaniem, i sygnatury korpusu mają przez całą migrację
zostać bajtowo identyczne.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class PreconditionFailed(Exception):
    """Transformacja nie miała prawa się zacząć."""


class PostconditionFailed(Exception):
    """Transformacja się odbyła i nie osiągnęła tego, co obiecywała."""


@dataclass(frozen=True)
class Transformation:
    """Jedna zmiana, opisana **zanim** się wydarzy.

    Pola są tym, o co prosiło ustalenie i audyt: co, na czym, pod jakim
    warunkiem, z jakim skutkiem, czy da się cofnąć i czym ryzykuje. Trzy z nich
    są funkcjami, bo warunek zapisany zdaniem jest komentarzem, a warunek
    zapisany funkcją jest sprawdzany.
    """

    #: Reguła raportu, którą ta zmiana się przedstawia. Jedno miejsce prawdy
    #: o tym, jak nazywa się to, co się dzieje.
    rule: str
    #: Czego dotyczy — ścieżka dokumentu albo nazwa pola.
    target: str
    #: Czy w ogóle jest co robić. Fałsz **nie jest błędem**: to jest zwykła
    #: odpowiedź „ta książka tego nie ma".
    precondition: Callable[[], bool]
    #: Czy po zmianie jest tak, jak miało być. Fałsz **jest** błędem i kosztuje
    #: transformację jej robotę.
    postcondition: Callable[[], bool]
    #: Czy da się to cofnąć, patrząc na sam wynik. Nie ma nic wspólnego
    #: z wycofaniem tutaj: to jest odpowiedź dla czytelnika raportu.
    reversible: bool = True


def carry_out(
    transformation: Transformation,
    snapshot: Callable[[], bytes],
    restore: Callable[[bytes], None],
    mutate: Callable[[], int],
) -> int:
    """Wykonaj *transformation*, albo nie zostaw po niej śladu.

    Zwraca, ile rzeczy zmieniła — zero znaczy, że warunek wstępny nie był
    spełniony i nic się nie stało.

    `snapshot` i `restore` są podane przez wołającego, bo tylko on wie, co jest
    jednostką pracy: bajty dokumentu, tekst arkusza, wartość pola. Ten plik nie
    zna książki i nie powinien jej znać.
    """
    if not transformation.precondition():
        return 0

    before = snapshot()
    changed = mutate()
    if not transformation.postcondition():
        restore(before)
        raise PostconditionFailed(
            f"{transformation.rule} na {transformation.target}: "
            "warunek końcowy nie wyszedł, zmiana została zdjęta"
        )
    return changed


__all__ = [
    "PostconditionFailed",
    "PreconditionFailed",
    "Transformation",
    "carry_out",
]
