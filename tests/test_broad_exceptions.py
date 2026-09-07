"""`except Exception` — każdy z powodem, i ani jednego więcej niż dziś.

Audyt 2026-09-05 nazwał ten dług i **nie** zalecił, co z nim zrobić: 55
szerokich handlerów, „każde do sklasyfikowania: powód, wpis w raporcie,
test" (`STAN-I-KIERUNEK-2026-09-05.md`, krok 4). Do 2026-09-07 urosło do
65 — bo nikt tego nie liczył.

Ten plik jest tą trzecią częścią. Nie zakazuje szerokiego handlera:
w tym programie są miejsca, gdzie jest jedyną uczciwą odpowiedzią — lxml
na cudzym dokumencie, Pillow na cudzym obrazku, cssutils na cudzym
arkuszu. Czego zakazuje, to **milczenia**: handler, który nie mówi,
czego się spodziewa i dlaczego łapie wszystko, jest nieodróżnialny od
handlera napisanego po to, żeby test przeszedł.

Dwie zapadki, obie w tę samą stronę co reszta projektu: liczba może
spaść, nie może urosnąć, a powód musi być przy każdym.
"""

from __future__ import annotations

import ast
import pathlib

import epubforge

SOURCE = pathlib.Path(epubforge.__file__).parent

#: Ile szerokich handlerów jest dziś. **Może spaść, nie może urosnąć.**
#: 55 nazwał audyt 2026-09-05; 65 naliczył ten test 2026-09-07, bo między
#: jednym a drugim doszedł czytnik PDF-a i etapy, które go obsługują.
#: Spadek znaczy, że któryś zwężono do tego, co naprawdę może wylecieć —
#: i to jest kierunek.
BROAD_TODAY = 65

#: Co liczy się jako szerokie: wszystko, co złapie błąd, którego nikt nie
#: wymienił z nazwy.
BROAD = ("Exception", "BaseException")


def _handlers():
    """Każdy szeroki handler pakietu jako `(plik, wiersz, wiersze bloku)`."""
    for path in sorted(SOURCE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                kind = handler.type
                if kind is not None and not (
                    isinstance(kind, ast.Name) and kind.id in BROAD
                ):
                    continue
                last = max(getattr(one, "end_lineno", one.lineno) for one in handler.body)
                yield path, handler.lineno, lines[handler.lineno - 1:last]


class TestEveryBroadHandlerSaysWhy:
    """Powód wolno postawić w wierszu `except` (`# noqa: BLE001 — …`) albo
    komentarzem w ciele: jedno i drugie czyta ten, kto tu zajrzy."""

    def test_none_of_them_is_silent(self):
        silent = [
            f"{path.relative_to(SOURCE.parent)}:{line}"
            for path, line, block in _handlers()
            if not any("#" in one for one in block)
        ]
        assert not silent, (
            "szeroki `except` bez powodu — napisz, czego się tu spodziewasz "
            "i dlaczego nie da się tego wymienić z nazwy: " + "; ".join(silent)
        )

    def test_the_number_has_not_grown(self):
        found = sum(1 for _ in _handlers())
        assert found <= BROAD_TODAY, (
            f"{found} szerokich handlerów, było {BROAD_TODAY}. Nowy szeroki "
            "handler to dług, który audyt już raz nazwał: albo wymień błędy "
            "z nazwy, albo podnieś tę liczbę świadomie i powiedz w commicie, "
            "co takiego może tam wylecieć."
        )

    def test_the_recorded_number_is_honest(self):
        """Ta sama para co przy zapadkach katalogu reguł: liczba, która
        została w tyle za kodem, przestaje cokolwiek trzymać."""
        found = sum(1 for _ in _handlers())
        assert found == BROAD_TODAY, (
            f"{found} szerokich handlerów; ustaw BROAD_TODAY na {found}."
        )
