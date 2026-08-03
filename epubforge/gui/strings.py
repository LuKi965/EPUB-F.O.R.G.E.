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

    # --- policy panel ---------------------------------------------------
    "policy.group": "Zasady przebudowy",
    "policy.mode.label": "Gdy zgodność ze standardem kłóci się z wyglądem:",
    "policy.mode.tip": (
        "Decyduje, co ma pierwszeństwo w sytuacjach spornych — na przykład gdy "
        "książka używa hacków CSS pod konkretny czytnik albo zawiera linki do "
        "plików, których nigdy w niej nie było."
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
        "Kasuje zasoby nieużywane przez żaden rozdział, arkusz stylów ani spis "
        "treści — a także śmieci w rodzaju .DS_Store czy Thumbs.db.\n\n"
        "Zmniejsza plik. Wyłącz, jeśli chcesz mieć pewność, że nic nie zniknie."
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
    "policy.group": "Rebuild policy",
    "policy.mode.label": "When conformance and appearance conflict:",
    "policy.mode.tip": (
        "Decides what wins in disputed cases — reader-specific CSS hacks, or links to files "
        "the book never contained."
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
        "Deletes resources no chapter, stylesheet or toc uses, plus junk like .DS_Store. "
        "Turn off if you want certainty that nothing disappears."
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
