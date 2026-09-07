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
#:
#: **Podniesione 65 → 71 (2026-09-07, revamp UI).** Zapadka nie zabrania
#: rosnąć — zmusza do argumentu, więc oto on, sześć miejsc po kolei:
#: `state.load_history` ×2 (plik historii, który ktoś edytował albo który
#: został po zaniku prądu; nikogo przebudowa od tego nie zależy, a okno ma
#: się otworzyć), `backend._analyse_one` (lxml i zipfile na cudzym pliku —
#: jeden wiersz mówiący „nie da się odczytać" zamiast partii, która staje
#: na trzeciej książce z trzydziestu), `backend._rebuild_one` (ten sam
#: handler, który stare okno ma w `Worker.run`: awaria wychodzi do raportu
#: i do wiersza tabeli), `workers` ×2 (bez nich zadanie umiera w wątku, a
#: okno zostaje na ekranie postępu na zawsze). Wszystkie z powodem
#: i wszystkie zgłaszają się człowiekowi — czyli spełniają regułę, której
#: ten plik pilnuje.
#:
#: **Podniesione 71 → 72 (2026-09-07, druga iteracja revampu).** Jedno miejsce:
#: `workers.ToolJob.run`. Narzędzia czytają całe półki cudzych książek — lxml,
#: zipfile, EPUBCheck, przeglądarka — i awaria jednego z nich ma być wiadomością
#: w polu wyniku, a nie martwym wątkiem i stroną, która do końca sesji pokazuje
#: pasek postępu. Ten sam argument co przy dwóch handlerach w `workers` obok.
BROAD_TODAY = 72

#: Co liczy się jako szerokie: wszystko, co złapie błąd, którego nikt nie
#: wymienił z nazwy.
BROAD = ("Exception", "BaseException")


def _handlers():
    """Każdy szeroki handler pakietu jako `(plik, węzeł, wiersze bloku)`.

    Każdy plik parsowany raz: te trzy testy pytają o to samo drzewo, a
    czytanie pakietu po razie na handler to sto parsowań na jeden test.
    """
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
                yield path, handler, lines[handler.lineno - 1:last]


def _catches(handler, name: str) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == name


class TestNobodySwallowsCtrlC:
    """`except BaseException` łapie także `KeyboardInterrupt` i `SystemExit`.

    Wolno go użyć, żeby po sobie posprzątać — `writer.py` kasuje tak plik
    tymczasowy, żeby połowa książki nie przeżyła Ctrl-C — ale wtedy **musi
    rzucić dalej**. Handler, który łapie `BaseException` i wraca, zamienia
    „człowiek zatrzymał program" w wynik pomiaru: `repair.py` odpowiadał tak
    „ten wpis jest uszkodzony" i skanował dalej cudzą bibliotekę (poprawione
    2026-09-07).
    """

    def test_a_base_exception_handler_re_raises(self):
        offenders = [
            f"{path.relative_to(SOURCE.parent)}:{handler.lineno}"
            for path, handler, _ in _handlers()
            if _catches(handler, "BaseException")
            and not any(isinstance(one, ast.Raise) for one in ast.walk(handler))
        ]
        assert not offenders, (
            "`except BaseException` bez `raise` połyka Ctrl-C: albo złap "
            "`Exception`, albo posprzątaj i rzuć dalej — " + "; ".join(offenders)
        )

    def test_the_one_that_may_is_the_one_that_cleans_up(self):
        """Nie zakaz, tylko granica: `writer.py` kasuje plik tymczasowy
        i rzuca dalej, więc Ctrl-C nadal zatrzymuje program — a połowa
        książki nie zostaje na dysku."""
        keeping = [
            path.name for path, handler, _ in _handlers()
            if _catches(handler, "BaseException")
        ]
        assert keeping == ["writer.py"], keeping


class TestEveryBroadHandlerSaysWhy:
    """Powód wolno postawić w wierszu `except` (`# noqa: BLE001 — …`) albo
    komentarzem w ciele: jedno i drugie czyta ten, kto tu zajrzy."""

    def test_none_of_them_is_silent(self):
        silent = [
            f"{path.relative_to(SOURCE.parent)}:{handler.lineno}"
            for path, handler, block in _handlers()
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
