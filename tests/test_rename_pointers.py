"""Każdy rodzaj wskaźnika przeżywa zmianę nazwy pliku — i nowy musi to udowodnić.

Z audytu zewnętrznego z 2026-08-17, i to jest jego najmocniejszy punkt
techniczny. `Book.rename` ręcznie aktualizuje kilkanaście miejsc, w których
mieszka ścieżka: spine, okładkę, nawigację, NCX, czasy trwania, rejestr
szyfrowania, fallbacki, media overlays, kolekcje, spis treści, punkty
orientacyjne, listę stron i sekcje nawigacyjne. Komentarz w kodzie sam przyznaje,
że **trzeci** z nich został kiedyś zapomniany, a zapomnienie znaczyło ciche
kasowanie danych.

Audyt zaproponował na to typowany graf zależności. To jest przepisanie modelu,
writera i połowy etapów — czyli lekarstwo droższe od choroby, a chorobą jest
jedno: *ktoś dopisze czternasty rodzaj wskaźnika i nie podłączy go tutaj*.

Ten plik atakuje dokładnie to i nic więcej. Buduje książkę, w której **każdy**
rodzaj wskaźnika celuje w ten sam plik, przenosi go raz i sprawdza, że nie
został ani jeden odnośnik pod starą nazwą. Test, który dopisze się sam, gdy
model urośnie: liczba pól przeszukiwanych rekurencyjnie jest liczona z modelu,
a nie wpisana ręcznie — więc nowe pole ze ścieżką pojawia się w porównaniu bez
niczyjej pamięci.
"""

from __future__ import annotations

import dataclasses

import pytest

from epubforge.model import (
    Book,
    Collection,
    CollectionLink,
    NavPoint,
    NavSection,
    Resource,
)

STARA = "OEBPS/text/rozdzial.xhtml"
NOWA = "EPUB/text/0001-rozdzial.xhtml"


@pytest.fixture
def book() -> Book:
    """Jedna książka, w której **każdy** wskaźnik celuje w ten sam plik."""
    book = Book()
    book.resources[STARA] = Resource(path=STARA, media_type="application/xhtml+xml", data=b"")
    inny = Resource(
        path="OEBPS/inny.xhtml", media_type="application/xhtml+xml", data=b""
    )
    inny.fallback = STARA
    inny.media_overlay = STARA
    book.resources[inny.path] = inny

    book.spine.append(book.resources[STARA])
    book.cover_path = STARA
    book.nav_path = STARA
    book.ncx_path = STARA
    book.metadata.media_durations[STARA] = "0:10:00"
    book.encrypted[STARA] = "aes"

    kolekcja = Collection(role="https://example.invalid/role")
    kolekcja.links.append(CollectionLink(path=STARA))
    book.collections.append(kolekcja)

    book.toc.append(NavPoint(label="Rozdział", target=f"{STARA}#anchor"))
    book.landmarks.append(NavPoint(label="Początek", target=STARA))
    book.page_list.append(NavPoint(label="1", target=f"{STARA}#page1"))
    book.extra_navs.append(
        NavSection(
            epub_type="loi",
            heading="Spis ilustracji",
            entries=[NavPoint(label="Rycina", target=STARA)],
        )
    )
    return book


def sciezki(value, seen=None) -> list:
    """Każda wartość tekstowa w modelu, która wygląda jak ścieżka.

    Chodzi po całej strukturze, a nie po wymienionej liście pól — dlatego pole
    dopisane jutro trafia tu bez czyjegokolwiek udziału. To jest cała różnica
    między tym testem a listą kontrolną, która starzeje się razem z modelem.
    """
    seen = seen if seen is not None else set()

    found: list = []
    if isinstance(value, str):
        # Nie do `seen`: identyczne napisy są w Pythonie tym samym obiektem, więc
        # pilnowanie ich po tożsamości zwinęłoby trzynaście wskaźników do jednego
        # i test przestałby cokolwiek sprawdzać. Cykl da się zrobić kontenerem,
        # nie napisem.
        return [value] if value.startswith(("OEBPS/", "EPUB/")) else []
    if id(value) in seen:
        return []
    seen.add(id(value))
    if isinstance(value, dict):
        for key, item in value.items():
            found += sciezki(key, seen) + sciezki(item, seen)
        return found
    if isinstance(value, (list, tuple, set)):
        for item in value:
            found += sciezki(item, seen)
        return found
    if dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            # Jedyne pole, którego zadaniem **jest** pamiętać starą nazwę:
            # writer używa go, żeby przepisać odwołania, a bilans, żeby
            # powiedzieć, co się z czym stało. Wymienione tu z nazwy, żeby
            # wyjątek był jeden i widoczny.
            if field.name == "original_path":
                continue
            found += sciezki(getattr(value, field.name, None), seen)
        return found
    return found


class TestEveryPointerFollowsTheFile:
    def test_the_old_path_is_nowhere_in_the_model(self, book):
        """Jedno zdanie zamiast trzynastu asercji: **nigdzie**.

        Trzynaście asercji sprawdza trzynaście rodzajów wskaźnika, o których
        ktoś pamiętał. Ta jedna sprawdza wszystkie, o których nie pamiętał.
        """
        book.rename(STARA, NOWA)
        zostale = [path for path in sciezki(book) if path.startswith(STARA)]
        assert not zostale, (
            "wskaźnik został pod starą nazwą — nowy rodzaj wskaźnika nie został "
            f"podłączony do Book.rename: {sorted(set(zostale))}"
        )

    def test_and_the_guard_would_have_noticed(self, book):
        """Kontrola przeciwna, bez której powyższy test mógłby nie sprawdzać nic:
        przed przeniesieniem stara ścieżka **jest** w modelu, wielokrotnie."""
        found = [path for path in sciezki(book) if path.startswith(STARA)]
        assert len(found) >= 10, found

    def test_the_fragment_survives_the_move(self, book):
        """Przeniesienie pliku nie jest przeniesieniem kotwicy w nim."""
        book.rename(STARA, NOWA)
        assert book.toc[0].target == f"{NOWA}#anchor"
        assert book.page_list[0].target == f"{NOWA}#page1"

    def test_a_pointer_at_another_file_is_left_alone(self, book):
        """Odwrotna pomyłka i równie kosztowna: przenoszenie cudzych wskaźników."""
        book.landmarks.append(NavPoint(label="Inny", target="OEBPS/inny.xhtml"))
        book.rename(STARA, NOWA)
        assert book.landmarks[-1].target == "OEBPS/inny.xhtml"

    def test_renaming_to_itself_changes_nothing(self, book):
        before = sorted(sciezki(book))
        book.rename(STARA, STARA)
        assert sorted(sciezki(book)) == before
