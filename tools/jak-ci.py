"""Uruchom suitę tak, jak uruchamia ją runner wydania — nie tak, jak wygodnie.

Powód powstania, zapisany, bo inaczej za miesiąc będzie wyglądać na przesadę:
build wydania 0.2.28 **padł na dwóch testach, które lokalnie przechodziły**.
Obie porażki miały jedną przyczynę — słownik hunspella leży w katalogu roboczym
tej maszyny, a runner pobiera go dopiero **po** testach. Czyli suita mierzyła
maszynę, a nie program.

To był **trzeci raz ten sam kształt błędu** w tym projekcie:

    epubcheck.*             — sygnatura wymagała Javy               (WP-12)
    hyphens.no-dictionary   — sygnatura wymagała *braku* słownika   (WP-10)
    hyphens.left-alone      — sygnatura wymagała słownika           (0.2.28)

Dwa pierwsze naprawiono filtrem nazwy reguły. Trzeci tego nie dawał: ze
słownikiem detektor **znajduje więcej**, więc dwa przebiegi naprawdę wykonały
inną pracę. Stąd `dictionaries.suppressed()` i stąd ten skrypt.

Co robi: chowa wszystko, co jest na tej maszynie, a czego runner nie ma na
etapie testów, uruchamia `pytest`, i zawsze odkłada z powrotem — również po
Ctrl-C i po wyjątku, bo skrypt, który przy porażce zostawia katalog schowany,
jest gorszy niż brak skryptu.

    python tools/jak-ci.py                # cała suita
    python tools/jak-ci.py tests/test_x.py

Kod wyjścia jest kodem wyjścia pytesta.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Co jest na tej maszynie, a czego runner nie ma, kiedy uruchamia testy.
#: Słowniki pobiera krok budowania, który leci **po** kroku testowym.
HIDDEN = ("dictionaries",)


def main(argv: list[str]) -> int:
    hidden: list[tuple[pathlib.Path, pathlib.Path]] = []
    holding = pathlib.Path(tempfile.mkdtemp(prefix="jak-ci-"))
    try:
        for name in HIDDEN:
            source = ROOT / name
            if source.exists():
                target = holding / name
                source.rename(target)
                hidden.append((source, target))
                print(f"  schowane na czas testów: {name}/")
        if not hidden:
            print("  nic do schowania — ta maszyna już wygląda jak runner")
        command = [sys.executable, "-m", "pytest", *(argv or ["-q"])]
        print(f"  {' '.join(command)}\n")
        return subprocess.call(command, cwd=ROOT)
    finally:
        # Bezwarunkowo. Porażka testu nie jest powodem, żeby zostawić czyjś
        # katalog roboczy w innym stanie, niż się go zastało.
        for source, target in hidden:
            if target.exists() and not source.exists():
                target.rename(source)
                print(f"\n  odłożone: {source.name}/")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
