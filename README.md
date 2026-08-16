<div align="center">

<img src="packaging/epubforge.png" alt="EPUB F.O.R.G.E." width="128" height="128">

# EPUB F.O.R.G.E.

**Przebudowuje dowolnego EPUB-a od zera na zgodnego z EPUB 3.3 — zachowując to,
jak książka wygląda.**

`0.2.27` · alpha · 2475 testów · **Windows**

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
robił to trochę inaczej i żaden nie robił tego całkiem zgodnie ze standardem.

To narzędzie **czyta książkę i składa ją na nowo**: czyta, co źródło naprawdę
deklaruje, buduje z tego model w pamięci i wypisuje z niego świeży, poprawny
kontener EPUB 3.3. Nie łata pliku wejściowego — pisze nowy. Dzięki temu wynik
jest poprawny niezależnie od tego, jak zepsute było wejście.

Naczelna zasada, sprawdzana testem na każdej książce: **żaden znak tekstu nie
ginie**. Nie „prawie żaden" i nie „liczba znaków się zgadza" — każdy znak
kolejności czytania źródła musi znaleźć się w wyniku, w tej samej kolejności.

## Trzy tryby

| Tryb | Co robi | Kiedy |
|---|---|---|
| **Zachowaj wygląd** (`preserve`) | pełna przebudowa; poprawia to, co jest zepsute, i zostawia to, o czym wydawca zdecydował świadomie | domyślny; do większości książek |
| **Wymuś standard** (`strict`) | to samo, ale zgodność wygrywa z wyglądem tam, gdzie się kłócą | gdy plik ma trafić do dystrybucji |
| **Tylko kontener** (`minimal`) | przebudowuje opakowanie, dokumentów nie otwiera | gdy chcesz wyłącznie naprawić strukturę |

Tryb „tylko kontener" robi w treści **dwie** zmiany, obie tego samego rodzaju.
Wymienia stary DOCTYPE na ten z EPUB 3, przenosząc razem z nim encje
(`&nbsp;` → `&#160;`), i wypełnia pusty `<title>` nagłówkiem samego dokumentu.
EPUB 2 dopuszczał jedno i drugie, EPUB 3 nie dopuszcza żadnego — a ten tryb
przebudowuje pakiet na EPUB-a 3, więc bez tych dwóch poprawek książka wchodzi
poprawna i wychodzi niepoprawna. Ani DOCTYPE, ani `<title>` nie są wyświetlane
w treści, więc żadna z tych zmian nie może zmienić tego, co widzi czytelnik.

## Instalacja

### Windows — bez Pythona i bez Javy

Pobierz z [wydań](https://github.com/LuKi965/EPUB-F.O.R.G.E./releases):

- **`EPUB-FORGE-x.y.z-setup.exe`** — instalator, skrót w menu Start
- **`EPUB-Forge-x.y.z-portable.zip`** — rozpakuj i uruchom, nic nie instaluje

### Ze źródeł

```bash
git clone https://github.com/LuKi965/EPUB-F.O.R.G.E.
cd EPUB-F.O.R.G.E.
pip install -e .
```

Wymaga Pythona 3.10+. EPUBCheck (opcjonalny, do walidacji) potrzebuje Javy 11+
i pobiera się sam przy pierwszym użyciu.

### O innych systemach, uczciwie

**Wydawany jest tylko Windows.** Kod nie robi niczego, co by go do Windowsa
przywiązywało, testy przechodzą na Linuksie i tam powstaje większość tego
programu — ale **nikt nie sprawdza wyniku na Linuksie ani na macOS-ie na
prawdziwych książkach i prawdziwym czytniku**, a to jest jedyny rodzaj
sprawdzenia, który tutaj cokolwiek znaczy.

Do 0.2.21 w tym miejscu stało „Windows / Linux / macOS". To było nieprawdą tego
rodzaju, którą łatwo napisać i trudno zauważyć: z faktu, że coś się uruchamia,
zrobiła obietnicę, że jest sprawdzone.

## Użycie

### Okno

```bash
epubforge-gui
```

Przeciągnij pliki, wybierz tryb, uruchom. Raport pojawia się obok kolejki;
**Zapisz raport zbiorczy…** (Ctrl+Shift+S) zapisuje całą kolejkę do jednego
pliku JSON, najgorsze książki na górze.

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

Znaki wodne i wpisy wydawcy **nie są usuwane** — są porządkowane, gdy powtarzają
się w każdym rozdziale, i zostają.

Tam, gdzie program nie wie, **pyta, zamiast zgadywać**. Martwy odnośnik, słowo
rozcięte łącznikiem przez konwersję (`wybo-rowy`) i metadana, która wyszła z
domysłu parsera, a nie z pliku — każde z nich to pytanie z opisanymi
konsekwencjami każdej odpowiedzi, z rekomendacją i z informacją, czy da się to
cofnąć. **Bez odpowiedzi nie zmienia się nic**, a odpowiedzi zapisują się obok
książki, więc ta sama książka nie pyta drugi raz. Wsad, korpus i każdy
wywołujący bibliotekę dostają książkę nietkniętą w tych miejscach.

## Ograniczenia

Rzeczy, o których lepiej wiedzieć przed, niż po:

- **Alpha.** Wersja to `0.2.x`, a `0.2.x` **jest** alfą — tak mówi tabela
  dojrzałości w dokumentacji projektu i to samo mówi każdy build
  od 0.2.0, bo tytuł okna bierze etap z kodu. Ten akapit przez kilka wydań
  twierdził, że do alfy jeszcze wchodzimy — co było nieprawdą obok binarki
  podpisanej „alpha". Zakres funkcji jest ustalony, poprawność sprawdzana na
  93 prawdziwych książkach: to jest definicja alfy z tamtej tabeli.
- **Do bety brakuje już tylko jednej rzeczy — i nie da się jej napisać.** Beta
  (`0.3.x`) wymagała profilu książki, sprzątania CSS i konsolidacji spanów: te
  trzy są wydane w 0.2.11, 0.2.14 i 0.2.14. Zostaje warunek czwarty: **ktoś
  spoza autora, kto przepuści przez to własną bibliotekę.**
- **Raport idzie za ustawieniem języka.** Okno, plik JSON i konsola mówią tym
  samym językiem, co interfejs; w wierszu poleceń decyduje `--report-language`.
  Angielski `message` zostaje w JSON-ie zawsze, bo to on jest interfejsem dla
  skryptów. Dotyczy to również akapitu szczegółów pod znaleziskiem. To, co
  zostaje po angielsku, to dane, a nie zdania: nazwy znaczników, wartości
  metadanych i komunikaty samego EPUBCheck-a.
- **Tryb ścisły od 0.2.23 potrafi odmówić wydania pliku.** Pyta EPUBCheck
  *zanim* plik trafi pod swoją nazwę i nie wydaje czegoś, co walidator uznaje
  za niepoprawne — również wtedy, gdy defekt przyszedł razem z książką i ten
  program go nie stworzył. Zmierzone na 0.2.27, cały korpus publiczny z
  walidatorem: **17 książek na 19 wychodzi, 2 są odmówione** — jedna za brak
  `viewport` w dokumencie o stałym układzie, druga za klasy Media Overlays bez
  arkusza, i obie wady przyszły razem ze źródłem. Odmowa **nie rusza** pliku,
  który już leży pod tą nazwą.
  Tryb zachowawczy i minimalny wydają i opisują, tak jak dotąd; wybór jest w
  oknie i pod `--gate`.
- **Sprawdzenie wyglądu od 0.2.24 też potrafi zatrzymać zapis, i jest
  obowiązkowe.** Program rysuje strony przed i po przebudowie i porównuje je;
  przy wykrytej stracie treści domyślnie nic nie zapisuje. Trzy stany:
  wyłączone / raportuj / zatrzymaj.
- **Od 0.2.26 instalator wozi własny silnik do rysowania** — `chrome-headless-shell`,
  przypięty sumą SHA-256 tak samo jak EPUBCheck. To nie jest przeglądarka: nie ma
  w nim interfejsu, więc **nie ma czym otworzyć okna**. Do 0.2.25 program szukał
  Chrome'a albo Edge'a na maszynie, a to znaczyło dwie złe rzeczy: Edge potrafił
  otworzyć puste okno, i wynik kontroli zależał od tego, jaką przeglądarkę kto
  ma — zmierzone, Edge i Chromium nie zgadzały się co do trzech z czterech
  rodzajów uszkodzenia. Instalator jest przez to o jakieś 110 MB większy.
  **Od 0.2.28 program nie szuka przeglądarki na maszynie w ogóle** — ani w
  PATH, ani w Program Files, ani u Playwrighta, i nie ma zmiennej, którą dałoby
  się postawić przed silnikiem dołączonym. Cały ten aparat istniał z jednego
  powodu: nie mieliśmy własnego silnika. Porównanie dwóch rysunków mówi coś o
  *książce* tylko wtedy, gdy oba zrobił ten sam silnik; puszczone na tym, co
  maszyna akurat ma, mówi coś o maszynie. Zostaje jedna furtka, dla uruchomienia
  z kodu źródłowego, gdzie nie ma czego dołączyć: `EPUBFORGE_CHROME`.
- **Nie konwertuje z PDF, MOBI ani Worda.** To inne zadanie i świadomie poza
  zakresem.
- **Nie zdejmuje DRM** i nie będzie.
- **Cała książka trafia do pamięci.** Przy dużej bibliotece i wielu procesach
  naraz to jest odczuwalne. Od 0.2.24 program **liczy to przed startem** —
  z katalogu ZIP-a, bez rozpakowywania — i odmawia, zamiast dać się zabić
  jądru w połowie roboty. Na 32 książkach półki najdroższa wychodzi na
  104 MiB, więc jest to zabezpieczenie na przypadek patologiczny, a nie próg,
  który komuś wejdzie w drogę. Wyłączalne, z własnym polem budżetu.

## Jak to jest sprawdzane

2475 testów, w tym cztery niezależne siatki bezpieczeństwa:

- **wyrocznia semantyczna** — czyta pakiet jako graf i wykrywa utratę
  pojedynczego egzemplarza, wartości albo krawędzi;
- **korpus publiczny** — sześć prawdziwych książek z Projektu Gutenberga
  i dziewięć syntetycznych, z zapisanymi sygnaturami; zmiana wyniku przebudowy
  wywala test u każdego, nie tylko u autora;
- **niezmiennik K1** — cały tekst źródła musi być w wyniku, w tej samej
  kolejności;
- **bilans wejście→wyjście** — od 0.2.25: co weszło, co wyszło, i czy różnicę
  tłumaczy wpis w bilansie zmian. K1 pilnuje tekstu, a to pilnuje wszystkiego
  innego — obrazek, który zniknął po cichu, nie zabiera ze sobą ani jednej
  litery i przez to jest niewidoczny dla K1.

```bash
pytest -q
```

42 z nich rysują strony prawdziwą przeglądarką i **pomijają się domyślnie**:
mierzą silnik, a nie ten program, więc uruchomione na przypadkowej przeglądarce
mierzą maszynę. Wskaż silnik jawnie, żeby je wykonać:

```bash
EPUBFORGE_RENDER_TESTS=1 pytest -q          # plus EPUBFORGE_CHROME, jeśli trzeba
```

## Dokumentacja

[`CHANGELOG.md`](CHANGELOG.md) mówi, co się zmieniło i dlaczego — każde wydanie
z uzasadnieniem, nie z listą commitów.

Reszta dokumentów projektu — roadmapa, opis korpusu, wyniki na prawdziwym
sprzęcie, archiwum wydań, zasady K1–K12 — jest prowadzona prywatnie. Nie dlatego,
że jest w nich coś wstydliwego, tylko dlatego, że opisują cudze książki: czyjeś
kupione egzemplarze, ich usterki i ich zawartość. To repozytorium jest publiczne,
a tamte pliki nie są dla przechodniów.

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
