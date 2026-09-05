# EPUB F.O.R.G.E. — opis aplikacji: cel, zamysł, zasady

Ten dokument jest dla kogoś, kto widzi to repozytorium pierwszy raz i ma je
ocenić albo zmienić — audytora, nowego współpracownika, kolejnego agenta.
Mówi, **po co** ten program istnieje i **czego się od niego wymaga**, zanim
powie, jak jest zbudowany. Szczegóły techniczne są w `CONTRIBUTING.md`,
historia zmian w `CHANGELOG.md`, obsługa w `README.md` (po polsku)
i `README.en.md` (po angielsku).

---

## 1. Cel w jednym zdaniu

Program bierze książkę elektroniczną, której **kod jest źle zrobiony** —
EPUB od wydawcy, z księgarni, z konwertera — i oddaje **EPUB 3.3 zbudowany
poprawnie, wyglądający na czytniku dokładnie tak, jak wydawca chciał**, tylko
bez błędów, które przeszkadzały mu tak wyglądać.

Słowami właściciela projektu: *wykrywanie i naprawianie błędów w uszkodzonym
formatowaniu i treści ebooków i ich odbudowa w nowym, czystym kontenerze.*

Użytkownikiem jest właściciel i jego prywatna półka legalnie kupionych
książek. **Miarą sukcesu jest półka:** każda książka wychodzi lepsza albo
nietknięta, nigdy gorsza.

## 2. Zamysł — trzy zdania, które rozstrzygają spory

1. **Naprawiaj kod, nie zmieniaj obrazu.** Wygląd książki to intencja
   wydawcy; kod książki to sposób, w jaki wydawca tę intencję zapisał.
   Program ma prawo zmieniać sposób zapisu, nie ma prawa zmieniać intencji.
   Konstrukcja niezgodna ze standardem, ale niosąca wygląd, jest
   **tłumaczona** na zgodny odpowiednik, nigdy kasowana; jeśli tłumaczenie
   zmieniłoby wygląd — niezgodność zostaje, z powodem w raporcie.
2. **Żaden znak tekstu nie ginie.** Nie „prawie żaden" i nie „liczba znaków
   się zgadza": każdy znak kolejności czytania źródła musi być w wyniku, w tej
   samej kolejności. To jest brama zapisu, nie ostrzeżenie — książka, która
   ją łamie, nie jest zapisywana.
3. **Gdy program nie wie — pyta; bez odpowiedzi nie zmienia nic.** Każde
   usunięcie czegokolwiek jest albo do odznaczenia w ustawieniach, albo
   poprzedzone pytaniem z opcjami, konsekwencjami i rekomendacją. Program nie
   zgaduje i nie „poprawia wszystkiego, co wygląda podejrzanie". Uruchomiony
   wsadowo bez człowieka zostawia treść dokładnie taką, jaka przyszła, i
   naprawia kod oraz kontener.

Kolejność przy konflikcie: **(1) treść nie może zniknąć, (2) wygląd nie może
się zmienić, (3) kod ma być poprawny.**

Każda rzecz w pliku należy do jednej z trzech klas:

| klasa | czym jest | co robi program |
|---|---|---|
| **intencja** | to, co wydawca ustawił świadomie: wcięcia, justowanie, kursywy, fonty, odstępy, kapitaliki, inicjały | zachowuje co do efektu, nawet jeśli musi przepisać na inny kod |
| **defekt kodu** | zapis, który nie robi tego, co wydawca chciał, albo robi to tylko na jednym czytniku: okładka bez reguły rozmiaru, encje HTML w XHTML, DOCTYPE 1.1 w EPUB 3, `font-style: regular`, brak generyka w font-stacku | naprawia automatycznie, gdy naprawa jest jednoznaczna, i wpisuje do raportu |
| **defekt treści** | tekst albo metadana błędna, ale bez pewności co do intencji: łącznik z konwersji („obo-jętna") kontra złożenie autora („czarno-czerwone"), zły `dc:language`, litera podmieniona systematycznie | wykrywa, klasyfikuje pewność, **pyta** albo zostawia z wpisem; nigdy nie rozstrzyga sam |

## 3. Co program robi

**Wejście:** plik EPUB (2 albo 3, dowolnie zepsuty — program czyta go
własnym czytnikiem, odbudowuje brakujący pakiet, odzyskuje uszkodzone
dokumenty) albo — od wersji w gałęzi rozwojowej — **PDF z warstwą tekstową**
(skan bez tekstu jest odmową; OCR to inny program). Katalogi całe.

**Wyjście:** nowy plik obok wejściowego (wejście nigdy nie jest nadpisywane;
zapis atomowy; nadpisanie istniejącego wyniku tylko z `--force`): EPUB 3.3,
a na życzenie także KEPUB dla czytników Kobo. Do tego **raport** (po polsku
albo po angielsku, w oknie, na konsoli i w JSON) i **bilans zmian**: co
weszło, co wyszło, i czy każdą różnicę tłumaczy wpis.

**Trzy tryby:** `preserve` (domyślny — naprawia zepsute, zostawia to, o czym
wydawca zdecydował), `strict` (zgodność ze standardem wygrywa z wyglądem tam,
gdzie się kłócą; do dystrybucji), `minimal` (tylko kontener, dokumentów nie
otwiera).

**Jak to działa w środku.** Program nie łata pliku: buduje **model książki w
pamięci** (`epubforge/model.py`) i przepuszcza go przez **potok etapów**
(`epubforge/stages/`), każdy z jedną odpowiedzialnością i uzasadnieniem
kolejności w kodzie: PDF (pytania właściwe dla PDF-a), fonty, obrazy,
struktura (nazwy plików z ról, okładka), metadane, profil książki, treść
(XHTML), style (CSS), typografia, łączniki, podmiany liter, przypisy, teksty
alternatywne obrazów, tabele, nawigacja, dostępność, profile zgodności
czytników, cięcie fontów, KEPUB. Na końcu **writer** (`epubforge/writer.py`)
pisze świeży kontener, a **bramy** decydują, czy w ogóle wolno go zapisać.

**Człowiek w pętli.** Pytania (`epubforge/decisions.py`, teksty w
`epubforge/question_texts.py`) mają opcje, konsekwencje i rekomendację;
odpowiedź może być stała dla całej partii, jest pamiętana obok pliku i
raport rozróżnia „nikt nie odpowiedział" od „odpowiedziano: zostaw". Wszystko,
co program potrafi, jest osiągalne z okna (PySide6) — okno nie jest
uproszczonym frontem do wiersza poleceń, a każde pole polityki ma swoją
kontrolkę.

## 4. Czego program nie robi

- nie zdejmuje DRM i nie będzie;
- nie konwertuje z MOBI ani z Worda; z PDF-a czyta tylko warstwę tekstową;
- nie usuwa niczego bez pytania albo bez przełącznika;
- nie zgaduje i nie naprawia treści bez człowieka;
- nie ma logiki „na tytuł", „na wydawcę", „na ISBN" — zero wyjątków dla
  konkretnych książek;
- nie jest klonem Calibre, edytorem ani ogólnym sanitizerem; nie generuje
  okładek, nie przemianowuje klas CSS bez dowodu, nie robi redakcji
  literackiej automatem, nie ma modelu językowego w pętli przetwarzania.

## 5. Dwanaście reguł niepodlegających negocjacji

Każda ma pilnujący ją test (`CONTRIBUTING.md` podaje który). Jeśli nowa
funkcja wymaga złamania którejś, funkcja jest źle zaprojektowana.

| # | reguła |
|---|---|
| K1 | ani jeden znak tekstu czytelnego nie ginie (podciąg znaków w kolejności czytania) |
| K2 | wynik jest funkcją wejścia: dwa uruchomienia dają te same bajty poza znacznikiem czasu, a i ten da się przypiąć |
| K3 | drugi przebieg nic nie zmienia (idempotencja na poziomie zawartości plików) |
| K4 | żadna deklaracja nie jest zmyślana: program deklaruje tylko to, co zmierzył |
| K5 | przy niepewności nie ruszamy: zachowaj i zaraportuj, albo zapytaj |
| K6 | każda zmiana ma wpis w raporcie; zmiana wysokiego ryzyka — pozycję w bilansie |
| K7 | `minimal` znaczy minimal: XHTML i CSS wychodzą bajt w bajt |
| K8 | model nie wie o ZIP-ie ani o składni OPF; format mieszka w czytniku i writerze |
| K9 | uzasadnienie mieszka przy kodzie („X przed Y, **bo** …") |
| K10 | stan, który musi przeżyć zapis, jest w pliku, nigdy tylko w pamięci przebiegu |
| K11 | deklaracja nie jest pomiarem: rozszerzenie, nagłówek ZIP, pusty atrybut — sprawdzamy na materiale |
| K12 | model jest kontraktem: konstrukcja nieodczytana do modelu znika z wyniku, więc każda taka strata jest naprawiona albo świadomie wpisana z powodem |

**Cztery jakości, oceniane osobno** — sukces w jednej nie kompensuje porażki
w innej: zgodność techniczna (EPUBCheck 5.3.0), integralność semantyczna (K1,
bilans zasobów i atrybutów, graf odwołań, metadane), wierność wizualna
(render przed/po w przypiętym Chromium; strona ze stratą blokuje zapis),
jakość operacyjna (determinizm, budżety pamięci i czasu, raport, pytania,
odporność na złośliwe archiwa). Zwykła publikacja wymaga wszystkich czterech.

## 6. Jak program dowodzi, że działa

- **Suita testów** (`tests/`, ok. 3 700 testów): każda reguła K ma test;
  reguła raportu bez miejsca, które ją podnosi, nie przechodzi; identyfikator
  reguły musi być literałem przy wywołaniu; teksty pytań i reguł istnieją po
  polsku i po angielsku; kilkadziesiąt testów pilnuje, że README mówi prawdę
  o kodzie. Testy bramy renderu (Chromium) i testy z prawdziwym PDF-em z
  korpusu są opcjonalne i skaczą z powodem, gdy silnika nie ma.
- **Korpusy publiczne** (`tests/corpus_gutenberg/`, `tests/corpus_public/`,
  `tests/corpus/`) z nagranymi sygnaturami wyjścia: zmiana wyjścia na
  którejkolwiek książce musi być zamierzona i nagrana na nowo.
- **Bramy** przy zapisie: K1, bilans (żaden zasób ani atrybut semantyczny nie
  znika bez wpisu), niezmienniki modelu, EPUBCheck w trybie ścisłym, render.
- **Kontrakt transformacji** (`epubforge/transformation.py`): każda zmiana,
  która zabiera czytelny tekst, jest opisana **przed** wykonaniem, z warunkiem
  końcowym; gdy warunek nie wyjdzie, dokument wraca do stanu sprzed zmiany.
- **CI** (`.github/workflows/tests.yml`): na każdy push cała suita dwa razy
  pod różnym ziarnem hasha oraz osobno na maszynie **bez walidatora i bez
  Javy** — bo trzy razy z rzędu ktoś z inną maszyną niż autor znajdował test,
  który padał tylko tam.
- **Półka właściciela** (160 książek, prywatne, nigdy w tym repozytorium):
  odciski całego wyjścia przed i po każdej zmianie w potoku, przebiegi całej
  półki z pełnym renderem, K3 mierzone na półce (drugi przebieg: 0 zmian
  w 60 książkach).
- **Audyty**: samoocena i tury niezależnych audytorów, z rejestrem ustaleń,
  w którym sprawdzenie autora jest **materiałem**, a werdykt należy do
  audytora. Rejestr, decyzje właściciela, rekordy przebiegów i lekcje żyją
  w **prywatnym repozytorium notatek**, nie tutaj.

## 7. Mapa repozytorium

| gdzie | co |
|---|---|
| `epubforge/reader.py`, `epubforge/pdf.py` | czytniki: EPUB (z odbudową uszkodzonego pakietu) i PDF (warstwa tekstowa → ten sam model) |
| `epubforge/model.py` | model książki — kontrakt (K12) |
| `epubforge/stages/` | potok etapów; `stages/__init__.py` podaje kolejność **z powodami** |
| `epubforge/pipeline.py` | przebieg, budżety, bramy, publikacja |
| `epubforge/writer.py`, `epubforge/ocf.py` | nowy kontener |
| `epubforge/fidelity.py`, `epubforge/balance.py`, `epubforge/invariants.py`, `epubforge/render_fidelity.py` | bramy: K1, bilans, niezmienniki, render |
| `epubforge/decisions.py`, `epubforge/question_texts.py`, `epubforge/memory.py` | pytania, ich teksty, pamięć odpowiedzi |
| `epubforge/rules.py`, `epubforge/report.py` | katalog reguł raportu (EN i PL), raport, bilans zmian |
| `epubforge/policy.py`, `epubforge/cli.py`, `epubforge/gui/` | polityka (każde pole = przełącznik i kontrolka), wiersz poleceń, okno |
| `epubforge/hyphens.py`, `epubforge/dictionaries.py`, `epubforge/typography.py`, `epubforge/substitutions.py`, `epubforge/watermark.py` | defekty treści: łączniki (ze słownikiem hunspell), typografia, podmiany liter, znaki wodne i śmieci księgarni |
| `epubforge/validate.py`, `epubforge/render.py` | EPUBCheck (przypięty, sterownik JVM), silnik renderu (przypięty Chromium) |
| `epubforge/kepub.py`, `epubforge/compat.py` | eksport KEPUB, profile zgodności czytników |
| `tests/` | suita; `tests/factory.py` i `tests/kitchen_sink.py` — materiał syntetyczny; korpusy publiczne |
| `tools/` | narzędzia pomiarowe używane w repozytorium |
| `packaging/` | build Windows (PyInstaller), przypięte sumy EPUBCheck, Chromium i słowników |
| `CHANGELOG.md` | **każda zmiana z powodem i pomiarem**, książki numerami |
| `CONTRIBUTING.md` | reguły, jak dodać etap, jak sprawdzić, że nic się nie popsuło, wersjonowanie, prywatność |

## 8. Co warto wiedzieć przed audytem

- **Stan.** Wydana wersja to `0.3.1` (alpha; wydawany jest tylko Windows).
  Gałąź rozwojowa niesie ponad nią: eksport KEPUB, PDF jako wejście,
  wykonanie rekomendacji dwóch audytów i kilka napraw K3 — wszystko opisane
  w `CHANGELOG.md` pod „Unreleased". Nic z tego nie jest wydane.
- **Prywatność.** Repozytorium kodu jest publiczne; półka właściciela jest
  prywatna. Żadna nazwa książki, autora ani wydawcy z półki nie ma prawa tu
  trafić — w dokumentach książki to „Książka N" albo numer. To jest reguła
  domowa, której złamanie nie jest błędem w kodzie, a mimo to jest błędem.
- **Czego nie da się sprawdzić z tego repozytorium.** Przebiegów na półce
  (prywatna), prób na fizycznych czytnikach (jedna, Kobo, 2026-08-04 —
  Kindle, Apple, RMSDK i KEPUB nigdy na sprzęcie), progów czytnika PDF
  (ustawione na materiale zastępczym: korpus złożony drugim składaczem;
  PDF-y właściciela jeszcze nie istnieją).
- **Znane granice, świadomie.** Dwie kolumny w PDF-ie są czytane po kolei,
  ale nie przekładane; tabele z PDF-a wchodzą jako akapity; K1 pilnuje
  strumienia znaków, nie podziału na akapity (na to są sygnatury korpusu);
  55 szerokich `except Exception` stoi z argumentem, że każde pominięcie
  jest w raporcie — audytor może to zakwestionować.
- **Jak uruchomić.** Python 3.10+; `pip install --require-hashes -r
  requirements.lock` i `pip install -e . --no-deps`; `pytest -q`. EPUBCheck
  stawia `packaging/build.py` (`EPUBCHECK_JAR`); silnik renderu wskazuje
  `EPUBFORGE_CHROME`, testy renderu i PDF-ów z korpusu włącza
  `EPUBFORGE_RENDER_TESTS=1`; słowniki hunspell (`pl_PL`, `en_US`) nie są
  w gicie — `EPUBFORGE_DICTIONARIES` wskazuje katalog z nimi. Bez tych
  trzech rzeczy program działa, robi mniej i **mówi w raporcie, czego nie
  sprawdził**.

## 9. Słowniczek

- **etap** — jeden krok potoku z jedną odpowiedzialnością (`stages/`).
- **brama** — sprawdzenie przed zapisem, które może odmówić publikacji.
- **bilans** — zestawienie wejście → wyjście: pliki, zasoby, atrybuty
  semantyczne, znaki; różnica bez wpisu to błąd.
- **reguła raportu** — stały identyfikator wpisu (`nav.cover-page-generated`,
  `hyphens.joined`…) z tekstem po polsku i po angielsku w `rules.py`.
- **pytanie** — decyzja, której program nie podejmuje sam; ma opcje,
  konsekwencje, rekomendację i grupę (odpowiedź może być stała dla grupy).
- **odcisk półki** — skrót wyjścia i raportu każdej książki półki, brany
  przed i po zmianie w potoku, żeby udowodnić, że refaktor nie ruszył bajtu.
- **preserve / strict / minimal** — trzy tryby (rozdział 3).
- **K1–K12** — reguły z rozdziału 5; **S-…** — reguły domowe współpracy
  z właścicielem (m.in. S-02 każde usunięcie za kratką albo pytaniem, S-05
  brak odpowiedzi to brak zmiany, S-06 prywatność półki, S-12 sprawdzenie
  autora to materiał, werdykt należy do audytora).
