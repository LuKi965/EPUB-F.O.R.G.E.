"""Znaki, których XML nie potrafi zapisać — jedna definicja na cały program.

Dla większości z nich — sterujące poniżej 0x20, surogaty, dwa nie-znaki na końcu
BMP — XML 1.0 nie ma **żadnego** zapisu: to nie jest kwestia escapowania, tylko
tego, że nie da się ich wyrazić. Dokument, który któryś z nich niesie, nie
parsuje się i książka się nie otwiera.

Blok C1 (`0x7f-0x9f`) jest tu z innego powodu i warto, żeby to było napisane, bo
inaczej ktoś słusznie zarzuci temu plikowi kłamstwo: te znaki XML 1.0 **wpuszcza**
do drzewa. Są tu, bo nie są tekstem — nie mają glifu, nie mają szerokości i żaden
czytnik ich nie rysuje — a XML 1.1 wymaga dla nich escapowania i walidator
zgłasza je na dokumentach treści. Prawdziwa książka z półki właściciela niosła
`U+008F` w dwóch rozdziałach i to jest ten przypadek, nie hipoteza.

Znalezione fuzzingiem writera (WP-18/EF-040). Zmierzone na domyślnym presecie:
książka z `0x0B` w tytule była **zapisywana**, ze statusem `succeeded`, a jej
dokument pakietu, `nav.xhtml` i `toc.ncx` nie parsowały się. Nieotwieralna
książka wyprodukowana przez tryb, którego ludzie faktycznie używają.

**Dlaczego osobny moduł, a nie stała w writerze.** Naprawa musi sięgać trzech
miejsc: writera (pakiet), `xhtml` (dokumenty treści) i etapu nawigacji, który
generuje `nav.xhtml` i NCX z tych samych metadanych przez własny escaper. Przy
pierwszym podejściu wpisałem to samo wyrażenie w każdym z nich, z komentarzem,
że dwie kopie są zbędne — bo `navigation` importujący z `writer` wiązałby etap
z tym, co działa po wszystkich etapach. Liść, od którego zależą wszyscy i który
nie zależy od nikogo, znosi ten problem bez kopiowania.
"""

from __future__ import annotations

import re

#: Wszystko poniżej 0x20 poza tabulacją, nową linią i powrotem karetki; blok
#: surogatów; oraz dwa nie-znaki na końcu BMP. Zbiór jest ustalony przez
#: specyfikację XML, więc nie może się rozjechać tak, jak rozjechałby się osąd.
FORBIDDEN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff￾￿]"
)


#: Podzbiór, którego **żadne odczytanie nie zamieni w tekst** — i tylko on ma
#: prawo być niewidoczny dla niezmiennika K1.
#:
#: Różnica wobec `FORBIDDEN` to blok C1, i kosztowała jedną rozbrojoną bramę.
#: `FORBIDDEN` obejmuje `0x7f-0x9f` w całości, więc złożenie K1 przez `legal`
#: przepuściło książkę, która gubiła **18 545 znaków**: `0x93`, `0x94`, `0x92`,
#: `0x97` — czyli „ ” ‘ i —, cudzysłowy i myślniki Sandersona, zapisane
#: w Windows-1252 i odczytane jak Latin-1. Nie są to znaki sterujące. Są to
#: znaki przestankowe, które trafiły nie tam, i K1 słusznie odmawiało tej
#: książki, dopóki nie kazałem mu tego przeoczyć.
#:
#: Zostaje więc to, czego cp1252 **nie definiuje** na żadnej pozycji:
#: `0x81`, `0x8d`, `0x8f`, `0x90`, `0x9d` oraz `0x7f`. Za nimi nie stoi żaden
#: znak w żadnym kodowaniu — nie ma czego uratować i nie ma czego stracić.
NEVER_TEXT = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x81\x8d\x8f\x90\x9d\ud800-\udfff￾￿]"
)


def legal(value: str) -> str:
    """*value* bez znaków, których XML nie uniesie. Każdy inny zostaje."""
    return FORBIDDEN.sub("", value or "")


def only_text(value: str) -> str:
    """*value* bez znaków, za którymi nie stoi żaden znak w żadnym kodowaniu.

    Do porównań tekstu, nie do zapisu. `legal` odpowiada na pytanie „co da się
    wpisać do pliku"; ta funkcja na pytanie „co w ogóle było tekstem".
    """
    return NEVER_TEXT.sub("", value or "")


def count(value: str) -> int:
    """Ile znaków *value* XML nie potrafi zapisać. Do raportu."""
    return len(FORBIDDEN.findall(value or ""))


__all__ = ["FORBIDDEN", "NEVER_TEXT", "count", "legal", "only_text"]
