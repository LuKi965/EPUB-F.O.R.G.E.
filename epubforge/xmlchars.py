"""Znaki, których XML nie potrafi zapisać — jedna definicja na cały program.

XML 1.0 nie ma dla nich **żadnego** zapisu: to nie jest kwestia escapowania,
tylko tego, że nie da się ich wyrazić. Dokument, który któryś z nich niesie, nie
parsuje się i książka się nie otwiera.

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


def legal(value: str) -> str:
    """*value* bez znaków, których XML nie uniesie. Każdy inny zostaje."""
    return FORBIDDEN.sub("", value or "")


def count(value: str) -> int:
    """Ile znaków *value* XML nie potrafi zapisać. Do raportu."""
    return len(FORBIDDEN.findall(value or ""))


__all__ = ["FORBIDDEN", "count", "legal"]
