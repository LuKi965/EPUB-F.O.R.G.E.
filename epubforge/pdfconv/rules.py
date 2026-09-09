"""What the converter's report lines say, in both languages.

They live here and not in `epubforge/rules.py` for the reason the whole module
does (D-056): a line that only ever appears in a report about a PDF is the
converter's text, and the repair core's catalogue should not carry it. They are
merged into that catalogue by `install()`, so every test and every reader of a
report still finds them in one place — the catalogue is the program's, the
authorship is the module's.
"""

from __future__ import annotations

#: `rule identifier -> the sentence`, English.
CATALOGUE: dict[str, str] = {
    "pdf.converted": "the PDF's text layer was read into a book: {pages} page(s), {lines} line(s) joined into {paragraphs} paragraph(s) and {headings} heading(s) in {sections} document(s), {images} image(s) carried across. Every character of the layer is in the book; what is joined, split or headed is decided from the typesetter's geometry with named thresholds",
    "pdf.no-text-layer": "the PDF has no text layer to read ({characters} character(s) over {pages} page(s)); reading it would mean OCR, which this program does not do. Nothing was written",
    "pdf.contents-page-read": "the PDF has no bookmarks, so the {count} entr(y/ies) of the table of contents it prints were read instead, each pointing at the page it names",
    "pdf.outline-used": "the PDF's own outline gave the documents and the table of contents: {count} entr(y/ies) used word for word, {unresolved} that named no page",
    "pdf.tables-rebuilt": "{count} grid(s) of cells were rebuilt as tables, {cells} cell(s) in all; read line by line each cell was a paragraph of a word or two",
    "pdf.lists-rebuilt": "{count} run(s) of paragraphs opening with a marker were marked up as lists; the markers the source drew are kept in the text, so the list sets none of its own",
    "pdf.drawing-not-carried": "{pages} page(s) carry a drawing made of vector strokes; this reader carries pictures and cannot draw, so the drawings are not in the book — the text printed on them is, gathered where it stood ({labelled} place(s))",
    "pdf.image-skipped": "{count} image(s) in the PDF use an encoding this program cannot turn into a file without inventing pixels; they are not in the book, and this line is where it says so",
    "pdf.reading-quality": "read as text: {paragraphs} paragraph(s), median {median} characters; {torn} of them ({share}%) run into the next one mid-sentence and {fragments} are a word or two — the count a layout of plain paragraphs produces",
    "pdf.reading-quality-poor": "this page was not read the way it was laid out: {torn} of {paragraphs} paragraph(s) — {share}% — end mid-sentence and continue in the next one, and {fragments} are a word or two long (median paragraph {median} characters). A document of columns, labels on artwork and tables reads as a stream of fragments; the text is all there and its order is not",
    "pdf.fixed-layout": "the PDF's pages were kept as pages: {pages} document(s) of {width}×{height} points, every line where the typesetter set it, and the publication declared `pre-paginated` so a reading system scales the page instead of reflowing it",
    "pdf.fixed-layout-cost": "what the fixed layout costs, said because it is a trade: the text cannot reflow and does not follow the reader's own font size, a page must be zoomed on a small screen, the structure this reader worked out is not written as structure ({tables} table(s) and {lists} list(s) are drawn where their cells and items stand), and a word the typesetter broke at a line end stays broken — its two halves stand in two places on the page and joining them would empty one of them. The text is still text — every character, in reading order — so it can be searched, selected and read aloud",
    "pdf.anchor-not-carried": "{count} table-of-contents anchor(s) could not travel when the running head between the two halves of a paragraph was removed: the paragraph they were folded into already carries one, which is two pages beginning inside one paragraph. Those entries still find their document and no longer the place in it",
    "pdf.running-heads-kept-fixed": "{count} running head(s) or page number(s) stay where they were drawn: this book keeps the PDF's pages, and a line taken out of a page laid out in fixed positions leaves a hole where it stood",
    "pdf.columns": "{pages} page(s) look set in two columns; the lines were joined in the order they stand on the page, which may interleave the columns — read the result before trusting it",
    "pdf.running-heads-found": "{count} line(s) repeat at the same height of the page and look like running heads or page numbers; they are marked in the text and asked about, nothing is removed here",
    "pdf.running-heads-kept": "{count} running head(s) or page number(s) from the PDF stay in the text as ordinary paragraphs, as chosen",
    "pdf.language-set": "the PDF declared no language; `{language}` was set on a person's word, proposed from the text ({share} Polish letters per thousand characters)",
    "pdf.language-default": "the PDF declared no language and none was chosen; the settings' default `{language}` stands, as for any book without one",
    "pdf.running-heads-left": "{count} running head(s) in {document} were not removed after all: what would have been left was not the text minus those lines, so the document went back to what it was and the lines stay",
    "pdf.running-heads-removed": "{count} running head(s) or page number(s) from the PDF removed from {documents} document(s), on a person's word or a batch's standing answer, and {rejoined} paragraph(s) they had cut in two joined back; the change ledger carries the entry",
    "pdf.characters-unplaced": "{count} character(s) the PDF draws did not land in any line this reader could place (for example {sample}); the rebuild cannot carry what it could not read, and the text check below will say so rather than pass",
    "pdf.destination-exists": "there is already a file called {name} where this conversion would write. Nothing was written: an existing file is somebody's, and this program does not decide on their behalf that it is not. Choose another folder, or say the file may be replaced",
    "pdf.not-for-the-rebuild": "this is a PDF, and the EPUB rebuild repairs books that are already in that format. Making one out of a PDF is a job of its own, with its own settings and its own report: `epubforge convert-pdf`, or PDF -> EPUB in the window. Nothing was written",
}

#: The same, Polish. Every identifier above has one here; `test_rules` holds
#: the two lists against each other for the whole program.
CATALOGUE_PL: dict[str, str] = {
    'pdf.converted': 'warstwa tekstowa PDF-a została wczytana jako książka: {pages} stron, {lines} wierszy złożonych w {paragraphs} akapitów i {headings} nagłówków w {sections} dokumentach, {images} obrazów przeniesionych. Każdy znak warstwy jest w książce; co jest złączone, podzielone albo nagłówkiem, wynika z geometrii składu przy nazwanych progach',
    'pdf.no-text-layer': 'PDF nie ma warstwy tekstowej do czytania ({characters} znaków na {pages} stron); czytanie go oznaczałoby OCR, którego ten program nie robi. Nic nie zapisano',
    'pdf.contents-page-read': 'PDF nie ma zakładek, więc przeczytano {count} pozycji spisu treści, który sam drukuje; każda wskazuje stronę, którą wymienia',
    'pdf.outline-used': 'własne zakładki PDF-a dały podział na dokumenty i spis treści: {count} pozycji użytych słowo w słowo, {unresolved} bez wskazanej strony',
    'pdf.tables-rebuilt': 'odtworzono {count} tabel z siatki komórek, razem {cells} komórek; czytane wiersz po wierszu każda z nich była akapitem na słowo albo dwa',
    'pdf.lists-rebuilt': 'oznaczono {count} ciągów akapitów zaczynających się od znacznika jako listy; znaczniki narysowane przez źródło zostają w tekście, więc lista nie stawia własnych',
    'pdf.drawing-not-carried': 'na {pages} stronach jest rysunek złożony z krzywych; ten czytnik przenosi obrazy i nie umie rysować, więc rysunków nie ma w książce — jest tekst, który na nich stał, zebrany tam, gdzie stał ({labelled} miejsc)',
    'pdf.image-skipped': '{count} obrazów w PDF-ie ma kodowanie, którego ten program nie zamieni na plik bez wymyślania pikseli; nie ma ich w książce, a ta linia o tym mówi',
    'pdf.reading-quality': 'przeczytane jako tekst: {paragraphs} akapitów, mediana {median} znaków; {torn} z nich ({share}%) urywa się w połowie zdania i biegnie dalej w następnym, a {fragments} ma wyraz albo dwa — tyle, ile daje układ ze zwykłych akapitów',
    'pdf.reading-quality-poor': 'ta strona nie została przeczytana tak, jak jest złożona: {torn} z {paragraphs} akapitów — {share}% — kończy się w połowie zdania i biegnie dalej w następnym, a {fragments} ma wyraz albo dwa (mediana akapitu {median} znaków). Dokument z kolumn, etykiet na rysunkach i tabel czyta się jako ciąg strzępów; cały tekst tu jest, a jego kolejność nie',
    'pdf.fixed-layout': 'strony PDF-a zostały zachowane jako strony: {pages} {pages:dokument|dokumenty|dokumentów} po {width}×{height} punktów, każdy wiersz tam, gdzie postawił go zecer, a publikacja deklaruje `pre-paginated`, więc czytnik skaluje całą stronę, zamiast składać ją na nowo',
    'pdf.fixed-layout-cost': 'ile kosztuje układ stały, powiedziane, bo to wymiana: tekst się nie przelewa i nie słucha wielkości pisma ustawionej przez czytelnika, na małym ekranie stronę trzeba powiększać, struktura, którą czytnik odczytał, nie jest zapisana jako struktura ({tables} {tables:tabela|tabele|tabel} i {lists} {lists:lista|listy|list} są narysowane tam, gdzie stoją ich komórki i punkty), a wyraz przeniesiony przez zecera na koniec wiersza zostaje przecięty — jego dwie połowy stoją w dwóch miejscach strony, a złączenie ich opróżniłoby jedno z nich. Tekst nadal jest tekstem — każdy znak, w kolejności czytania — więc da się go szukać, zaznaczać i czytać na głos',
    'pdf.anchor-not-carried': '{count} {count:kotwica spisu tresci nie mogla|kotwice spisu tresci nie mogly|kotwic spisu tresci nie moglo} przejsc przy usuwaniu zywej paginy stojacej miedzy polowami akapitu: akapit, do ktorego je zlaczono, ma juz wlasna — czyli dwie strony zaczynaja sie w jednym akapicie. Te pozycje trafiaja nadal do swojego dokumentu, ale juz nie w to miejsce',
    'pdf.running-heads-kept-fixed': '{count} {count:wiersz żywej paginy albo numeru strony zostaje|wiersze żywej paginy albo numerów stron zostają|wierszy żywej paginy albo numerów stron zostaje} tam, gdzie {count:był narysowany|były narysowane|było narysowanych}: ta książka zachowuje strony PDF-a, a wiersz wyjęty ze strony o stałym układzie zostawia dziurę w miejscu, w którym stał',
    'pdf.columns': '{pages} stron wygląda na złożone w dwóch kolumnach; wiersze zostały złączone w kolejności, w jakiej stoją na stronie, co może przeplatać kolumny — przeczytaj wynik, zanim mu zaufasz',
    'pdf.running-heads-found': '{count} wierszy powtarza się na tej samej wysokości strony i wygląda na żywą paginę albo numery stron; są oznaczone w tekście i zapytane, tu nic nie jest usuwane',
    'pdf.running-heads-kept': '{count} wierszy żywej paginy albo numerów stron z PDF-a zostaje w tekście jako zwykłe akapity, jak wybrano',
    'pdf.language-set': 'PDF nie deklarował języka; `{language}` ustawiony na słowo człowieka, z propozycji z tekstu ({share} polskich liter na tysiąc znaków)',
    'pdf.language-default': 'PDF nie deklarował języka i żaden nie został wybrany; zostaje domyślny z ustawień `{language}`, jak dla każdej książki bez języka',
    'pdf.running-heads-left': '{count} wierszy żywej paginy w {document} jednak nie usunięto: to, co miało zostać, nie było tekstem bez tych wierszy, więc dokument wrócił do stanu sprzed zmiany, a wiersze zostają',
    'pdf.running-heads-removed': '{count} wierszy żywej paginy albo numerów stron z PDF-a usuniętych z {documents} dokumentów, na słowo człowieka albo stałą odpowiedź partii, a {rejoined} akapitów przez nie przeciętych złączonych z powrotem; wpis jest w bilansie zmian',
    'pdf.characters-unplaced': '{count} {count:znak narysowany|znaki narysowane|znaków narysowanych} w PDF-ie nie {count:trafił|trafiły|trafiło} do żadnego wiersza, który ten czytnik umie ułożyć (np. {sample}); przebudowa nie przeniesie tego, czego nie odczytała, a kontrola tekstu niżej powie to zamiast przepuścić',
    'pdf.destination-exists': 'w miejscu, gdzie miałaby powstać książka, jest już plik {name}. Nic nie zapisano: istniejący plik jest czyjś i program nie rozstrzyga za nikogo, że nie jest. Wskaż inny folder albo pozwól zastąpić plik',
    'pdf.not-for-the-rebuild': 'to jest PDF, a przebudowa EPUB naprawia książki, które już są EPUB-ami. Zrobienie książki z PDF-a to osobne zadanie, z własnymi ustawieniami i własnym raportem: `epubforge convert-pdf`, albo PDF -> EPUB w oknie. Nic nie zapisano',
}


def install() -> None:
    """Add these lines to the program's catalogue.

    Called from the module's `install()` and therefore from the package's
    assembly point, so a report rendered anywhere in this program can name a
    `pdf.*` rule whether or not a PDF was read in this run — a stored report
    is read back long after the run that made it.
    """
    from .. import rules

    rules.CATALOGUE.update(CATALOGUE)
    rules.CATALOGUE_PL.update(CATALOGUE_PL)
