# EPUB F.O.R.G.E.

**F**abryka **O**dbudowy i **R**enowacji **G**litchujących **E**PUB-ów

Przekuwa wadliwe EPUB-y w czysty **EPUB 3.3**, nie tracąc tego, co czyni książkę
sobą — okładki, grafik, czcionek, układu i typografii.

*(English: [`README.en.md`](README.en.md).)*

---

## Spis treści

1. [Na czym to polega](#na-czym-to-polega)
2. [Co jest zachowywane](#co-jest-zachowywane)
3. [Co jest naprawiane](#co-jest-naprawiane)
4. [Czego narzędzie nie rusza](#czego-narzędzie-nie-rusza)
5. [Tryby pracy](#tryby-pracy)
6. [Zgodność z czytnikami](#zgodność-z-czytnikami)
7. [Dostępność cyfrowa](#dostępność-cyfrowa)
8. [Instalacja](#instalacja)
9. [Użycie](#użycie)
10. [Raport](#raport)
11. [Jak to jest zbudowane](#jak-to-jest-zbudowane)
12. [Budowanie paczki](#budowanie-paczki)
13. [Ograniczenia](#ograniczenia)
14. [Rozwój](#rozwój)
15. [Autorzy i licencja](#autorzy-i-licencja)

---

## Na czym to polega

Narzędzie nie łata pliku, który dostaje. Wczytuje książkę do modelu niezależnego
od formatu, wyrzuca oryginalny kontener i generuje nowy: dokument pakietu,
nawigację, manifest, spine, nazwy plików i strukturę ZIP.

To nie jest ozdobnik architektoniczny, tylko powód, dla którego to działa. Pliki
z księgarń i konwerterów psują się w sposób, który wymyka się łataniu: manifesty
wymieniające nieistniejące pliki, spine wskazujący brakujące identyfikatory,
`<center>` i `<font>` z konwertera HTML z 2004 roku, identyfikatory zaczynające
się cyfrą, nieokreślone encje HTML w plikach podających się za XML, czcionki
zaobfuskowane kluczem, którego nikt nie zapisał. Narzędzie *naprawiające* musi
przewidzieć każdy z tych przypadków z osobna. Przebudowa musi go tylko
**odczytać** — a wynik jest poprawny z konstrukcji, nie z listy poprawek.

Zasada nadrzędna, której podlega cała reszta:

> Naprawiamy to, co jest **jawnym błędem**. Zostawiamy to, co jest **decyzją
> wydawcy** — nawet nietypową. Gdy nie da się rozstrzygnąć, wygrywa wygląd,
> a wątpliwość idzie do raportu.

---

## Co jest zachowywane

Zachowanie wyglądu to twarde wymaganie, nie „staranie się”. Przestarzały markup
jest **tłumaczony**, nigdy usuwany:

| Źródło | Wynik | Wygląd |
|---|---|---|
| `<center>` | `<div style="text-align: center">` | identyczny |
| `<font color size face>` | `<span style="…">` | identyczny |
| `<table border cellspacing bgcolor>` | odpowiedniki CSS na elemencie | identyczny |
| `<tt>` `<big>` `<strike>` | `<span>` z pasującym CSS | identyczny |
| `<a name="x">` | `<a id="x">` | identyczny |
| czcionki zaobfuskowane | odszyfrowane, `encryption.xml` usunięty | identyczny |
| WebP / BMP / TIFF | PNG, odnośniki przepisane | identyczny |

### Znaki wodne

Znaki wodne księgarń (*social DRM*) **nie są usuwane** — to sprawa między Tobą
a sprzedawcą, nie narzędziem. Są za to porządkowane, bo w oryginale potrafią
zdemolować książkę technicznie: pojedynczy token wstrzyknięty w
`<div style="font-size:1px !important">` na końcu **każdego** dokumentu — 34
kopie w jednej zmierzonej tu książce, 27 i 23 w dwóch kolejnych.

Tekst tokenu zostaje nietknięty. Znika powtarzane po trzydzieści parę razy
formatowanie inline z `!important`, zastąpione jedną regułą, a znacznik dostaje
`aria-hidden`, żeby czytnik ekranowy przestał go literować na końcu każdego
rozdziału. Widoczne informacje o ochronie — te przeznaczone do przeczytania —
są rozpoznawane osobno i zostają dokładnie takie, jakie były.

---

## Co jest naprawiane

Osobna kategoria: rzeczy, które przeglądarka i tak odrzuca, więc ich naprawa
**przywraca** intencję wydawcy, zamiast ją nadpisywać.

- **`font-style: regular`** — `regular` nie jest wartością CSS, więc parser
  wyrzucał całą deklarację. Zamieniane na `normal`.
- **`<p><img/></p>` w tekście ciągłym** — reguła
  `p { text-indent: 2%; text-align: justify }` pisana pod prozę przesuwała
  okładki i strony tytułowe w bok i nigdy ich nie centrowała.
- **Blok wewnątrz elementu liniowego** — nagłówek zbudowany jako
  `<h1><a><span style="display:block">…</span></a></h1>`. Blok rozbija element
  liniowy na anonimowe pudełka i marginesy zaczynają się zachowywać
  nieprzewidywalnie; opakowanie awansuje na `inline-block`.
- **Błędne typy MIME w manifeście** — np. `application/x-font-ttf`, który nie
  istnieje w żadnym standardzie.
- **Identyfikatory niebędące poprawnymi nazwami XML** — zmieniane wraz ze
  wszystkimi odnośnikami, także we wnętrzu spisu treści.
- **Nieokreślone encje** (`&nbsp;` i pokrewne) w plikach deklarujących się jako
  XML, na których czytniki wykładają się fatalnie.

### Skąd narzędzie wie, że to błąd

Poprawka obrazków jest tu dobrym przykładem, bo pokazuje różnicę między
„naprawiam usterkę” a „narzucam swój gust”. Zanim akapit z samym obrazkiem
zostanie wycentrowany, czytana jest kaskada CSS:

- `p.ilustracja { text-align: right }` — reguła celuje w ten akapit klasą, więc
  jest **decyzją o tym obrazku**. Zostaje.
- `p { text-align: justify }` — reguła pisana pod prozę, która przypadkiem
  spadła na grafikę przez dziedziczenie. Akapit jest z niej wyłączany.
- styl inline — zawsze respektowany.
- selektor zbyt złożony, żeby go jednoznacznie odczytać — traktowany jak
  celowany. Przy niepewności narzędzie **nie rusza**.

Dlatego książki, które stylują swoje ilustracje świadomie, wychodzą nietknięte,
a poprawiane są tylko strony, na których o wyrównaniu nie zdecydował nikt.

---

## Czego narzędzie nie rusza

Rzeczy, które są **wyborem** wydawcy — nawet dziwnym — zostają i trafiają do
raportu jako `zachowano`:

- `div.dol { position: absolute; bottom: 0 }` dociska dedykację do dołu strony;
  to układ, a nie usterka. (Usuwane dopiero w trybie `strict`.)
- Hacki CSS pod konkretne czytniki, `@media amzn-*`, właściwości `adobe-*`.
- Skrypty — część książek o stałym układzie bez nich się rozjeżdża.
- Odnośniki do plików, których książka nigdy nie zawierała: tekst zostaje,
  usterka idzie do raportu.

**DRM nie jest ruszany.** Prawdziwe szyfrowanie jest wykrywane, odrzucane
i raportowane; narzędzie odwraca wyłącznie obfuskację czcionek, która DRM-em nie
jest.

---

## Tryby pracy

Tam, gdzie zgodność naprawdę kłóci się z wyglądem, decyduje tryb — a każde
odstępstwo i tak trafia do raportu.

| Tryb | Co wygrywa | Co robi |
|---|---|---|
| **`preserve`** *(domyślny)* | wygląd | Naprawia jawne błędy. Odstępstwa, które działają, zostają z adnotacją `zachowano`. |
| **`strict`** | specyfikacja | Martwe odnośniki tracą `href` (tekst zostaje), znikają bloki `@media` pod Kindle, właściwości `adobe-*` i pozycjonowanie bezwzględne. |
| **`minimal`** | nic | Regenerowany jest wyłącznie kontener: OPF, nawigacja i struktura ZIP. Pliki XHTML i CSS wychodzą **bajt w bajt** takie, jakie weszły. |

W trybie `minimal` etapy XHTML i CSS w ogóle się nie uruchamiają. Samo
sparsowanie i ponowne zapisanie dokumentu zmienia jego bajty, nawet gdy nic mu
nie brakuje — więc jedynym sposobem dotrzymania tej obietnicy jest nieotwieranie
tych plików.

---

## Zgodność z czytnikami

Wynikiem tego narzędzia jest książka zgodna ze standardem. Niektóre urządzenia
standardu nie trzymają się, a ich awaria nie jest głośna: czytnik nie protestuje,
tylko renderuje książkę źle — pusty spis treści, okładka, która się nie
pojawia, rozdziały zlane w jeden akapit.

Dlatego profile zgodności są **opcjonalne i domyślnie wyłączone**, a każdy z nich
wyłącznie **dokłada**: plik, deklarację albo stary element. Żaden nic nie usuwa,
nie przepisuje tego, co w książce było, ani nie zmienia wyglądu na czytniku
trzymającym się specyfikacji. To jest cena wstępu — ustępstwo, które mogłoby
zepsuć książkę na poprawnym oprogramowaniu, nie jest ustępstwem, tylko regresją.

| Profil | Urządzenia | Co dokłada |
|---|---|---|
| `kindle` | Amazon Kindle (Send-to-Kindle, konwersja KFX/KF8) | `<guide>`, arkusz z blokowymi elementami HTML5, stara pisownia łamania stron |
| `kobo` | Rakuten Kobo czytające EPUB-a wprost | NCX, `<guide>`, blokowe elementy HTML5 |
| `apple` | Apple Books (iOS, macOS) | `META-INF/com.apple.ibooks.display-options.xml` |
| `legacy` | Adobe RMSDK — PocketBook, Nook, Sony, starsze Kobo i Onyx | wszystko powyższe |

Dlaczego akurat to:

- **`<guide>`** — konwerter Amazona i czytniki oparte na RMSDK szukają okładki
  i miejsca rozpoczęcia lektury właśnie tam, nie w nawigacji EPUB 3. Element nie
  należy już do EPUB 3.3, choć EPUBCheck wciąż go akceptuje: plik pozostaje
  poprawny, ale niesie coś, co standard porzucił.
- **Blokowe elementy HTML5** — RMSDK renderuje nieznany element jako liniowy,
  więc książka zbudowana z `<section>` zlewa się w jeden ciągły akapit. Arkusz
  jest podlinkowany **przed** arkuszami wydawcy, więc każda jego reguła nadal
  wygrywa.
- **`page-break-*`** — nowoczesne właściwości łamania są młodsze od tych
  silników. Stara pisownia jest dopisywana **przed** nową, żeby w aktualnym
  czytniku wciąż wygrywała ta, którą napisał wydawca.
- **`specified-fonts`** — bez tego pliku Apple Books ignoruje wszystkie osadzone
  kroje i podstawia własny. Powstaje tylko wtedy, gdy książka faktycznie zawiera
  czcionki: deklaracja czegoś, czego nie ma, byłaby po prostu nieprawdą.

Z wszystkimi czterema profilami naraz wynik nadal przechodzi EPUBCheck z zerem
błędów i zerem ostrzeżeń — pilnuje tego test.

```bash
epubforge compat                       # co dokładnie robi każdy profil i po co
epubforge build ksiazka.epub --compat kindle,apple
```

Czego to **nie** jest: lekarstwa na czytnik, który odmawia otwarcia pliku
w ogóle. Taka usterka leży gdzie indziej i profil jej nie naprawi.

---

## Dostępność cyfrowa

Od czerwca 2025 **European Accessibility Act** obejmuje ebooki, więc metadane
dostępności przestały być opcjonalne. Narzędzie generuje deklaracje
**EPUB Accessibility 1.1** wyprowadzone z tego, co książka faktycznie zawiera:
`schema:accessMode`, `accessModeSufficient`, `accessibilityFeature`,
`accessibilityHazard` i podsumowanie.

Obowiązuje przy tym jedna twarda zasada: **żadna deklaracja nie jest zmyślana.**
Narzędzie, które wpisze `alternativeText` książce bez opisów alternatywnych, nie
poprawiło dostępności — wyprodukowało fałszywe oświadczenie i utrudniło
znalezienie problemu. Dlatego:

- `alternativeText` pojawia się tylko wtedy, gdy **każda** ilustracja ma realny
  opis;
- alt powtarzający nazwę pliku (`alt="title-1"`, `alt="cover"`) jest wykrywany
  i **nie** liczy się jako opis;
- okładka dostaje opis z tytułu książki, bo okładka przedstawia książkę;
- zgodność z WCAG **nigdy** nie jest deklarowana automatycznie — maszynowo się
  jej nie da ustalić, a pod EAA to oświadczenie wydawcy. Służy do tego jawna
  flaga `--claim-conformance`.

Braki, których nie da się naprawić automatycznie (brakujące opisy, przeskoki
poziomów nagłówków, tabele bez komórek nagłówkowych), trafiają do raportu jako
robota dla człowieka.

---

## Instalacja

### Windows — bez Pythona i bez Javy

Pobierz `EPUB-FORGE-<wersja>-setup.exe` ze
[strony wydań](https://github.com/LuKi965/EPUB-F.O.R.G.E./releases) albo wersję
przenośną `.zip`. Obie zawierają środowisko Pythona, Qt, minimalne środowisko
Javy i EPUBCheck — na komputerze docelowym nie trzeba mieć niczego. Instalator
działa w trybie użytkownika i nie pyta o uprawnienia administratora.

W paczce są dwa programy:

- `EPUB-Forge.exe` — okno. Przeciągasz książki, oglądasz raport, zapisujesz wynik.
- `epubforge.exe` — to samo z wiersza poleceń, do przetwarzania wsadowego.

### Ze źródeł

```bash
pip install -e ".[gui]"
```

Tutaj EPUBCheck jest opcjonalny: wskaż `epubcheck.jar` zmienną `EPUBCHECK_JAR`
albo umieść `epubcheck` w `PATH`. Bez niego działa wszystko poza walidacją.

---

## Użycie

```bash
# Jedna książka, obok oryginału
epubforge build ksiazka.epub

# Cała biblioteka do jednego folderu, z weryfikacją
epubforge build ~/Ebooki -o ~/Ebooki/czyste --check

# Co się psuje w całej bibliotece — rankingowo, nic nie zapisując
epubforge survey ~/Ebooki

# Czym te książki są: pochodzenie, uszkodzenia, typografia
epubforge inventory ~/Ebooki --json spis.json

# Pełna zgodność, wygląd na drugim miejscu
epubforge build ksiazka.epub --strict -o czysta.epub

# Z ustępstwami pod konkretne urządzenia
epubforge build ksiazka.epub --compat kobo

# Co jest nie tak z tym plikiem, bez zapisywania czegokolwiek
epubforge inspect ksiazka.epub

# Interfejs graficzny
epubforge gui
```

Przydatne flagi: `--no-ncx`, `--strip-scripts`, `--keep-orphans`, `--keep-layout`,
`--keep-watermark-markup`, `--no-a11y-metadata`, `--claim-conformance wcag-aa`,
`--compat`, `--modified`, `--title/--author/--publisher/--series/--language`,
`--report raport.json`, `-v`.

### Interfejs

Trzy zakładki, bo to trzy różne pytania:

| Zakładka | Do czego |
|---|---|
| **Przebudowa** | pojedyncze książki: przeciągasz, oglądasz raport, zapisujesz wynik |
| **Biblioteka** | cały folder naraz — przegląd (co się psuje) albo inwentarz (czym te książki są) |
| **Korpus** | podpisy Twojej biblioteki, żeby pilnowała narzędzia przy każdej kolejnej zmianie |

Polski lub angielski, przełączany w menu **Ustawienia → Język interfejsu**
(wybór jest zapamiętywany). Każda opcja ma dymek opisujący, co zrobi z książką —
nie powtarzający jej nazwy. Motyw jasny i ciemny dobiera się z ustawień systemu.

Okno bierze część dostępnego pulpitu zamiast stałego rozmiaru, a kolumna opcji
przewija się, zamiast być ucinana na niższych ekranach.

### Jako biblioteka

```python
from epubforge import rebuild, Policy

wynik = rebuild("we.epub", "wy.epub", Policy.preset("strict"))
print(wynik.report.to_text())
```

---

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
zachowano   compat         added the EPUB 2 <guide> element for readers that look for it
ostrzeżenie accessibility  2 images have alt text that only repeats the filename
```

Treść wpisów jest na razie po angielsku — tłumaczenie wymaga przebudowy sposobu,
w jaki etapy tworzą komunikaty, i jest zaplanowane osobno.

### Poczucie humoru

Charakter tego narzędzia mieszka w dokumentacji i w stałych opisach interfejsu,
nie w komentarzu do każdego uruchomienia. W samej pracy jest dokładnie jedna
sucha uwaga i pojawia się rzadko: gdy plik przychodzi bez **żadnej** usterki, co
jest na tyle niecodzienne, że zasługuje na uniesioną brew. Poza tym program
milczy — dowcip po każdej książce przestaje bawić przy trzeciej, a obok
ostrzeżenia zwyczajnie przeszkadza.

---

## Jak to jest zbudowane

```
odczyt → czcionki → obrazy → struktura → metadane → xhtml → css
       → nawigacja → dostępność → zgodność → zapis
```

Kolejność jest nośna i udokumentowana w `epubforge/stages/__init__.py`:

- **czcionki przed metadanymi** — deobfuskacja opiera się na *źródłowym*
  identyfikatorze, który normalizacja może wymienić;
- **struktura przed treścią** — zamraża mapę ścieżek, od której zależy
  przepisywanie odnośników;
- **dostępność przed zgodnością** — musi zmierzyć samą książkę, a nie ustępstwa
  dołożone na wierzch;
- **zgodność na końcu** — to jedyny etap, który świadomie odchodzi od standardu,
  i żaden wcześniejszy nie musi o tym wiedzieć.

Warstwy: `reader.py` sprowadza dowolny plik do modelu (`model.py`), etapy w
`stages/` go przekształcają, `writer.py` składa z niego kontener. Nic w modelu
nie wie o ZIP-ie ani o składni OPF.

### Gwarancje

Trzy własności wyniku są sprawdzane jako całość, niezależnie od tego, co robi
którykolwiek etap. Mają własny plik testów, bo są innej kategorii niż testy
zachowania: test zachowania mówi „ta usterka jest naprawiana", te mówią
„cokolwiek dołożysz, wynik nadal to spełnia".

| | Własność |
|---|---|
| **K1** | Ani jeden znak tekstu czytelnego nie ginie. Zawartość `<body>` w kolejności spine jest identyczna przed i po. |
| **K2** | Wynik jest funkcją wejścia. Dwa uruchomienia dają te same bajty — jedyna ruchoma część, `dcterms:modified`, daje się przypiąć przez `--modified` albo `SOURCE_DATE_EPOCH`. |
| **K3** | Drugi przebieg nic nie zmienia. Idempotencja na poziomie zawartości plików, nie ich nazw. |

Komplet zasad, wraz z testami, które ich pilnują, jest w
[`CONTRIBUTING.md`](CONTRIBUTING.md).

### Przegląd biblioteki

```bash
epubforge survey ~/Ebooki --json przeglad.json
```

Przepuszcza całą bibliotekę przez pełny potok, **niczego nie zapisując**, i daje
jedną rankingową listę: która usterka w ilu książkach. Sto osobnych raportów to
sto rzeczy do przeczytania; to jest jedna odpowiedź na pytanie, co warto naprawić
najpierw. Reguła napisana z jednej książki jest zgadywaniem — ta sama usterka
w czterdziestu jest faktem.

Nazwy plików **nie trafiają** do wyniku, chyba że poprosisz o to przez
`--with-names`. Przegląd ma się dać komuś pokazać, a lista tytułów mówi więcej
o Twojej półce niż o narzędziu.

W wersji instalowanej najprościej użyć skrótu **Menu Start → EPUB F.O.R.G.E. →
„Wiersz polecen"** — otwiera konsolę z `epubforge` już dostępnym. Krok po kroku:
[`docs/KORPUS.md`](docs/KORPUS.md).

### Inwentarz biblioteki

```bash
epubforge inventory ~/Ebooki --json spis.json --map mapa.txt
```

Przegląd mówi, **co narzędzie zrobiło**; inwentarz mówi, **czym te książki są**.
To pytanie wcześniejsze i mniej oczywiste: przegląd potrafi wymienić wyłącznie te
usterki, które narzędzie już umie nazwać, więc sam siebie nie zaskoczy.

Mierzone jest pochodzenie (ślady Calibre, InDesigna, Worda, konwersji z PDF-u —
jako **lista**, bo pliki bywają warstwowe), uszkodzenia (eksplozja klas, zupa
spanów, martwy CSS, atrybuty prezentacyjne) i typografia (formy cudzysłowów
i pauz, wielokropki, twarde spacje, mojibake, dywizy zostawione przez łamanie
wierszy). To jest materiał, na którym dopiero da się rozstrzygnąć, **które reguły
w ogóle warto pisać** — biblioteka w 70% po Calibre potrzebuje czego innego niż
taka, w której połowa to konwersje z PDF-u.

Wynik to same liczby i częstości znaków. `--map` zapisuje osobno powiązanie
skrótu z nazwą pliku i **jest jedynym plikiem, który nazywa Twoje książki** —
nie powstaje, dopóki o niego nie poprosisz.

### Testy

```bash
pytest
```

Zestaw przebudowuje plik testowy zawierający opisane wyżej uszkodzenia
i sprawdza wynik — w tym, jeśli EPUBCheck jest zainstalowany, że tryb `strict`
waliduje się z zerem błędów i zerem ostrzeżeń, również z włączonymi wszystkimi
profilami zgodności.

Osobno działa regresja na prawdziwych książkach — pełna instrukcja w
[`docs/KORPUS.md`](docs/KORPUS.md). Nie mogą one trafić do
publicznego repozytorium, więc leżą w katalogu z `.gitignore`, a wersjonowane są
wyłącznie **metryki**: liczby błędów EPUBCheck, dotrzymanie niezmiennika tekstu,
kształt raportu i skrót wyniku — osobno dla trybu `preserve` i `strict`. Podpisy
nazywane są skrótem książki, nie jej tytułem: treść i tak nie wyciekała, ale lista
tytułów w publicznym repozytorium to ta sama klasa informacji, której cały ten
mechanizm ma nie ujawniać. Test pomija się sam, gdy katalogu nie ma.
Szczegóły w [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Budowanie paczki

Wymaga JDK 17+ (dla `jlink`) i `pip install pyinstaller`.

```bash
python packaging/build.py                # pobiera EPUBCheck, linkuje JRE, zamraża
python packaging/build.py --skip-java    # ~60 MB, bez walidacji
python packaging/smoke_test.py           # uruchamia wynik z wyczyszczonym środowiskiem
```

Wynik trafia do `dist/EPUB-Forge/`. `smoke_test.py` czyści `PATH`, `JAVA_HOME`
i `EPUBCHECK_JAR` przed uruchomieniem zbudowanych plików wykonywalnych, więc
wykryje sytuację, w której paczka po cichu polega na czymś zainstalowanym na
maszynie budującej.

Instalatory Windows powstają przez `.github/workflows/build-windows.yml`.
Wypchnij tag `v*`, żeby wydać wersję, albo uruchom workflow ręcznie.

---

## Ograniczenia

- **DRM nie jest ruszany.** Prawdziwe szyfrowanie jest wykrywane, odrzucane
  i raportowane.
- Książki o stałym układzie przechodzą z zachowanymi właściwościami
  `rendition:*`, ale ich pozycjonowanie nie jest przeliczane.
- Nazwy plików są sprowadzane do ASCII, z transliteracją znaków, których Unicode
  nie rozkłada (`okładka.png` → `okladka.png`, `Żółć.xhtml` → `Zolc.xhtml`).
  Odnośniki są przepisywane.
- Warstwa typograficzna — cudzysłowy, pauza dialogowa, twarde spacje, mojibake —
  **nie istnieje**. To jedyna duża kategoria „syfu po generatorach", której
  narzędzie nie rusza; jest świadomie zaplanowana na koniec, bo jako jedyna łamie
  gwarancję K1. Patrz [`docs/ROADMAP.md`](docs/ROADMAP.md).
- Cała książka jest trzymana w pamięci. Dla pojedynczego pliku bez znaczenia,
  przy wsadzie liczonym w tysiącach — istotne.
- Treść raportu jest po angielsku.

---

## Rozwój

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — reguły, których nowa funkcja nie może
  złamać, każda ze wskazaniem testu, który jej pilnuje.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — co dalej, w jakiej kolejności i dlaczego
  akurat takiej.
- [`docs/KORPUS.md`](docs/KORPUS.md) — **instrukcja krok po kroku** dla właściciela
  biblioteki: jak pomóc projektowi, nie wypuszczając z dysku ani jednej książki.

### Wersja i dojrzałość to dwie różne rzeczy

To jest **pre-alpha**. Program mówi to o sobie sam, wszędzie tam, gdzie podaje
wersję:

```
epub-forge 0.1.0 (pre-alpha)
```

Numer wersji nie próbuje już nieść tej informacji, bo się do tego nie nadaje —
liczba rosnąca w stronę 1.0 czyta się jako postęp ku wydaniu niezależnie od tego,
co ktoś miał na myśli. PATCH podbija się przy każdym wydaniu, cokolwiek zawiera;
MINOR wyłącznie razem z etapem dojrzałości, po odhaczeniu wypisanych warunków.

| Etap | | |
|---|---|---|
| **pre-alpha** | `0.1.x` | prototyp; działa na książkach autora, korpusu nie ma |
| **alpha** | `0.2.x` | poprawność sprawdzana na 30+ prawdziwych książkach, raport przetłumaczony |
| **beta** | `0.3.x` | kompletne, używane przez kogoś poza autorem |
| **1.0** | | stabilne — pełne warunki w [`CONTRIBUTING.md`](CONTRIBUTING.md) |

Co to znaczy w praktyce: narzędzie **nigdy nie nadpisuje pliku źródłowego** i to
jest własność pilnowana testem, ale poza tym trzymaj oryginały. To jest prototyp
i tak się nazywa.

---

## Autorzy i licencja

- **Łukasz „LuKi” Kniotek** — pomysł, kierunek i wymagania
- **Claude (Anthropic)** — projekt i implementacja

Licencja MIT — patrz [`LICENSE`](LICENSE), gdzie wymieniono też licencje
komponentów dołączanych do paczek (EPUBCheck, OpenJDK, Qt).
