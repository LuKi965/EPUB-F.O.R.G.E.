# EPUB-Forge

Przebudowuje dowolny plik EPUB do czystego standardu **EPUB 3.3**, nie tracąc tego,
co czyni książkę sobą — okładki, grafik, czcionek, układu i typografii.

Narzędzie nie łata pliku, który dostaje. Wczytuje książkę do modelu niezależnego od
formatu, wyrzuca oryginalny kontener i generuje nowy: dokument pakietu, nawigację,
manifest, spine, nazwy plików i strukturę ZIP. Właśnie dlatego poprawność wyniku nie
zależy od tego, jak zepsute było źródło.

*(README in English: see [`README.en.md`](README.en.md).)*

## Dlaczego przebudowa, a nie naprawa

Pliki z księgarń i konwerterów psują się w sposób, który wymyka się łataniu:
manifesty wymieniające nieistniejące pliki, spine wskazujący brakujące identyfikatory,
`<center>` i `<font>` z konwertera HTML z 2004 roku, identyfikatory zaczynające się
cyfrą, nieokreślone encje HTML w plikach podających się za XML, czcionki
zaobfuskowane kluczem, którego nikt nie zapisał. Narzędzie naprawiające musi
przewidzieć każdy taki przypadek. Przebudowa musi go tylko *odczytać* — a wynik jest
poprawny z konstrukcji.

## Co jest zachowywane

Zachowanie wyglądu to twarde wymaganie, nie „staranie się". Przestarzały markup jest
**tłumaczony**, nigdy usuwany:

| Źródło | Wynik | Wygląd |
|---|---|---|
| `<center>` | `<div style="text-align: center">` | identyczny |
| `<font color size face>` | `<span style="…">` | identyczny |
| `<table border cellspacing bgcolor>` | odpowiedniki CSS na elemencie | identyczny |
| `<tt>` `<big>` `<strike>` | `<span>` z pasującym CSS | identyczny |
| `<a name="x">` | `<a id="x">` | identyczny |
| czcionki zaobfuskowane | odszyfrowane, `encryption.xml` usunięty | identyczny |
| WebP / BMP / TIFF | PNG, odnośniki przepisane | identyczny |

## Naprawa błędów wydawcy

Osobna kategoria: rzeczy, które przeglądarka i tak odrzuca, więc ich naprawa
**przywraca** intencję wydawcy, zamiast ją nadpisywać.

- **`font-style: regular`** — `regular` nie jest wartością CSS, więc parser wyrzucał
  całą deklarację. Zamieniane na `normal`.
- **`<p><img/></p>` w tekście ciągłym** — reguła `p { text-indent: 2%; text-align: justify }`
  pisana pod prozę przesuwała okładki i strony tytułowe w bok i nigdy ich nie
  centrowała. Akapity zawierające wyłącznie obrazek są z tego wyłączane.
- **Błędne typy MIME w manifeście** — np. `application/x-font-ttf`, który nie istnieje
  w żadnym standardzie.
- **Identyfikatory niebędące poprawnymi nazwami XML** — zmieniane wraz ze wszystkimi
  odnośnikami, także we wnętrzu spisu treści.

Rzeczy, które są **wyborem** wydawcy — nawet nietypowym — zostają i trafiają do
raportu. `div.dol { position: absolute; bottom: 0 }` dociska dedykację do dołu strony;
to układ, a nie usterka.

## Dostępność cyfrowa

Od czerwca 2025 **European Accessibility Act** obejmuje ebooki, więc metadane
dostępności przestały być opcjonalne. Narzędzie generuje deklaracje
**EPUB Accessibility 1.1** wyprowadzone z tego, co książka faktycznie zawiera:
`schema:accessMode`, `accessModeSufficient`, `accessibilityFeature`,
`accessibilityHazard` i podsumowanie.

Obowiązuje przy tym jedna twarda zasada: **żadna deklaracja nie jest zmyślana.**
Narzędzie, które wpisze `alternativeText` książce bez opisów alternatywnych, nie
poprawiło dostępności — wyprodukowało fałszywe oświadczenie i utrudniło znalezienie
problemu. Dlatego:

- `alternativeText` pojawia się tylko wtedy, gdy **każda** ilustracja ma realny opis;
- alt powtarzający nazwę pliku (`alt="title-1"`, `alt="cover"`) jest wykrywany i
  **nie** liczy się jako opis;
- okładka dostaje opis z tytułu książki, bo okładka przedstawia książkę;
- zgodność z WCAG **nigdy** nie jest deklarowana automatycznie — maszynowo się jej nie
  da ustalić, a pod EAA to oświadczenie wydawcy. Służy do tego jawna flaga
  `--claim-conformance`.

Braki, których nie da się naprawić automatycznie (brakujące opisy, przeskoki poziomów
nagłówków, tabele bez komórek nagłówkowych), trafiają do raportu jako robota dla
człowieka.

## Zgodność kontra wygląd

Tam, gdzie jedno naprawdę kłóci się z drugim, decyduje tryb — a każde odstępstwo i tak
trafia do raportu.

- **`preserve`** (domyślny) — wygrywa wygląd. Hacki CSS pod konkretne czytniki,
  skrypty i linki do plików, których książka nigdy nie zawierała, zostają, każde
  odnotowane jako `zachowano`.
- **`strict`** — wygrywa specyfikacja. Martwe odnośniki tracą `href` (tekst zostaje),
  znikają bloki `@media` pod Kindle, właściwości `adobe-*` i pozycjonowanie
  bezwzględne. Wynik przechodzi EPUBCheck bez zastrzeżeń.
- **`minimal`** — tylko kontener. Pliki treści przechodzą bajt w bajt; regenerowane są
  wyłącznie OPF, nawigacja i struktura ZIP.

## Instalacja

### Windows — bez Pythona i bez Javy

Pobierz `EPUB-Forge-<wersja>-setup.exe` ze
[strony wydań](https://github.com/LuKi965/EPUB-Forge/releases) albo wersję przenośną
`.zip`. Obie zawierają środowisko Pythona, Qt, minimalne środowisko Javy i EPUBCheck —
na komputerze docelowym nie trzeba mieć niczego. Instalator działa w trybie
użytkownika i nie pyta o uprawnienia administratora.

W paczce są dwa programy:

- `EPUB-Forge.exe` — okno. Przeciągasz książki, oglądasz raport, zapisujesz wynik.
- `epubforge.exe` — to samo z wiersza poleceń, do przetwarzania wsadowego.

### Ze źródeł

```bash
pip install -e ".[gui]"
```

Tutaj EPUBCheck jest opcjonalny: wskaż `epubcheck.jar` zmienną `EPUBCHECK_JAR` albo
umieść `epubcheck` w `PATH`. Bez niego działa wszystko poza walidacją.

## Użycie

```bash
# Jedna książka, obok oryginału
epubforge build ksiazka.epub

# Cała biblioteka do jednego folderu, z weryfikacją
epubforge build ~/Ebooki -o ~/Ebooki/czyste --check

# Pełna zgodność, wygląd na drugim miejscu
epubforge build ksiazka.epub --strict -o czysta.epub

# Co jest nie tak z tym plikiem, bez zapisywania czegokolwiek
epubforge inspect ksiazka.epub

# Interfejs graficzny
epubforge gui
```

Przydatne flagi: `--no-ncx`, `--strip-scripts`, `--keep-orphans`, `--keep-layout`,
`--no-a11y-metadata`, `--claim-conformance wcag-aa`,
`--title/--author/--publisher/--series/--language`, `--report raport.json`, `-v`.

## Interfejs

Polski lub angielski, przełączany w menu **Ustawienia → Język interfejsu** (wybór jest
zapamiętywany). Każda opcja ma dymek opisujący, co zrobi z książką — nie powtarzający
jej nazwy. Motyw jasny i ciemny dobiera się z ustawień systemu.

## Raport

Każde uruchomienie rozlicza się z tego, co zrobiło. Wpisy mają jeden z poziomów:
`naprawiono` (usterka poprawiona), `zachowano` (odstępstwo zostawione świadomie),
`ostrzeżenie`, `błąd`, `informacja`. `--report` zapisuje te same dane w JSON-ie.

```
naprawiono  package        rebuilt the package from EPUB 2.0 to EPUB 3.3
naprawiono  css            corrected 5 declarations using the invalid value 'regular'
naprawiono  xhtml          centred 1 image-only paragraph and removed its text indent
naprawiono  accessibility  added EPUB Accessibility 1.1 discovery metadata
zachowano   css            kept 1 absolute/fixed position rule in a reflowable book
ostrzeżenie accessibility  2 images have alt text that only repeats the filename
```

Treść wpisów jest na razie po angielsku — tłumaczenie wymaga przebudowy sposobu, w
jaki etapy tworzą komunikaty, i jest zaplanowane osobno.

## Jako biblioteka

```python
from epubforge import rebuild, Policy

wynik = rebuild("we.epub", "wy.epub", Policy.preset("strict"))
print(wynik.report.to_text())
```

## Potok przetwarzania

Kolejność etapów ma znaczenie i jest udokumentowana w `epubforge/stages/__init__.py`.

```
odczyt → czcionki → obrazy → struktura → metadane → xhtml → css → nawigacja → dostępność → zapis
```

`czcionki` przed `metadanymi`, bo deobfuskacja opiera się na *źródłowym*
identyfikatorze, który normalizacja może wymienić. `struktura` przed `xhtml`, bo
zamraża mapę ścieżek, od której zależy przepisywanie odnośników. `dostępność` na
końcu, bo mierzy gotową książkę.

## Budowanie paczki

Wymaga JDK 17+ (dla `jlink`) i `pip install pyinstaller`.

```bash
python packaging/build.py                # pobiera EPUBCheck, linkuje JRE, zamraża
python packaging/build.py --skip-java    # ~60 MB, bez walidacji
python packaging/smoke_test.py           # uruchamia wynik z wyczyszczonym środowiskiem
```

Wynik trafia do `dist/EPUB-Forge/`. `smoke_test.py` czyści `PATH`, `JAVA_HOME` i
`EPUBCHECK_JAR` przed uruchomieniem zbudowanych plików wykonywalnych, więc wykryje
sytuację, w której paczka po cichu polega na czymś zainstalowanym na maszynie
budującej.

Instalatory Windows powstają przez `.github/workflows/build-windows.yml`. Wypchnij tag
`v*`, żeby wydać wersję, albo uruchom workflow ręcznie.

## Ograniczenia

- **DRM nie jest ruszany.** Prawdziwe szyfrowanie jest wykrywane, odrzucane i
  raportowane. Odwracana jest wyłącznie obfuskacja czcionek, która DRM-em nie jest.
- Książki o stałym układzie przechodzą z zachowanymi właściwościami `rendition:*`, ale
  ich pozycjonowanie nie jest przeliczane.
- Nazwy plików są sprowadzane do ASCII. Polskie `ł` nie ma rozkładu unikodowego i
  wypada (`okładka.png` → `okadka.png`); odnośniki są przepisywane.

## Testy

```bash
pytest
```

Zestaw przebudowuje plik testowy zawierający opisane wyżej uszkodzenia i sprawdza
wynik — w tym, jeśli EPUBCheck jest zainstalowany, że tryb `--strict` waliduje się z
zerem błędów i zerem ostrzeżeń.

## Autorzy

- **Łukasz „LuKi” Kniotek** — pomysł, kierunek i wymagania
- **Claude (Anthropic)** — projekt i implementacja

Licencja MIT — patrz [`LICENSE`](LICENSE), gdzie wymieniono też licencje komponentów
dołączanych do paczek (EPUBCheck, OpenJDK, Qt).
