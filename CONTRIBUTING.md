# Zasady pracy nad EPUB F.O.R.G.E.

Ten plik nie opisuje, co narzędzie robi — od tego jest [`README.md`](README.md)
(po angielsku: [`README.en.md`](README.en.md)). Opisuje, czego **nie wolno
złamać**, dodając cokolwiek nowego, i jak się tu pracuje. Wersja publiczna;
pełny zapis decyzji, pomiarów i rejestr ustaleń mieszka w prywatnym
repozytorium notatek, bo mówi o prywatnych książkach.

---

## Reguły niepodlegające negocjacji

Każda ma pilnujący ją test. Jeśli nowa funkcja wymaga złamania którejś, to nie
jest powód do złamania reguły — to sygnał, że funkcja jest źle zaprojektowana.

| # | Reguła | Pilnuje |
|---|---|---|
| **K1** | **Ani jeden znak tekstu czytelnego nie ginie.** Tekst wewnątrz `<body>`, w kolejności spine, po zwinięciu białych znaków, jest identyczny przed i po; proza dokumentu przeniesionego ze źródła wychodzi co do znaku identyczna. To niezmiennik *strumienia znaków*, nie struktury. | `test_rebuild_preserves_every_readable_character`, `fidelity.text_is_preserved` |
| **K2** | **Wynik jest funkcją wejścia.** Dwa uruchomienia na tym samym pliku dają te same bajty, poza `dcterms:modified` — a i to daje się przypiąć (`--reproducible`, `--modified`, `SOURCE_DATE_EPOCH`). | `test_output_is_byte_reproducible`, `test_zip_entries_carry_no_wall_clock_timestamp` |
| **K3** | **Drugi przebieg nic nie zmienia.** Idempotencja na poziomie zawartości plików. | `test_second_pass_changes_nothing_but_the_timestamp` |
| **K4** | **Żadna deklaracja nie jest zmyślana.** Narzędzie deklaruje wyłącznie to, co zmierzyło — metadane dostępności, każde `<meta>`. | `TestEmptyAltIsNeverADescription`, `TestAccessibility*` |
| **K5** | **Przy niepewności nie ruszamy.** Nieczytelny selektor, niejednoznaczna struktura, nieznana konstrukcja → zachowaj i zaraportuj, albo zapytaj. | `cascade.py`, `TestImageParagraphs`, kolejka decyzji |
| **K6** | **Każda zmiana ma wpis w raporcie.** Zmiana bez wpisu jest błędem, nawet jeśli merytorycznie poprawna; zmiana wysokiego ryzyka ma dodatkowo pozycję w bilansie. | `test_a_real_rebuild_never_reports_zero_changes`, `balance.reconcile` |
| **K7** | **`minimal` znaczy minimal.** Pliki XHTML i CSS wychodzą bajt w bajt. | `test_minimal_mode_leaves_content_files_byte_identical` |
| **K8** | **Model nie wie o ZIP-ie ani o składni OPF.** Wiedza o formacie mieszka w `reader.py` i `writer.py`. | przegląd kodu |
| **K9** | **Uzasadnienie mieszka przy kodzie.** Nie „fonts, images, structure", tylko „fonts **przed** metadata, **bo** deobfuskacja kluczuje się na źródłowym identyfikatorze". | `stages/__init__.py` jest wzorcem |
| **K10** | **Stan, który musi przeżyć zapis, zapisuje się do pliku — nigdy do `Context`.** | patrz niżej |
| **K11** | **Deklaracja nie jest pomiarem.** Rozmiar z nagłówka ZIP, rozszerzenie, pusty atrybut — sprawdzamy na materiale albo traktujemy jako nieznane. | `TestArchiveLimits`, `TestDocumentSelection` |
| **K12** | **Model jest kontraktem.** Konstrukcja nieodczytana do modelu znika z wyniku bez śladu; każda taka strata jest naprawiona albo wpisana na listę świadomych pominięć z powodem. | `test_nothing_leaves_the_package_document_unnoticed` |

### O zakresie K1

K1 skleja tekst i zwija białe znaki, więc łapie: zgubione słowo, zjedzoną
literę, przestawiony akapit. **Nie łapie**: scalenia dwóch akapitów w jeden,
rozbicia jednego na dwa, zamiany `<p>` na `<div>`, ani zmiany atrybutu.
Sygnatura korpusowa liczy bloki tekstowe; zmiana ich liczby jest widoczna
w `--record`. Każda reguła zmieniająca podział na bloki albo atrybuty
semantyczne musi mieć własne zabezpieczenie ponad K1.

### O K10

Etap treści wstawiał kiedyś `alt=""` obrazkom bez żadnego i zapamiętywał
w `Context`, że zrobił to sam; etap dostępności czytał tę notatkę. Notatka żyła
jeden przebieg, a wynik wracał z dysku — przy drugim przebiegu pusty `alt` był
nie do odróżnienia od decyzji wydawcy. Poprawka nie polegała na zapisaniu
notatki, tylko na usunięciu potrzeby jej istnienia: pusty `alt` nigdy nie
liczy się jako opis. Wniosek ogólny: jeśli poprawność wyniku zależy od czegoś,
co wiesz tylko w trakcie tego uruchomienia, przeprojektuj regułę.

### O K11 i K12

K4 pilnuje tego, co narzędzie twierdzi na wyjściu, K11 tego, co przyjmuje na
wejściu, K12 tego, co gubi po drodze. Test przy przeglądzie kodu: *gdyby ten
plik był złośliwy, co musiałby napisać, żeby ta linijka zrobiła coś złego?*
Jeśli odpowiedź jest krótka, linijka łamie K11. `tests/kitchen_sink.py` trzyma
po jednym egzemplarzu każdej konstrukcji z EPUB 3.3 §5, a lista
`DROPPED_ON_PURPOSE` jest dokumentacją decyzji, nie workiem na wyjątki.

---

## Trzy zasady o człowieku

1. **Wszystko, co niepewne, idzie przez pytanie.** Pytanie ma streszczenie,
   szczegół, opcje z konsekwencjami, rekomendację i informację, czy da się
   cofnąć. Bez odpowiedzi nic się nie zmienia. Rekomendacja programu nigdy nie
   jest stosowana sama.
2. **Cokolwiek program usuwa, jest do odznaczenia albo do potwierdzenia** —
   bez wyjątków. Kod, który nie może niczego narysować (martwe reguły
   generatorów, resztki konwerterów), jest usuwalny z wpisem w raporcie, za
   kratką.
3. **Każde ustawienie jest osiągalne z okna i z wiersza poleceń.** Pilnują
   tego `tests/test_gui_reaches_everything.py` i
   `tests/test_cli_reaches_everything.py`; wyjątek wymaga podanego powodu.

---

## Dodawanie etapu

```python
class NowyStage(Stage):
    name = "nowy"          # ta sama nazwa, co kategoria w raporcie

    def run(self, ctx: Context) -> None:
        ...
```

Zanim etap uznasz za gotowy:

- [ ] miejsce w kolejności udokumentowane zdaniem „X przed Y, bo…" w `stages/__init__.py` (K9);
- [ ] respektuje `policy.rewrite_content` — w `minimal` nie rusza XHTML ani CSS (K7);
- [ ] respektuje `policy.strict` — jeśli robi kompromis wygląd kontra standard, ma obie ścieżki;
- [ ] każda zmiana ma `self.note(...)` na poziomie `FIX` albo `PRESERVED` (K6), a każda ryzykowna — `self.changed(...)`;
- [ ] identyfikator reguły ma przedrostek równy nazwie etapu i wpis w `rules.py` po polsku i po angielsku z tymi samymi polami (`tests/test_rules.py` trzyma zapadki);
- [ ] nie zostawia modelu w połowie zmienionego przy wyjątku — wyjątek etapu przerywa cały przebieg i nic nie zostaje zapisane (`tests/test_failure_injection.py` obejmuje każdy etap);
- [ ] jeśli tylko mierzy, deklaruje `mutates = False` — potok sprawdzi odcisk modelu;
- [ ] fixture w `tests/factory.py` z usterką, którą etap leczy, i **test, że etap nie rusza materiału, którego nie powinien** — ważniejszy niż ten, że naprawia;
- [ ] `pytest tests/test_invariants.py` dalej przechodzi;
- [ ] wpis w `CHANGELOG.md` (sekcja *Unreleased*), a jeśli etap jest widoczny dla użytkownika — w obu README.

---

## Jak sprawdzić, że nic się nie popsuło

```bash
pytest -q                                   # cała suita; bez Javy, silnika, słowników pomija z powodem
python tools/jak-ci.py                      # jak na maszynie budującej wydanie
EPUBFORGE_RENDER_TESTS=1 pytest -q          # plus testy rysujące strony (EPUBFORGE_CHROME)
python -m tests.test_public_corpus --record # nowa sygnatura korpusu, gdy zmiana wyniku jest zamierzona
python packaging/release_check.py           # przed słowem „wydane": ma powiedzieć Nothing owed.
```

Testy wymagające Javy (EPUBCheck), silnika rysującego albo słowników pomijają
się i mówią, dlaczego — czytaj powody pomięć (`pytest -rs`), nie licz ich.

### Korpus

Syntetyczne fixture'y w `tests/factory.py` potwierdzają to, co już wiemy.
Prawdziwe książki potwierdzają resztę — ale są cudzymi utworami i **nigdy nie
trafiają do repozytorium**. W repozytorium są wyłącznie sygnatury (liczby
i skróty), nigdy treść ani tytuł; nazwa pliku sygnatury to skrót książki. Korpus
publiczny (`tests/corpus_public`, `tests/corpus_gutenberg`) każdy może
uruchomić; prywatna półka autora jest mierzona osobno, a wyniki są cytowane
w changelogu liczbami i rolami („Książka 1"), nigdy tytułami.

---

## Wersjonowanie

Numer wersji liczy wydania, nie mierzy dojrzałości. Dojrzałość mówi
`__stage__` obok `__version__` w `epubforge/__init__.py` i widać ją wszędzie
tam, gdzie widać wersję:

```
epub-forge 0.3.1 (alpha)
```

| Etap | MINOR | Co to znaczy |
|---|---|---|
| **pre-alpha** | `0.1.x` | prototyp, działa na książkach autora |
| **alpha** | `0.2.x` | zakres funkcji ustalony, poprawność sprawdzana na prawdziwych plikach |
| **beta** | `0.3.x` | kompletne i sprawdzone na całej półce (osiem punktów sprawdzalnych poleceniem) |
| **1.0** | `1.0.0` | stabilne: dwa wydania bez nowego defektu z korpusu, API niezmienione, instalator sprawdzony na czystym Windowsie |

**MINOR podbija się wyłącznie razem z etapem** albo gdy właściciel nazwie
wydanie po ukończonym, zaudytowanym planie. **PATCH podbija się przy każdym
wydaniu**, cokolwiek zawiera. Praca między wydaniami idzie do sekcji
*Unreleased* w `CHANGELOG.md`; przy wydaniu sekcja dostaje numer i datę.

### Wydanie

„Wydane" ma definicję maszynową: **tag i wydanie istnieją na zdalnym
repozytorium** — sprawdza to `packaging/release_check.py`, i dopóki nie wypisze
`Nothing owed.`, właściwe zdanie brzmi „gotowe do wydania, brakuje: …". Build
Windows (PyInstaller + Inno Setup, z przypiętym silnikiem rysującym i EPUBCheck
o sprawdzonej sumie) uruchamia się przez *Actions → Build Windows → Run
workflow* z tagiem w polu `release_tag`; workflow zakłada tag na commicie,
który właśnie zbudował i przetestował. Notatki wydania to sekcja changeloga
dla tej wersji — jej brak przerywa wydanie. Wydanie kamienia milowego dostaje
gałąź `frozen/vX.Y.Z-<kamień>`, która nigdy się nie porusza.

Kształt wpisu wydaniowego: jedno zdanie, o co chodziło; tabela „at a glance"
ze skalą po prawej; nowe/naprawione w dwóch zdaniach; pełne opisy z reprodukcją
albo liczbą. Czytany na trzech głębokościach, bo tak jest czytany.

---

## Metryki, po których poznajemy, że jest lepiej

| Wskaźnik | Cel |
|---|---|
| błędy EPUBCheck po przebudowie w trybie `strict` | 0 na 100 % korpusu |
| naruszenia K1 | 0, zawsze, bez wyjątku |
| książki dające ten sam bajt przy drugim przebiegu | 100 % |
| **stosunek `naprawiono` do `zachowano`** | **nie rośnie** między wydaniami |
| książki, na których jakiś etap rzucił wyjątkiem | 0 |
| błędy walidatora **wprowadzone** względem źródła | 0 |

Czwarty wiersz jest najważniejszy. Naturalny dryf każdego narzędzia tej klasy
prowadzi do „naprawiania" coraz większej liczby rzeczy, aż wszystkie książki
zaczynają wyglądać tak samo; ten wskaźnik jest jedyną obroną i pilnujemy go
z tą samą powagą co K1.

---

## Czego świadomie nie robimy

| Nie robimy | Dlaczego |
|---|---|
| łamania DRM | wykrywamy, odmawiamy, raportujemy |
| konwersji formatów (MOBI/AZW3/PDF → EPUB) | inne narzędzie; zaczynamy tam, gdzie konwerter kończy |
| edycji treści bez pytania | korekta literówek i „poprawianie" stylu autora — nawet gdy kusi; program może **pytać**, czy to błąd, nie wolno mu **rozstrzygać** |
| generowania okładek | zmyślanie, tylko graficzne (K4) |
| przemianowywania klas CSS poza jednym wersjonowanym słownikiem | nazwa per książka to chaos; słownik `epubforge` jest deterministyczny, z mapą starych nazw w raporcie |
| przeliczania układu fixed-layout | nie da się bez renderowania; deklarowane jako ograniczenie |
| automatycznego deklarowania zgodności WCAG | maszynowo nieustalalne; to oświadczenie wydawcy (K4) |
| LLM w pętli przetwarzania | niedeterministyczne, więc łamie K2 |
| logiki per tytuł / ISBN / wydawca / nazwa pliku | `tests/test_no_book_specific_logic.py` |

---

## Prywatność

W publicznym repozytorium nie ma tytułów, nazwisk, identyfikatorów pakietów
ani fragmentów cudzych książek — również w testach, sygnaturach i changelogu.
Przed każdym wydaniem repozytorium przechodzi skaner nazw własnych, który żyje
poza nim. Humor jest dozwolony w README i tekstach statycznych okna, nigdy
w raporcie i nigdy w kodzie.

## Licencja

GNU GPL v3 lub późniejsza — patrz [`LICENSE`](LICENSE). Wkład do repozytorium
oznacza zgodę na tę licencję.
