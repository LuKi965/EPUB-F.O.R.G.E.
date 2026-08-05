# Sześć prawdziwych książek

Z Project Gutenberg, w domenie publicznej, commitowane razem ze źródłem — bo
test korpusowy, który u wszystkich poza jedną osobą jest pomijany, niczego nie
pilnuje.

| Plik | Język | Rozmiar | Czym się różni |
|---|---|---|---|
| `pan-tadeusz.epub` | pl | 1,2 MB | najdłuższa, 14 ilustracji |
| `oliver-twist-vol-2-of-3.epub` | en | 807 KB | 8 ilustracji, tom ze zbioru |
| `king-arthur-and-the-knights-of-the-r.epub` | en | 334 KB | najwięcej bloków |
| `camille-la-dame-aux-camilias.epub` | en | 248 KB | jedna ilustracja, długi tekst |
| `tajemnica-baskerville-w-dziwne-przyg.epub` | pl | 229 KB | polskie znaki w treści |
| `romeo-i-julia.epub` | pl | 152 KB | najmniejsza; dramat, nie proza |

Wszystkie pochodzą z tego samego generatora (`ebookmaker`), więc **nie**
poszerzają pokrycia rodzin generatorów z [`docs/ROADMAP.md`](../../docs/ROADMAP.md).
Ich wartość jest inna: to jedyne książki, które wolno tu trzymać, więc dzięki
nim regresja korpusowa biegnie w CI u każdego.

Pliki są niezmienione — dokładnie tak, jak zostały pobrane, razem z licencją
Project Gutenberg w środku, która na tych warunkach pozwala je rozpowszechniać.
Przebudowane wersje nie są commitowane; w `expected/` leżą tylko sygnatury,
czyli liczby i skróty.

## Co znalazły od razu

Pole `text_invariant` wychodziło **fałszywe na wszystkich sześciu** — i nie
dlatego, że tekst ginął. Porównywało liczby znaków przez równość, a przebudowa
generuje stronę okładki, co dokłada dwa znaki. K1 mówi, że żaden znak nie ma
**zginąć**; nie mówi, że żadnego nie wolno dodać. Poprawka jest w
`epubforge/corpus.py::_text_survived` i sprawdza teraz to, co K1 naprawdę
stwierdza: cały tekst źródła nadal jest w wyniku, w tej samej kolejności.

Żadna książka wymyślona na potrzeby testu by tego nie pokazała, bo wszystkie
mają okładkę w spine.
