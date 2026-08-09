<div align="center">

<img src="packaging/epubforge.png" alt="EPUB F.O.R.G.E." width="128" height="128">

# EPUB F.O.R.G.E.

**Przebudowuje dowolnego EPUB-a od zera na zgodnego z EPUB 3.3 — zachowując to,
jak książka wygląda.**

`0.2.14` · alpha · 1112 testów · Windows / Linux / macOS

[Instalacja](#instalacja) · [Użycie](#użycie) · [Tryby](#trzy-tryby) ·
[Ograniczenia](#ograniczenia) · [Rozwój](CONTRIBUTING.md) ·
[Zmiany](CHANGELOG.md)

*[English version](README.en.md)*

</div>

---

> ### ⚠️ Zanim wrzucisz tu swoją bibliotekę
>
> Aplikacja powstała z wykorzystaniem metody tak zwanego **Vibe Codingu** i może
> (a prawie na pewno jest) potencjalnym **AI slopem**. Autorzy nie odpowiadają
> za przypadkową autodestrukcję plików w niej przetwarzanych. Wyznajemy zasadę —
> **u mnie działa, u Ciebie nie musi**. Jak nie pasuje, to sobie zatenteguj.
>
> <div align="center"><img src="docs/to-sie-zateguje.jpg" alt="Spokojnie, to się zateguje" width="380"></div>
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

## Ograniczenia

Rzeczy, o których lepiej wiedzieć przed, niż po:

- **Alpha.** Wersja to `0.2.x`, a `0.2.x` **jest** alfą — tak mówi tabela
  dojrzałości w [`CONTRIBUTING.md`](CONTRIBUTING.md) i to samo mówi każdy build
  od 0.2.0, bo tytuł okna bierze etap z kodu. Ten akapit przez kilka wydań
  twierdził, że do alfy jeszcze wchodzimy — co było nieprawdą obok binarki
  podpisanej „alpha". Zakres funkcji jest ustalony, poprawność sprawdzana na
  93 prawdziwych książkach: to jest definicja alfy z tamtej tabeli.
- **Do bety brakuje dwóch rzeczy, nie trzech.** Beta (`0.3.x`) wymaga wydanych
  `profile.py`, sprzątania CSS i konsolidacji spanów, plus kogoś spoza autora,
  kto przepuścił przez to własną bibliotekę. `profile.py` jest wydany w 0.2.11.
  Zostają punkty [4] i [5] roadmapy.
- **Raport idzie za ustawieniem języka.** Okno, plik JSON i konsola mówią tym
  samym językiem, co interfejs; w wierszu poleceń decyduje `--report-language`.
  Angielski `message` zostaje w JSON-ie zawsze, bo to on jest interfejsem dla
  skryptów. Dotyczy to również akapitu szczegółów pod znaleziskiem. To, co
  zostaje po angielsku, to dane, a nie zdania: nazwy znaczników, wartości
  metadanych i komunikaty samego EPUBCheck-a.
- **Nie konwertuje z PDF, MOBI ani Worda.** To inne zadanie — patrz
  [`docs/ROADMAP.md`](docs/ROADMAP.md), punkt 10.
- **Nie zdejmuje DRM** i nie będzie.
- **Cała książka trafia do pamięci.** Przy dużej bibliotece i wielu procesach
  naraz to jest odczuwalne.

## Jak to jest sprawdzane

1112 testów, w tym trzy niezależne siatki bezpieczeństwa:

- **wyrocznia semantyczna** — czyta pakiet jako graf i wykrywa utratę
  pojedynczego egzemplarza, wartości albo krawędzi;
- **korpus publiczny** — sześć prawdziwych książek z Projektu Gutenberga
  i dziewięć syntetycznych, z zapisanymi sygnaturami; zmiana wyniku przebudowy
  wywala test u każdego, nie tylko u autora;
- **niezmiennik K1** — cały tekst źródła musi być w wyniku, w tej samej
  kolejności.

```bash
pytest -q
```

## Dokumentacja

| Plik | O czym |
|---|---|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | reguły K1–K12, wersjonowanie, jak się wydaje |
| [`CHANGELOG.md`](CHANGELOG.md) | co się zmieniło i dlaczego |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | co dalej i czego świadomie nie robimy |
| [`docs/URZADZENIA.md`](docs/URZADZENIA.md) | wyniki na prawdziwym sprzęcie |
| [`docs/archive/`](docs/archive/) | poprzednia wersja tego pliku, z pełnym opisem decyzji projektowych |

## Autorzy i licencja

Łukasz „LuKi" Kniotek, przy wydatnym udziale modeli językowych — patrz akapit
o Vibe Codingu na górze.

MIT. Rób z tym, co chcesz; jak coś zepsujesz, to Twoje.
