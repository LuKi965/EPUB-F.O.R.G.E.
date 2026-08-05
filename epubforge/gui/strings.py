"""Interface text.

Polish is the default because that is what this tool is used in; English is
kept alongside so the strings stay reviewable by non-Polish speakers and the
app can be switched with EPUBFORGE_LANG=en.

Tooltips deliberately explain *consequences* rather than restating the label —
someone deciding whether to tick a box needs to know what it will do to their
book, not what the box is called.
"""

from __future__ import annotations

import os

PL: dict[str, str] = {
    # --- window and toolbar ---------------------------------------------
    "window.title": "EPUB F.O.R.G.E. {version}",
    "toolbar.add": "Dodaj książki…",
    "toolbar.add.tip": (
        "Wybierz pliki EPUB do przebudowy.\n\n"
        "Możesz też po prostu przeciągnąć je w dowolne miejsce tego okna."
    ),
    "toolbar.clear": "Wyczyść listę",
    "toolbar.clear.tip": "Usuwa wszystkie pozycje z listy. Nie kasuje żadnych plików z dysku.",
    "toolbar.output": "Folder wyjściowy:",
    "toolbar.output.placeholder": "puste — zapisz obok pliku źródłowego jako *.forged.epub",
    "toolbar.output.tip": (
        "Gdzie zapisać przebudowane książki.\n\n"
        "Gdy pole jest puste, każdy plik trafia obok oryginału z końcówką "
        "„.forged.epub”. Oryginał nigdy nie jest nadpisywany."
    ),
    "toolbar.browse": "Przeglądaj…",
    "toolbar.browse.tip": "Wskaż folder, w którym mają wylądować gotowe pliki.",

    # --- table ----------------------------------------------------------
    "table.book": "Książka",
    "table.status": "Stan",
    "table.fixed": "Naprawiono",
    "table.fixed.tip": "Liczba usterek, które narzędzie poprawiło.",
    "table.kept": "Zachowano",
    "table.kept.tip": (
        "Liczba odstępstw od standardu zostawionych świadomie, bo ich usunięcie "
        "zmieniłoby wygląd książki. Szczegóły w raporcie poniżej."
    ),
    "table.issues": "Uwagi",
    "table.issues.tip": "Ostrzeżenia i błędy, których nie dało się naprawić automatycznie.",

    "status.queued": "w kolejce",
    "status.working": "przetwarzanie",
    "status.done": "gotowe",
    "status.issues": "gotowe z uwagami",
    "status.failed": "niepowodzenie",
    "status.blocked": "odmowa",

    # --- policy panel ---------------------------------------------------
    "policy.group": "Zasady przebudowy",
    "policy.mode.label": "Gdy zgodność ze standardem kłóci się z wyglądem:",
    "policy.mode.tip": (
        "Każdy tryb buduje książkę od nowa: pakiet, nawigację, nazwy plików i "
        "strukturę ZIP. Tak działa to narzędzie — nie łata pliku, tylko wczytuje "
        "książkę i składa nowy, poprawny kontener.\n\n"
        "Ten wybór dotyczy wyłącznie tego, co zrobić z *treścią* w sytuacjach "
        "spornych — na przykład gdy książka używa hacków CSS pod konkretny czytnik "
        "albo zawiera linki do plików, których nigdy w niej nie było."
    ),
    "policy.mode.preserve": "Zachowaj wygląd, zgłoś odstępstwa",
    "policy.mode.strict": "Wymuś standard, nawet kosztem wyglądu",
    "policy.mode.minimal": "Przebuduj tylko kontener, nie ruszaj treści",
    "policy.mode.preserve.tip": (
        "Tryb domyślny i zalecany.\n\n"
        "Książka wygląda dokładnie tak jak przedtem. Jawne błędy wydawcy są "
        "naprawiane, ale rzeczy, które tylko odbiegają od standardu, a działają "
        "— zostają, z adnotacją w raporcie."
    ),
    "policy.mode.strict.tip": (
        "Pełna zgodność z EPUB 3.3, nawet jeśli coś się przez to przesunie.\n\n"
        "Martwe odnośniki tracą href (tekst zostaje), znikają bloki CSS pisane "
        "pod Kindle i właściwości specyficzne dla Adobe. Wynik przechodzi "
        "EPUBCheck bez zastrzeżeń."
    ),
    "policy.mode.minimal.tip": (
        "Regeneruje wyłącznie OPF, nawigację i strukturę ZIP.\n\n"
        "Pliki XHTML i CSS przechodzą bajt w bajt. Użyj, gdy chcesz naprawić "
        "opakowanie, ale absolutnie nie tykać zawartości."
    ),

    "policy.ncx": "Dołącz zapasowy NCX dla starszych czytników",
    "policy.ncx.tip": (
        "Dokłada stary spis treści w formacie EPUB 2 obok nowego.\n\n"
        "Kosztuje kilka kilobajtów, ale sprawia, że spis treści działa również "
        "na leciwych czytnikach. Zalecane."
    ),
    "policy.orphans": "Usuń pliki, do których nic nie prowadzi",
    "policy.orphans.tip": (
        "Domyślnie WYŁĄCZONE i lepiej tak zostawić.\n\n"
        "Kasuje zasoby, których nie widzi żaden rozdział, arkusz stylów ani spis "
        "treści. Problem w tym, że narzędzie jeszcze nie widzi wszystkich "
        "odwołań: nie zna „srcset”, elementu <picture> ani odsyłaczy zrobionych "
        "wewnątrz pliku SVG. Plik używany przez którekolwiek z nich wygląda tu "
        "jak nieużywany — i zostałby skasowany.\n\n"
        "Zysk to kilka kilobajtów. Ryzyko to dziura w miejscu obrazka."
    ),
    "policy.layout": "Uporządkuj pliki w folderach wg typu",
    "policy.layout.tip": (
        "Przenosi treść do EPUB/text, style do EPUB/styles, obrazy do "
        "EPUB/images i tak dalej, a nazwy sprowadza do bezpiecznego ASCII.\n\n"
        "Wszystkie odnośniki są przepisywane. Niektóre czytniki potrafią się "
        "wyłożyć na polskich znakach w nazwach plików."
    ),
    "policy.scripts": "Usuń skrypty JavaScript",
    "policy.scripts.tip": (
        "Wycina elementy <script> i atrybuty zdarzeń.\n\n"
        "Domyślnie wyłączone: część książek o stałym układzie używa skryptów do "
        "poprawnego wyświetlania i bez nich się rozjedzie."
    ),
    "policy.validate": "Sprawdź wynik programem EPUBCheck",
    "policy.validate.tip": (
        "Uruchamia oficjalny walidator W3C na gotowym pliku i dopisuje jego "
        "werdykt do raportu.\n\n"
        "Wydłuża przetwarzanie o kilka sekund na książkę."
    ),
    "policy.validate.missing": (
        "EPUBCheck nie został znaleziony.\n\n"
        "W wersji instalowanej jest dołączony. Przy uruchamianiu ze źródeł "
        "wskaż plik epubcheck.jar zmienną EPUBCHECK_JAR."
    ),

    # --- tabs and shared ------------------------------------------------
    "tab.rebuild": "Przebudowa",
    "tab.library": "Biblioteka",
    "tab.corpus": "Korpus",
    "common.folder": "Folder:",
    "common.browse": "Przeglądaj…",
    "common.run": "Uruchom",
    "common.stop": "Przerwij",
    "common.save": "Zapisz wynik…",
    "common.saved": "Zapisano: {path}",
    "common.pickfolder": "Wybierz folder",
    "common.nofolder": "Najpierw wskaż folder z książkami.",
    "common.working": "Pracuję: {name}",
    "common.done": "Gotowe — {count} książek",

    # --- library tab ----------------------------------------------------
    "library.intro": (
        "Dwa różne pytania o całą bibliotekę naraz. Nic nie jest zapisywane obok "
        "Twoich książek i nic ich nie zmienia."
    ),
    "library.mode": "Co policzyć:",
    "library.survey": "Przegląd — co narzędzie naprawia i jak często",
    "library.survey.tip": (
        "Przepuszcza każdą książkę przez pełne przetwarzanie i zlicza znaleziska.\n\n"
        "Odpowiada na pytanie „co się psuje najczęściej”, a nie „co jest w tej jednej "
        "książce”. Reguła napisana z jednego pliku jest zgadywaniem; ta sama usterka "
        "w czterdziestu plikach jest faktem.\n\n"
        "Wynik nie jest nigdzie zapisywany poza plikiem, który sam wskażesz."
    ),
    "library.inventory": "Inwentarz — czym te książki są",
    "library.inventory.tip": (
        "Mierzy pochodzenie (ślady Calibre, InDesigna, Worda, konwersji z PDF-u), "
        "uszkodzenia (eksplozja klas, zupa spanów, martwy CSS) i typografię "
        "(cudzysłowy, pauzy, wielokropki, mojibake).\n\n"
        "Przegląd potrafi wymienić tylko te usterki, które narzędzie już umie nazwać — "
        "więc sam siebie nie zaskoczy. Inwentarz mówi, czego jeszcze nie widzi."
    ),
    "library.withnames": "Dołącz nazwy plików do wyniku",
    "library.withnames.tip": (
        "Domyślnie wyłączone. Wynik ma się dać komuś pokazać, a lista tytułów mówi "
        "więcej o Twojej półce niż o narzędziu.\n\n"
        "Włącz, jeśli chcesz móc odnaleźć konkretną książkę stojącą za liczbą."
    ),
    "library.empty": "Wskaż folder z ebookami i naciśnij „Uruchom”.",

    # --- corpus tab -----------------------------------------------------
    "corpus.intro": (
        "Sieć bezpieczeństwa dla tego programu, nie dla Twoich plików.\n\n"
        "Dla każdej książki zapisuje, co przebudowa z niej zrobiła — same liczby "
        "i skrót wyniku. Gdy jutro zmienię w narzędziu regułę, a ta zmiana zepsuje "
        "którąkolwiek z Twoich książek, ten test to zauważy — mimo że tych książek "
        "nigdy nie widziałem i nie zobaczę. „Inny wynik” znaczy więc: przebudowana "
        "inaczej niż ostatnim razem. Twój plik na dysku pozostaje nietknięty."
    ),
    "corpus.books": "Książki:",
    "corpus.signatures": "Podpisy:",
    "corpus.signatures.placeholder": "puste — folder „expected” obok książek",
    "corpus.check": "Sprawdź",
    "corpus.check.tip": (
        "Porównuje każdą książkę z zapisanym podpisem i wypisuje, co się różni.\n\n"
        "Nic nie nadpisuje."
    ),
    "corpus.record": "Nagraj podpisy",
    "corpus.record.tip": (
        "Zapisuje podpisy z tego przebiegu jako nowy punkt odniesienia — i najpierw "
        "pokazuje, co się zmieniło.\n\n"
        "Rób to wtedy, gdy zmiana w narzędziu była zamierzona."
    ),
    "corpus.what": (
        "Podpis zawiera: liczbę znalezisk, czy tekst przeżył przebudowę, liczbę bloków, "
        "wynik EPUBCheck i skrót pliku wyjściowego. Ani tytułu, ani autora, ani jednego "
        "zdania treści."
    ),
    "corpus.empty": "Wskaż folder z książkami i naciśnij „Sprawdź”.",
    "corpus.status.unchanged": "bez zmian",
    "corpus.status.changed": "inny wynik",
    "corpus.status.new": "nowa",
    "corpus.status.failed": "błąd",

    # --- reader compatibility -------------------------------------------
    "compat.group": "Zgodność z czytnikami (opcjonalne)",
    "compat.hint": "Ustępstwa na rzecz konkretnych urządzeń:",
    "compat.hint.tip": (
        "Domyślnie żadne z nich nie jest włączone, bo wynikiem tego narzędzia jest "
        "książka zgodna ze standardem, a każde z tych ustępstw jest krokiem w bok.\n\n"
        "Wszystkie są wyłącznie dokładające: dopisują plik, deklarację albo stary "
        "element. Żadne nic nie usuwa ani nie przepisuje tego, co już w książce było, "
        "i żadne nie zmienia wyglądu na czytniku trzymającym się standardu."
    ),
    "compat.kindle": "Kindle (Amazon)",
    "compat.kindle.tip": (
        "Dokłada element <guide>, po którym konwerter Amazona odnajduje okładkę i "
        "miejsce rozpoczęcia lektury, arkusz deklarujący elementy HTML5 jako blokowe "
        "oraz starą pisownię właściwości łamania stron obok nowej.\n\n"
        "Jeśli okładka jest zawinięta w SVG, dostaniesz uwagę w raporcie: Kindle radzi "
        "sobie z tym słabo, ale rozwinięcie tego zmieniłoby układ na każdym innym "
        "czytniku, więc narzędzie tego nie rusza."
    ),
    "compat.kobo": "Kobo",
    "compat.kobo.tip": (
        "Pilnuje obecności NCX, dokłada <guide> i arkusz z blokowymi elementami HTML5.\n\n"
        "Dotyczy sytuacji, w której Kobo czyta EPUB-a wprost, a nie przekonwertowanego "
        "do KEPUB-a. To nie jest lekarstwo na czytnik, który w ogóle odmawia otwarcia "
        "pliku — taka usterka leży gdzie indziej."
    ),
    "compat.apple": "Apple Books",
    "compat.apple.tip": (
        "Dokłada plik META-INF/com.apple.ibooks.display-options.xml.\n\n"
        "Bez niego Apple Books ignoruje wszystkie osadzone kroje pisma i podstawia "
        "własny. Plik powstaje tylko wtedy, gdy książka faktycznie zawiera czcionki — "
        "w przeciwnym razie deklarowałby coś, czego nie ma."
    ),
    "compat.legacy": "Starsze czytniki (Adobe RMSDK)",
    "compat.legacy.tip": (
        "PocketBook, Nook, Sony, starsze Kobo i Onyx. Wszystkie powyższe ustępstwa "
        "naraz: NCX, <guide>, blokowe elementy HTML5 i stara pisownia łamania stron.\n\n"
        "Te czytniki renderują nieznany element jako liniowy, przez co książka "
        "zbudowana z <section> zlewa się w jeden ciągły akapit."
    ),
    "compat.note": (
        "Element <guide> nie należy już do EPUB 3.3 — EPUBCheck wciąż go akceptuje, "
        "więc plik pozostaje poprawny, ale niesie coś, co standard porzucił."
    ),

    # --- metadata overrides ---------------------------------------------
    "meta.group": "Nadpisanie metadanych (opcjonalne)",
    "meta.placeholder": "zostaw puste — użyj tego, co jest w książce",
    "meta.title": "Tytuł",
    "meta.title.tip": "Zastępuje dc:title we wszystkich przetwarzanych książkach.",
    "meta.author": "Autor",
    "meta.author.tip": (
        "Zastępuje głównego autora. Nazwisko do sortowania („Kowalski, Jan”) "
        "zostanie wyliczone automatycznie."
    ),
    "meta.language": "Język (BCP 47)",
    "meta.language.tip": (
        "Kod języka, np. „pl” albo „pl-PL”.\n\n"
        "Używany też wtedy, gdy książka w ogóle nie deklaruje języka lub "
        "deklaruje go błędnie."
    ),

    # --- actions --------------------------------------------------------
    "action.run": "Przebuduj",
    "action.run.tip": "Uruchamia przebudowę wszystkich książek z listy.",
    "action.save": "Zapisz raport…",
    "action.save.tip": "Zapisuje raport zaznaczonej książki jako plik JSON.",
    "menu.file": "&Plik",
    "menu.quit": "Zakończ",

    # --- report ---------------------------------------------------------
    "report.placeholder": "Zaznacz książkę na liście, aby zobaczyć, co zostało w niej zmienione.",
    "report.source": "źródło",
    "report.output": "wynik",
    "report.notwritten": "NIE ZAPISANO",

    "level.fix": "naprawiono",
    "level.preserved": "zachowano",
    "level.warn": "ostrzeżenie",
    "level.error": "błąd",
    "level.info": "informacja",

    # --- status bar and dialogs -----------------------------------------
    "status.hint": "Przeciągnij pliki EPUB w dowolne miejsce tego okna.",
    "status.hint.nocheck": "EPUBCheck niedostępny — weryfikacja wyłączona.",
    "status.queued.count": "W kolejce: {count}",
    "status.working": "Przebudowuję {name}…",
    "status.validating": "Sprawdzam {name} programem EPUBCheck…",
    "status.finished": "Zakończono {count} książek — wszystkie zapisane.",
    "status.finished.failures": "Zakończono {count} książek — {failures} nie udało się zapisać.",
    "dialog.nothing.title": "Nie ma czego przebudowywać",
    "dialog.nothing.body": "Najpierw dodaj przynajmniej jeden plik EPUB.",
    "dialog.overwrite.title": "Wynik nadpisałby oryginał",
    "dialog.overwrite.body": (
        "Wybierz inny folder wyjściowy — plik {name} zostałby nadpisany w miejscu."
    ),
    "dialog.noreport.title": "Brak raportu",
    "dialog.noreport.body": "Najpierw przebuduj książkę, a potem zaznacz ją na liście.",
    "dialog.filter": "Pliki EPUB (*.epub)",
    "dialog.selectfiles": "Wybierz pliki EPUB",
    "dialog.selectfolder": "Wybierz folder wyjściowy",
    "dialog.savereport": "Zapisz raport",

    # --- settings and about ---------------------------------------------
    "menu.settings": "&Ustawienia",
    "menu.language": "Język interfejsu",
    "menu.help": "&Pomoc",
    "menu.about": "O programie",
    "language.pl": "Polski",
    "language.en": "English",
    "about.title": "O programie EPUB F.O.R.G.E.",
    "about.subtitle": "Fabryka Odbudowy i Renowacji Glitchujących EPUB-ów",
    "about.tagline": "Przekuwa wadliwe ebooki w czysty EPUB 3.3 — bez psucia tego, jak wyglądają.",
    "about.version": "Wersja {version}",
    "about.authors": "Autorzy",
    "about.author.human": "Łukasz „LuKi” Kniotek — pomysł, kierunek i wymagania",
    "about.author.ai": "Claude (Anthropic) — projekt i implementacja",
    "about.license": "Licencja",
    "about.license.body": "MIT. Kod źródłowy dostępny na GitHubie.",
    "about.components": "Dołączone komponenty",
    "about.components.body": (
        "EPUBCheck (W3C) — licencja BSD 3-Clause\n"
        "Środowisko OpenJDK zbudowane jlinkiem — GPLv2 z wyjątkiem Classpath\n"
        "Qt przez PySide6 — LGPLv3, biblioteki dołączone jako wymienialne pliki"
    ),
    "about.close": "Zamknij",
}

EN: dict[str, str] = {
    "window.title": "EPUB F.O.R.G.E. {version}",
    "toolbar.add": "Add books…",
    "toolbar.add.tip": "Pick EPUB files to rebuild.\n\nYou can also drop them anywhere in this window.",
    "toolbar.clear": "Clear list",
    "toolbar.clear.tip": "Empties the list. No files are deleted from disk.",
    "toolbar.output": "Output folder:",
    "toolbar.output.placeholder": "empty — write next to the source as *.forged.epub",
    "toolbar.output.tip": (
        "Where rebuilt books are written.\n\nLeft empty, each file is written beside its "
        "original with a .forged.epub suffix. The source is never overwritten."
    ),
    "toolbar.browse": "Browse…",
    "toolbar.browse.tip": "Choose the folder for the finished files.",
    "table.book": "Book",
    "table.status": "Status",
    "table.fixed": "Fixed",
    "table.fixed.tip": "Defects the tool corrected.",
    "table.kept": "Kept",
    "table.kept.tip": (
        "Deviations left in place on purpose, because removing them would change how the "
        "book looks. See the report below."
    ),
    "table.issues": "Issues",
    "table.issues.tip": "Warnings and errors that could not be fixed automatically.",
    "status.queued": "queued",
    "status.working": "working",
    "status.done": "done",
    "status.issues": "done with issues",
    "status.failed": "failed",
    "status.blocked": "refused",
    "policy.group": "Rebuild policy",
    "policy.mode.label": "When conformance and appearance conflict:",
    "policy.mode.tip": (
        "Every mode builds the book anew: package, navigation, filenames, ZIP "
        "layout. That is how this tool works — it does not patch a file, it reads "
        "the book and assembles a correct container.\n\n"
        "This choice is only about what to do with the *content* in disputed "
        "cases — reader-specific CSS hacks, or links to files the book never "
        "contained."
    ),
    "policy.mode.preserve": "Preserve appearance, report deviations",
    "policy.mode.strict": "Enforce the standard, even if rendering changes",
    "policy.mode.minimal": "Rebuild the container only, leave content alone",
    "policy.mode.preserve.tip": (
        "The default. The book looks exactly as before. Clear publisher errors are repaired, "
        "but things that merely deviate from the spec while working are kept and reported."
    ),
    "policy.mode.strict.tip": (
        "Full EPUB 3.3 conformance even if something shifts. Dead links lose their href, "
        "Kindle-only CSS and Adobe properties are removed. Passes EPUBCheck cleanly."
    ),
    "policy.mode.minimal.tip": (
        "Regenerates only the OPF, navigation and ZIP structure. XHTML and CSS pass through "
        "byte for byte."
    ),
    "policy.ncx": "Include a legacy NCX for older readers",
    "policy.ncx.tip": (
        "Adds the EPUB 2 table of contents alongside the new one. Costs a few kilobytes and "
        "makes the toc work on old devices. Recommended."
    ),
    "policy.orphans": "Remove files nothing references",
    "policy.orphans.tip": (
        "OFF by default, and best left that way.\n\n"
        "Deletes resources no chapter, stylesheet or table of contents points at. "
        "The catch is that the tool cannot yet see every reference: it does not "
        "follow srcset, <picture>, or links made from inside an SVG. A file used "
        "by any of those looks unused here and would be deleted.\n\n"
        "The saving is a few kilobytes. The risk is a hole where a picture was."
    ),
    "policy.layout": "Reorganise files into typed folders",
    "policy.layout.tip": (
        "Moves content to EPUB/text, styles to EPUB/styles and so on, folding names to safe "
        "ASCII. Every reference is rewritten. Some readers choke on non-ASCII filenames."
    ),
    "policy.scripts": "Remove JavaScript",
    "policy.scripts.tip": (
        "Strips <script> elements and event attributes. Off by default: some fixed-layout "
        "books need scripting to render correctly."
    ),
    "policy.validate": "Verify the result with EPUBCheck",
    "policy.validate.tip": (
        "Runs the official W3C validator on the finished file and adds its verdict to the "
        "report. Adds a few seconds per book."
    ),
    "policy.validate.missing": (
        "EPUBCheck was not found.\n\nThe installed build bundles it. Running from source, "
        "point EPUBCHECK_JAR at epubcheck.jar."
    ),
    "tab.rebuild": "Rebuild",
    "tab.library": "Library",
    "tab.corpus": "Corpus",
    "common.folder": "Folder:",
    "common.browse": "Browse…",
    "common.run": "Run",
    "common.stop": "Stop",
    "common.save": "Save result…",
    "common.saved": "Saved: {path}",
    "common.pickfolder": "Choose a folder",
    "common.nofolder": "Point at a folder of books first.",
    "common.working": "Working: {name}",
    "common.done": "Done — {count} book(s)",

    "library.intro": (
        "Two different questions about a whole library. Nothing is written beside your "
        "books and nothing changes them."
    ),
    "library.mode": "What to measure:",
    "library.survey": "Survey — what the tool repairs, and how often",
    "library.survey.tip": (
        "Runs every book through the full pipeline and counts the findings.\n\n"
        "It answers \"what breaks most often\", not \"what is in this one book\". A rule "
        "written from a single file is a guess; the same defect in forty files is a "
        "fact.\n\nNothing is written anywhere except the file you choose."
    ),
    "library.inventory": "Inventory — what the books are made of",
    "library.inventory.tip": (
        "Measures provenance (traces of Calibre, InDesign, Word, a PDF conversion), "
        "damage (class explosion, span soup, dead CSS) and typography (quotes, dashes, "
        "ellipses, mojibake).\n\n"
        "A survey can only name defects the tool already knows about, so it never "
        "surprises anybody. An inventory says what it cannot yet see."
    ),
    "library.withnames": "Include filenames in the result",
    "library.withnames.tip": (
        "Off by default. The result is meant to be shareable, and a list of titles says "
        "more about your shelf than about the tool.\n\n"
        "Turn on if you need to find the book behind a number."
    ),
    "library.empty": "Point at a folder of e-books and press Run.",

    "corpus.intro": (
        "A safety net for this program, not for your files.\n\n"
        "For each book it records what the rebuild did to it — counts only, plus a "
        "hash of the result. When a rule changes tomorrow and that change breaks one "
        "of your books, this notices — even though nobody ever handed the books over. "
        "\"Different\" therefore means: rebuilt differently than last time. Your file "
        "on disk is untouched."
    ),
    "corpus.books": "Books:",
    "corpus.signatures": "Signatures:",
    "corpus.signatures.placeholder": "empty — an \"expected\" folder beside the books",
    "corpus.check": "Check",
    "corpus.check.tip": "Compares each book with its signature and lists what differs. Overwrites nothing.",
    "corpus.record": "Record signatures",
    "corpus.record.tip": (
        "Writes this run's signatures as the new baseline — showing first what moved.\n\n"
        "Do this when the change in the tool was intended."
    ),
    "corpus.what": (
        "A signature holds: how many findings, whether the text survived, the block "
        "count, the EPUBCheck verdict and a hash of the output. No title, no author, "
        "not a word of the text."
    ),
    "corpus.empty": "Point at a folder of books and press Check.",
    "corpus.status.unchanged": "unchanged",
    "corpus.status.changed": "different result",
    "corpus.status.new": "new",
    "corpus.status.failed": "failed",

    "compat.group": "Reader compatibility (optional)",
    "compat.hint": "Concessions to particular devices:",
    "compat.hint.tip": (
        "All off by default, because the product of this tool is a standards-clean "
        "book and each of these steps away from it.\n\n"
        "Every one is additive: it adds a file, a declaration or a legacy element. "
        "None removes or rewrites what the book already had, and none changes how a "
        "reader that follows the specification renders it."
    ),
    "compat.kindle": "Kindle (Amazon)",
    "compat.kindle.tip": (
        "Adds the <guide> element Amazon's converter uses to find the cover and the "
        "start-reading position, a stylesheet declaring the HTML5 sectioning elements "
        "as blocks, and the legacy spelling of the page-break properties beside the "
        "modern one.\n\n"
        "If the cover is wrapped in SVG you get a note in the report: Kindle handles "
        "that poorly, but unwrapping it would change the layout on every other reader, "
        "so the tool leaves it alone."
    ),
    "compat.kobo": "Kobo",
    "compat.kobo.tip": (
        "Insists on the NCX, adds <guide> and the HTML5 block stylesheet.\n\n"
        "For Kobo reading the EPUB directly rather than a converted KEPUB. It is not a "
        "cure for a device that refuses to open a file at all — that fault lies "
        "elsewhere."
    ),
    "compat.apple": "Apple Books",
    "compat.apple.tip": (
        "Adds META-INF/com.apple.ibooks.display-options.xml.\n\n"
        "Without it Apple Books ignores every embedded face and substitutes its own. "
        "Written only when the book actually embeds fonts — otherwise it would declare "
        "something that is not there."
    ),
    "compat.legacy": "Older readers (Adobe RMSDK)",
    "compat.legacy.tip": (
        "PocketBook, Nook, Sony, older Kobo and Onyx. Everything above at once: NCX, "
        "<guide>, HTML5 block declarations and the legacy page-break spelling.\n\n"
        "These renderers treat an element they do not know as inline, which collapses "
        "a book built from <section> into one running paragraph."
    ),
    "compat.note": (
        "<guide> is no longer part of EPUB 3.3. EPUBCheck still accepts it, so the file "
        "stays valid, but it carries something the specification dropped."
    ),

    "meta.group": "Metadata overrides (optional)",
    "meta.placeholder": "leave empty — keep what the book has",
    "meta.title": "Title",
    "meta.title.tip": "Replaces dc:title in every book processed.",
    "meta.author": "Author",
    "meta.author.tip": "Replaces the main author. The sort name is derived automatically.",
    "meta.language": "Language (BCP 47)",
    "meta.language.tip": (
        "A tag such as \"pl\" or \"pl-PL\". Also used when the book declares no language, "
        "or an invalid one."
    ),
    "action.run": "Rebuild",
    "action.run.tip": "Rebuilds every book in the list.",
    "action.save": "Save report…",
    "action.save.tip": "Writes the selected book's report as JSON.",
    "menu.file": "&File",
    "menu.quit": "Quit",
    "report.placeholder": "Select a book to see what the rebuild changed.",
    "report.source": "source",
    "report.output": "output",
    "report.notwritten": "NOT WRITTEN",
    "level.fix": "fixed",
    "level.preserved": "kept",
    "level.warn": "warning",
    "level.error": "error",
    "level.info": "info",
    "status.hint": "Drop EPUB files anywhere in this window.",
    "status.hint.nocheck": "EPUBCheck unavailable — validation disabled.",
    "status.queued.count": "Queued: {count}",
    "status.working": "Rebuilding {name}…",
    "status.validating": "Checking {name} with EPUBCheck…",
    "status.finished": "Finished {count} book(s) — all written.",
    "status.finished.failures": "Finished {count} book(s) — {failures} could not be written.",
    "dialog.nothing.title": "Nothing to do",
    "dialog.nothing.body": "Add at least one EPUB file first.",
    "dialog.overwrite.title": "Output would overwrite the source",
    "dialog.overwrite.body": "Choose a different output folder — {name} would be overwritten in place.",
    "dialog.noreport.title": "No report",
    "dialog.noreport.body": "Rebuild a book first, then select it.",
    "dialog.filter": "EPUB files (*.epub)",
    "dialog.selectfiles": "Select EPUB files",
    "dialog.selectfolder": "Select output folder",
    "dialog.savereport": "Save report",

    "menu.settings": "&Settings",
    "menu.language": "Interface language",
    "menu.help": "&Help",
    "menu.about": "About",
    "language.pl": "Polski",
    "language.en": "English",
    "about.title": "About EPUB F.O.R.G.E.",
    "about.subtitle": "Factory for Overhauling and Renovating Glitchy EPUBs",
    "about.tagline": "Forges broken e-books into clean EPUB 3.3 — without spoiling how they look.",
    "about.version": "Version {version}",
    "about.authors": "Authors",
    "about.author.human": "Łukasz \u201cLuKi\u201d Kniotek — concept, direction and requirements",
    "about.author.ai": "Claude (Anthropic) — design and implementation",
    "about.license": "License",
    "about.license.body": "MIT. Source available on GitHub.",
    "about.components": "Bundled components",
    "about.components.body": (
        "EPUBCheck (W3C) — BSD 3-Clause\n"
        "OpenJDK runtime built with jlink — GPLv2 with the Classpath Exception\n"
        "Qt via PySide6 — LGPLv3, shipped as replaceable shared libraries"
    ),
    "about.close": "Close",
}

LANGUAGES = {"pl": PL, "en": EN}


DEFAULT_LANGUAGE = "pl"


def _detect() -> str:
    """Environment override first, then Polish.

    The system locale is deliberately *not* consulted: a machine reporting an
    English locale (a container, an English Windows install) should not decide
    the interface language. The GUI overrides this from stored settings.
    """
    override = os.environ.get("EPUBFORGE_LANG", "").strip().lower()[:2]
    return override if override in LANGUAGES else DEFAULT_LANGUAGE


def language() -> str:
    return _ACTIVE


_ACTIVE = _detect()


def set_language(code: str) -> None:
    global _ACTIVE
    if code in LANGUAGES:
        _ACTIVE = code


def tr(key: str, **kwargs) -> str:
    """Look up *key*, falling back to English and then to the key itself."""
    text = LANGUAGES[_ACTIVE].get(key) or EN.get(key) or key
    return text.format(**kwargs) if kwargs else text
