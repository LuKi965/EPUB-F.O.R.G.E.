<div align="center">

<img src="packaging/epubforge.png" alt="EPUB F.O.R.G.E." width="128" height="128">

# EPUB F.O.R.G.E.

**Przebudowuje dowolnego EPUB-a od zera na zgodnego z EPUB 3.3 — zachowując to,
jak książka wygląda.**

`0.2.29` · alpha · **Windows**

[Instalacja](#instalacja) · [Użycie](#użycie) · [Tryby](#trzy-tryby) ·
[Ograniczenia](#ograniczenia) · [Zmiany](CHANGELOG.md)

[![English](https://img.shields.io/badge/English-informational?style=for-the-badge&logo=googletranslate&logoColor=white)](README.en.md)

</div>

---

> ### ⚠️ Zanim wrzucisz tu swoją bibliotekę
>
> Aplikacja powstała z wykorzystaniem metody tak zwanego **Vibe Codingu** i może
> (a prawie na pewno jest) potencjalnym **AI slopem**. Autorzy nie odpowiadają
> za przypadkową autodestrukcję plików w niej przetwarzanych. Wyznajemy zasadę —
> **u mnie działa, u Ciebie nie musi**. Jak nie pasuje, to sobie zatenteguj.
>
> <div align="center"><img src="packaging/to-sie-zateguje.jpg" alt="Spokojnie, to się zateguje" width="380"></div>
>
> Uczciwie natomiast: **narzędzie nigdy nie nadpisuje pliku wejściowego**, zapis
> jest atomowy (przerwany przebieg nie zostawia połowy pliku), a nadpisanie
> istniejącego wyjścia wymaga `--force`. To nie jest gwarancja — to jest lista
> rzeczy, które są przetestowane.

---

## Na czym to polega

EPUB to ZIP z dokumentami XHTML, arkuszami CSS i plikiem opisującym całość.
Przez piętnaście lat produkowało go kilkanaście generatorów, z których każdy
robił to trochę inaczej i żaden całkiem zgodnie ze standardem.

To narzędzie **czyta książkę i składa ją na nowo.** Nie łata pliku wejściowego:
buduje z niego model w pamięci i wypisuje świeży kontener EPUB 3.3. Dzięki temu
wynik jest poprawny niezależnie od tego, jak zepsute było wejście.

Naczelna zasada, sprawdzana na każdej książce: **żaden znak tekstu nie ginie.**
Nie „prawie żaden" i nie „liczba znaków się zgadza" — każdy znak kolejności
czytania źródła musi znaleźć się w wyniku, w tej samej kolejności.

Druga zasada, równie ważna i częściej zaskakująca: **utrata ozdobnika też jest
uszkodzeniem książki.** Kursywa, którą wydawca wybrał, ramka wokół motta,
odstęp przed rozdziałem — to jest treść, nie dodatek. Dlatego program woli
zostawić odstępstwo od standardu i je opisać, niż je usunąć i zmienić wygląd.

**Co tu znaczy „zachowując wygląd".** Nie to, że strona wypadnie identycznie co
do piksela — zwykła książka nie wygląda tak samo na dwóch czytnikach nawet
wtedy, gdy nikt jej nie tknął. Stron w niej nie ma; składa je czytnik, u siebie,
przy swojej szerokości ekranu, swojej czcionce i ustawieniach czytelnika. Znaczy
to, że **przeżywa każde rozstrzygnięcie wydawcy**: kursywa zostaje kursywą,
odstęp przed rozdziałem zostaje odstępem, wcięcie zostaje wcięciem, wyśrodkowanie
zostaje wyśrodkowaniem. Konstrukcje, które wypadły ze standardu, są **tłumaczone**
na dzisiejsze odpowiedniki, a nie kasowane — bo kasowanie zmienia wygląd,
a tłumaczenie nie.

## Czego ten program nie zrobi

Zebrane na górze, bo to jest szybsza droga do sprawdzenia, czy w ogóle jest dla
Ciebie:

- **nie zdejmuje DRM** i nie będzie — autor nie popiera piractwa, a to narzędzie
  służy wyłącznie dostosowywaniu **legalnie zakupionych** książek do własnych
  urządzeń;
- **nie konwertuje z PDF, MOBI ani Worda** — to inne zadanie, świadomie poza
  zakresem;
- **nie usuwa niczego bez pytania albo bez przełącznika.** Wszystko, co ten
  program kiedykolwiek kasuje, jest albo do odznaczenia, albo poprzedzone
  pytaniem z konsekwencjami i rekomendacją;
- **nie zgaduje.** Gdy nie wie, pyta; bez odpowiedzi nie zmienia nic.

## Trzy tryby

| Tryb | Co robi | Kiedy |
|---|---|---|
| **Zachowaj wygląd** (`preserve`) | pełna przebudowa; poprawia to, co zepsute, zostawia to, o czym wydawca zdecydował świadomie | domyślny; do większości książek |
| **Wymuś standard** (`strict`) | to samo, ale zgodność wygrywa z wyglądem tam, gdzie się kłócą | gdy plik ma trafić do dystrybucji |
| **Tylko kontener** (`minimal`) | przebudowuje opakowanie, dokumentów nie otwiera | gdy chcesz naprawić wyłącznie strukturę |

Tryb „tylko kontener" robi w treści **dwie** zmiany i obie tego samego rodzaju:
wymienia stary DOCTYPE na ten z EPUB 3, przenosząc razem z nim encje
(`&nbsp;` → `&#160;`), i wypełnia pusty `<title>` nagłówkiem dokumentu. EPUB 2
dopuszczał jedno i drugie, EPUB 3 nie dopuszcza żadnego — a ten tryb buduje
EPUB-a 3, więc bez tych poprawek książka wchodzi poprawna i wychodzi
niepoprawna. Żadnej z tych rzeczy czytelnik nie widzi na stronie.

## Instalacja

### Windows — bez Pythona i bez Javy

Pobierz z [wydań](https://github.com/LuKi965/EPUB-F.O.R.G.E./releases):

- **`EPUB-FORGE-x.y.z-setup.exe`** — instalator, skrót w menu Start
- **`EPUB-Forge-x.y.z-portable.zip`** — rozpakuj i uruchom, nic nie instaluje

Instalator wozi wszystko, czego program potrzebuje: walidator EPUBCheck, silnik
do rysowania stron i słowniki. Każde z nich przypięte sumą SHA-256 — nic nie
jedzie w instalatorze, czego to wydanie nie zmierzyło.

### Ze źródeł

```bash
git clone https://github.com/LuKi965/EPUB-F.O.R.G.E.
cd EPUB-F.O.R.G.E.
pip install -e .
```

Wymaga Pythona 3.10+. EPUBCheck (do walidacji) potrzebuje Javy 11+ i pobiera się
sam przy pierwszym użyciu. Bez silnika do rysowania i bez słowników program
działa — robi mniej i **mówi w raporcie, czego nie sprawdził**.

### O innych systemach, uczciwie

**Wydawany jest tylko Windows.** Kod nie jest do niego przywiązany i testy
przechodzą na Linuksie, ale wyniku na Linuksie ani na macOS-ie nikt nie
sprawdza na prawdziwych książkach i prawdziwym czytniku.

## Użycie

### Okno

```bash
epubforge-gui
```

Przeciągnij pliki, wybierz tryb, uruchom. Raport pojawia się obok kolejki;
**Zapisz raport zbiorczy…** (Ctrl+Shift+S) zapisuje całą kolejkę do jednego
pliku JSON, najgorsze książki na górze.

Wszystko, co ten program potrafi, jest osiągalne z okna. To nie jest uproszczony
front do wiersza poleceń.

### Wiersz poleceń

```bash
epubforge build ksiazka.epub                       # jedna książka
epubforge build *.epub --output przebudowane/      # cała półka
epubforge build ksiazka.epub --strict --report r.json
epubforge build ksiazka.epub --report-language pl   # raport po polsku
epubforge inspect ksiazka.epub                     # co jest w środku
epubforge compat                                   # co robią profile zgodności
```

Kod wyjścia mówi, co się stało: `0` — zapisano, `1` — nie zapisano, `2` —
zapisano, ale są problemy warte przeczytania.

### Przełączniki, które coś usuwają albo zmieniają wygląd

Wszystkie **domyślnie wyłączone**, wszystkie osiągalne z okna:

| przełącznik | co robi |
|---|---|
| `--remove-shop-notices` | usuwa widoczne zdania księgarni — numer zamówienia, „zakupione dla", adres kupującego. Raport wypisuje **każde usunięte zdanie co do słowa**, nie liczbę |
| `--relative-units` | przepisuje rozmiary czcionek z pikseli na `rem`, żeby ustawienie czcionki w czytniku do nich sięgało |
| `--strict` | zgodność wygrywa z wyglądem tam, gdzie się kłócą |
| `--remove-dead` | usuwa reguły CSS i `<span>`-y, o których analiza wykazała, że nie robią nic |

### Profile zgodności

Opcjonalne i domyślnie wyłączone. Każdy tylko **dokłada** — plik, deklarację
albo stary element — i żaden nie zmienia wyglądu na czytniku trzymającym się
standardu.

```bash
epubforge build ksiazka.epub --compat kindle,apple
```

`kindle` · `kobo` · `apple` · `legacy` (Adobe RMSDK: PocketBook, Nook, Sony)

## Co narzędzie o sobie mówi

Każdy przebieg kończy się raportem, w którym każda zmiana ma swój wiersz i swój
powód. Pięć poziomów: `ERROR`, `WARN`, `PRESERVED` (odstępstwo od standardu
zachowane celowo, bo jego usunięcie zmieniłoby wygląd), `FIX`, `INFO`.

Raport mówi też o tym, **czego nie sprawdził**: brak walidatora, brak silnika do
rysowania i brak słownika są w nim nazwane. Przebieg, który widział mniej, nie
ma prawa wyglądać na czystą książkę.

### Znaki wodne

> **Zastrzeżenie.** Autor tego narzędzia nie popiera piractwa. Program nie
> zdejmuje DRM i nie służy do obchodzenia zabezpieczeń. Powstał do
> dostosowywania **legalnie zakupionych** książek do własnych urządzeń
> i zakłada, że użytkownik ma prawo do plików, które mu podaje.

Ukryte znaczniki księgarni są domyślnie **porządkowane, nie usuwane**: powtórzone
style zamieniają się w jedną regułę, a sam znacznik zostaje.

Widoczne zdania — numer zamówienia, dane kupującego — są domyślnie
**zachowywane**. Przełącznik pozwala je usunąć, wraz z pełną listą tego, co
zniknęło, co do słowa. Taka wstawka potrafi siedzieć w biegnącym tekście tuż
przed pierwszym zdaniem powieści albo dokładać całą stronę.

Stopka redakcyjna wydawcy — adres, telefon, ISBN — **nie jest** znakiem wodnym
i nie jest ruszana. Na tym rozróżnieniu ta funkcja stoi albo upada.

### Kiedy program pyta

Martwy odnośnik, słowo rozcięte łącznikiem przez konwersję (`wybo-rowy`),
metadana, która wyszła z domysłu parsera zamiast z pliku — każde z nich to
pytanie z opisanymi konsekwencjami, z rekomendacją i z informacją, czy da się to
cofnąć. Odpowiedzi zapisują się obok książki, więc ta sama książka nie pyta
drugi raz. Wsad, korpus i każdy wywołujący bibliotekę dostają książkę nietkniętą
w tych miejscach.

Przy łącznikach program pyta tylko tam, gdzie ma **dowód**: albo ta sama książka
pisze to słowo bez łącznika gdzie indziej, albo słownik mówi, że pierwsza połowa
nie jest słowem, więc takie złożenie nie istnieje. `savoir-vivre` i
`czarno-czerwony` nie są o nic pytane.

## Ograniczenia

Rzeczy, o których lepiej wiedzieć przed, niż po:

- **Alpha.** Wersja `0.2.x` **jest** alfą: zakres funkcji jest ustalony,
  a poprawność sprawdzana na prawdziwych książkach, nie tylko na atrapach.
- **Tryb ścisły potrafi odmówić wydania pliku.** Pyta EPUBCheck *zanim* plik
  trafi pod swoją nazwę i nie wydaje czegoś, co walidator uznaje za niepoprawne —
  również wtedy, gdy defekt przyszedł razem z książką. Zmierzone na całym
  korpusie publicznym: **17 książek na 19 wychodzi, 2 są odmówione**, obie za
  wady, które przyszły ze źródłem. Odmowa **nie rusza** pliku leżącego już pod
  tą nazwą.
- **Sprawdzenie wyglądu też potrafi zatrzymać zapis i jest obowiązkowe.**
  Program rysuje strony przed i po przebudowie i porównuje je; przy wykrytej
  stracie treści domyślnie nie zapisuje nic. Trzy stany: wyłączone / raportuj /
  zatrzymaj.
- **Silnik do rysowania jest tylko ten dołączony.** Program nie szuka
  przeglądarki na maszynie, bo porównanie dwóch rysunków mówi coś o książce
  tylko wtedy, gdy oba zrobił ten sam silnik — Edge i Chromium nie zgodziły się
  co do trzech z czterech rodzajów uszkodzenia. Kosztuje to jakieś 110 MB
  instalatora. Przy uruchomieniu z kodu źródłowego, gdzie nie ma czego dołączyć,
  silnik wskazuje `EPUBFORGE_CHROME`.
- **Raport idzie za ustawieniem języka**; w wierszu poleceń decyduje
  `--report-language`. W JSON-ie angielski `message` zostaje zawsze, bo to on
  jest interfejsem dla skryptów.
- **Cała książka trafia do pamięci.** Program liczy to przed startem,
  z katalogu ZIP-a, i odmawia zamiast paść w połowie roboty. Na prawdziwych
  książkach najdroższa wychodzi na 104 MiB, więc to zabezpieczenie na przypadek
  patologiczny. Wyłączalne, z własnym polem budżetu.

## Jak to jest sprawdzane

Pięć niezależnych siatek bezpieczeństwa, poza zwykłymi testami jednostkowymi:

- **niezmiennik K1** — cały tekst źródła musi być w wyniku, w tej samej
  kolejności;
- **bilans wejście→wyjście** — co weszło, co wyszło, i czy różnicę tłumaczy wpis
  w rejestrze zmian. K1 pilnuje tekstu, a to pilnuje wszystkiego innego: obrazek,
  który zniknął po cichu, nie zabiera ze sobą ani jednej litery i przez to jest
  dla K1 niewidoczny;
- **wyrocznia semantyczna** — czyta pakiet jako graf i wykrywa utratę
  pojedynczego egzemplarza, wartości albo krawędzi;
- **korpus publiczny** — sześć prawdziwych książek z Projektu Gutenberga
  i trzynaście syntetycznych, z zapisanymi sygnaturami; zmiana wyniku przebudowy
  wywala test u każdego, kto go uruchomi;
- **brak strat funkcjonalnych** — każde ustawienie musi być osiągalne z okna albo
  z wiersza poleceń, każde pole wyboru w oknie musi coś ustawiać, a każda reguła
  raportu musi mieć wpis w obu językach.

```bash
pytest -q                    # cała suita
python tools/jak-ci.py       # to samo w warunkach maszyny budującej wydanie
```

Drugie chowa to, czego nie ma maszyna budująca wydanie. Testy wymagające Javy,
silnika do rysowania albo słowników **pomijają się i mówią, dlaczego** — bez nich
mierzyłyby maszynę. Żeby wykonać te, które rysują strony:

```bash
EPUBFORGE_RENDER_TESTS=1 pytest -q          # plus EPUBFORGE_CHROME, jeśli trzeba
```

## Dokumentacja

[`CHANGELOG.md`](CHANGELOG.md) mówi, co się zmieniło i dlaczego — każde wydanie
z uzasadnieniem, nie z listą commitów.

Reszta dokumentów projektu jest prowadzona prywatnie, bo opisuje konkretne
kupione egzemplarze — ich usterki i ich zawartość.

## Autorzy i licencja

**Łukasz „LuKi" Kniotek** — pomysł, projekt, decyzje i prowadzenie. Kod pisany
przez modele językowe pod jego kierunkiem i według jego wyborów.

Copyright © 2026 Łukasz Kniotek.

**GNU GPL v3 lub późniejsza.** Wolno używać, badać, zmieniać i rozpowszechniać —
pod warunkiem, że to, co z tego zrobisz, też będzie na GPL i też z otwartym
źródłem. Zamknięty produkt na tym kodzie jest zabroniony.

Program jest rozpowszechniany w nadziei, że będzie użyteczny, ale **BEZ
JAKIEJKOLWIEK GWARANCJI**; nawet bez domyślnej gwarancji PRZYDATNOŚCI HANDLOWEJ
albo PRZYDATNOŚCI DO OKREŚLONYCH ZASTOSOWAŃ. Szczegóły w [`LICENSE`](LICENSE).

Aplikacja korzysta z bibliotek na LGPL (Qt/PySide6, cssutils) — ich warunki
obowiązują niezależnie i pozwalają je w zbudowanym pliku podmienić.
