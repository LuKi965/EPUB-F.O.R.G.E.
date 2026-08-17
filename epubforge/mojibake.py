"""Interpunkcja Windows-1252, która wylądowała w bloku sterującym.

**Co się psuje.** Windows-1252 trzyma na pozycjach `0x80`–`0x9f` znaki
przestankowe: cudzysłowy drukarskie, myślniki, wielokropek, znak euro. Latin-1
i Unicode trzymają tam kody sterujące, których żadna czcionka nie rysuje. Gdy
czyjś konwerter odczyta tekst z Windowsa jak Latin-1, każdy cudzysłów zamienia
się w niewidoczny kod — i zostaje w pliku na trwałe, bo dalsza droga przez
UTF-8 zapisuje go już poprawnie jako `U+0093`.

**Że to nie jest nasz błąd odczytu**, warto powiedzieć wprost, bo pierwsza myśl
jest inna: pliki, na których to znaleziono, deklarują UTF-8 i **są** poprawnym
UTF-8. Uszkodzenie jest w treści, nie w odczycie.

**Zasięg, zmierzony.** Dwie książki na sto sześćdziesiąt — na półce kupionych
zero, w mieszanej kolekcji dwie: jedna z **18 545** takimi znakami, druga
z trzema. Czyli rzadkie i, kiedy już wystąpi, masowe.

**Dlaczego tłumaczenie, a nie usunięcie.** Do 0.2.28 te znaki były usuwane, więc
brama K1 słusznie odmawiała takiej książki — nie dało się jej przebudować wcale.
Tablica ma dwadzieścia siedem zdefiniowanych pozycji i jest jednoznaczna:
`0x93` to zawsze „, `0x97` to zawsze —. Odwzorowanie jest deterministyczne,
więc mieści się w tym, co ten program robi ze starymi konstrukcjami wszędzie
indziej — tłumaczy je, zamiast kasować.

**Czego ten moduł nie robi i robić nie będzie.** Nie zgaduje kodowania i nie
naprawia „mojibake" w szerszym sensie — sekwencji typu `Ã³` zamiast `ó`, gdzie
uszkodzeniu uległy bajty tekstu i odwrócenie go wymaga sądu o tym, co autor
miał na myśli. Tu odwzorowanie jest jeden do jednego i bezstratne, i to jest
cała różnica między tym plikiem a heurystyką.

Zmiana jest zmianą **znaków tekstu**, więc nie dzieje się bez pytania (S-02)
i ma wpis w rejestrze zmian.
"""

from __future__ import annotations

#: Pozycje `0x80`–`0x9f` według Windows-1252, bez pięciu niezdefiniowanych
#: (`0x81`, `0x8d`, `0x8f`, `0x90`, `0x9d`). Zbudowana przez sam kodek, a nie
#: przepisana z tablicy w dokumentacji: przepisana ręcznie miałaby literówkę
#: i nikt by jej nie zauważył, bo to są znaki, których nie widać.
TRANSLATION: dict[int, str] = {}
for _byte in range(0x80, 0xA0):
    try:
        TRANSLATION[_byte] = bytes([_byte]).decode("cp1252")
    except UnicodeDecodeError:
        continue  # pozycja niezdefiniowana — nie stoi za nią żaden znak
del _byte

_TABLE = str.maketrans(TRANSLATION)


def repairable(text: str) -> int:
    """Ile znaków *text* da się przetłumaczyć. Do raportu i do pytania."""
    return sum(1 for character in text or "" if ord(character) in TRANSLATION)


def repaired(text: str) -> str:
    """*text* z interpunkcją na swoim miejscu. Każdy inny znak bez zmian."""
    return (text or "").translate(_TABLE)


def census(root) -> dict[str, int]:
    """Ile razy każdy znak występuje w tekście dokumentu.

    Kluczem jest **znak docelowy**, nie bajt źródłowy: pytanie do człowieka ma
    brzmieć „1174 myślniki", a nie „1174 razy `0x97`". Bajt jest przyczyną,
    myślnik jest tym, co ta osoba zobaczy w książce.
    """
    from . import xhtml

    found: dict[str, int] = {}
    for element in xhtml.iter_elements(root):
        for value in (element.text, element.tail):
            for character in value or "":
                target = TRANSLATION.get(ord(character))
                if target is not None:
                    found[target] = found.get(target, 0) + 1
    return found


def apply(root) -> int:
    """Przetłumacz tekst dokumentu w miejscu; zwróć liczbę zmienionych znaków."""
    from . import xhtml

    changed = 0
    for element in xhtml.iter_elements(root):
        if element.text:
            count = repairable(element.text)
            if count:
                element.text = repaired(element.text)
                changed += count
        if element.tail:
            count = repairable(element.tail)
            if count:
                element.tail = repaired(element.tail)
                changed += count
    return changed


__all__ = ["TRANSLATION", "apply", "census", "repairable", "repaired"]
