"""Poczekaj na tag wydania — z terminem i z wyjściem, gdy build padnie.

Powód powstania jest konkretny i mój: przy 0.2.28 uruchomiłem build, a potem
czekałem pętlą `until git ls-remote | grep tag; do sleep; done`. Build padł
w trzeciej minucie, tag nie miał prawa powstać, a pętla czekała dalej. Właściciel
musiał mi powiedzieć, że stoję.

Pętla była napisana na **jeden** warunek — sukces — i dlatego nie umiała się
skończyć inaczej. Ten skrypt kończy się na trzy sposoby i każdy jest wypisany:

    0  tag jest na origin
    1  minął termin
    2  wygląda na to, że build padł (tagu nie ma, a nowy commit nie przybył)

Zasada, która z tego zostaje i którą warto pamiętać poza tym skryptem:
**pętla czekająca na cudzy sukces musi mieć termin i warunek porażki.** Bez
jednego z tych dwóch nie jest czekaniem, tylko zawieszeniem.

    python packaging/wait_for_tag.py v0.2.28
    python packaging/wait_for_tag.py v0.2.28 --minutes 25
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

#: Ile build Windowsa zwykle trwa — testy dwa razy, PyInstaller, Chromium,
#: instalator. Zmierzone na wydaniach 0.2.23–0.2.27: 18–24 minuty. Termin jest
#: ustawiony z zapasem, a nie na styk, bo wolny runner nie jest porażką.
TYPICAL_MINUTES = 35

#: Jak często pytać. Rzadko, bo `ls-remote` to połączenie do GitHuba, a nikt tu
#: nie potrzebuje rozdzielczości lepszej niż pół minuty.
POLL_SECONDS = 30


def tags() -> str:
    try:
        return subprocess.run(
            ["git", "ls-remote", "--tags", "origin"],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except subprocess.SubprocessError:
        # Sieć potrafi mrugnąć. To nie jest powód, żeby przerwać czekanie —
        # ale jest powód, żeby nie udawać, że wiemy, co na origin.
        return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="np. v0.2.28")
    parser.add_argument("--minutes", type=int, default=TYPICAL_MINUTES)
    arguments = parser.parse_args(argv)

    wanted = f"refs/tags/{arguments.tag}"
    deadline = time.monotonic() + arguments.minutes * 60
    checks = 0

    while True:
        if wanted in tags():
            print(f"{arguments.tag} jest na origin.")
            return 0
        if time.monotonic() >= deadline:
            print(
                f"Minęło {arguments.minutes} min, a {arguments.tag} nie ma na "
                f"origin.\nSprawdź przebieg build-windows.yml — jeżeli padł, "
                f"tag nie powstanie i dalsze czekanie nic nie da.",
                file=sys.stderr,
            )
            return 1
        checks += 1
        # Widoczny ślad, żeby dało się odróżnić czekanie od zawieszenia. Bez
        # tego jedno wygląda dokładnie jak drugie — co jest właśnie tym, co
        # kazało napisać ten plik.
        remaining = int(deadline - time.monotonic())
        print(f"  [{checks}] jeszcze nie ma; termin za {remaining // 60} min")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
