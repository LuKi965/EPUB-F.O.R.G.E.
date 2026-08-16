"""What the program says when it asks somebody a question, in both languages.

EF-032. Every question this program puts to a person was written in Polish, as a
literal, in the module that happened to raise it — `hyphens.py` and `pipeline.py`
between them. The report has had a catalogue with both languages since 0.2.4 and
renders from `rule` + `values` at display time; the questions, which are the one
place the program actually *talks* to somebody, had neither. An English user got
the interface in English and then, at the moment of being asked to decide
something irreversible about their book, a paragraph of Polish.

The mechanism is deliberately the smaller of the two available. The report keeps
`rule` and `values` and renders per call, which is right for a report: it is
written once and read in whatever language somebody asks for. A question is
asked, answered and gone, so it is rendered once here, at the moment of asking,
in the language the interface is running in. `set_language` is how that language
gets in — the window calls it at start-up, and the default matches the window's
own default so that nothing changes for the owner.

Keys are dotted and name the situation, not the wording, so that rephrasing a
question is editing this file and touching nothing else.
"""

from __future__ import annotations

import os

LANGUAGES = ("pl", "en")

#: Where the command line already says which language the interface speaks —
#: `cli.py` reads it for the closing remark. Read here too so that a batch run
#: with nobody at the window still asks in the language that run was configured
#: for, rather than needing a second setting nobody would think to change.
ENV_LANGUAGE = "EPUBFORGE_LANG"


def _initial() -> str:
    """Polish unless the environment says otherwise — the window's default, so
    a build that never calls `set_language` behaves exactly as it did before
    this module existed."""
    named = os.environ.get(ENV_LANGUAGE, "")[:2].lower()
    return named if named in LANGUAGES else "pl"


#: Language of the next question asked.
_ACTIVE = _initial()


def set_language(code: str) -> None:
    """Ask the next question in *code*. Unknown codes leave the setting alone."""
    global _ACTIVE
    if code in LANGUAGES:
        _ACTIVE = code


def language() -> str:
    return _ACTIVE


TEXTS_PL: dict[str, str] = {
    # --- hyphens: a word cut in two by markup somebody chose ----------------
    "hyphen.cut-by-markup.summary": "„{word}” — słowo przecięte znacznikiem <{carrier}>",
    "hyphen.cut-by-markup.detail": (
        "Nie proponuję złączenia: obie połowy siedzą w różnych elementach, "
        "a <{carrier}> niesie własne formatowanie albo znaczenie. Złączenie "
        "przeniosłoby tekst poza element, który ktoś wybrał — to zmiana "
        "struktury, a nie pisowni."
    ),
    "hyphen.cut-by-markup.keep": "Zostaw jak jest",
    "hyphen.cut-by-markup.keep.why": (
        "Słowo zostaje przecięte dokładnie tak, jak w pliku źródłowym"
    ),
    # --- hyphens: one word --------------------------------------------------
    "hyphen.one.summary": "„{word}” — łącznik w środku słowa",
    "hyphen.one.keep": "Zostaw jak jest",
    "hyphen.one.keep.why": (
        "Słowo zostaje z łącznikiem, dokładnie tak jak w pliku źródłowym"
    ),
    "hyphen.one.join": "Złącz w „{joined}”",
    "hyphen.one.join.why": "W tekście będzie „{joined}”",
    "hyphen.one.write": "Wpisz poprawną formę",
    "hyphen.one.write.why": "W tekście będzie to, co wpiszesz",
    # --- hyphens: a whole confidence class at once --------------------------
    "hyphen.group.summary": (
        "{count} słów z łącznikiem — {label}, bez dowodu w tej książce"
    ),
    "hyphen.group.detail": (
        "Ta książka nigdzie nie pisze tych słów bez łącznika, więc nie ma dowodu, "
        "że łącznik jest usterką konwersji, a nie pisownią autora. Wiele z nich "
        "to prawdziwe wyrazy złożone.\n\n{shown}{more}"
    ),
    "hyphen.group.more": " … i jeszcze {count}",
    "hyphen.group.label.likely": "prawdopodobne",
    "hyphen.group.label.uncertain": "niepewne",
    "hyphen.group.keep": "Zostaw wszystkie",
    "hyphen.group.keep.why": "Żadne z tych słów nie zostanie zmienione — tak jak dotąd",
    "hyphen.group.join": "Złącz wszystkie {count}",
    "hyphen.group.join.why": (
        "Każde z tych słów straci łącznik; to zmiana treści i nie da się jej "
        "cofnąć z samego wyniku"
    ),
    # --- the appearance check could not run at all --------------------------
    "render.unverified.summary": (
        "Sprawdzenie wyglądu jest obowiązkowe i nie dało się go wykonać"
    ),
    "render.unverified.detail": (
        "Program rysuje strony przed i po przebudowie i porównuje je, żeby wykryć "
        "stronę, która straciła treść. Na tej maszynie nie ma przeglądarki, którą "
        "mógłby do tego użyć, więc wynik nie został sprawdzony.\n\n"
        "Zainstaluj Chromium albo Chrome'a, albo wskaż własną przeglądarkę zmienną "
        "{variable}, a sprawdzenie wykona się samo. Możesz też świadomie z niego "
        "zrezygnować — teraz, tą odpowiedzią, albo z góry dla całej partii "
        "ustawieniem „przyjmij niesprawdzone”."
    ),
    "render.unverified.keep": "Nie zapisuj",
    "render.unverified.keep.why": (
        "Plik nie powstanie, a ten, który leży pod tą nazwą, zostanie nietknięty. "
        "Nic nie tracisz i możesz wrócić po zainstalowaniu przeglądarki."
    ),
    "render.unverified.publish": "Zapisz mimo to",
    "render.unverified.publish.why": (
        "Plik powstanie, a w raporcie stanie, że wygląd nie został sprawdzony. "
        "Świadoma rezygnacja z weryfikacji."
    ),
    # --- a metadata field that came out of a damaged package ----------------
    "metadata.reconstructed.summary": "„{current}” — {label} odczytany z uszkodzonego pakietu",
    "metadata.reconstructed.detail": (
        "Pakiet tej książki dał się sparsować dopiero po odzysku, więc to pole "
        "jest odczytem parsera, a nie tym, co napisał wydawca. Wyszło: „{current}”."
    ),
    "metadata.reconstructed.keep": "Zostaw „{current}”",
    "metadata.reconstructed.keep.why": "W książce zostanie to, co odczytał parser",
    "metadata.reconstructed.write": "Wpisz poprawną wartość",
    "metadata.reconstructed.write.why": "W książce będzie to, co wpiszesz",
}

TEXTS_EN: dict[str, str] = {
    "hyphen.cut-by-markup.summary": "“{word}” — a word cut in two by a <{carrier}>",
    "hyphen.cut-by-markup.detail": (
        "No join is offered: the two halves sit in different elements, and "
        "<{carrier}> carries formatting or meaning of its own. Joining them would "
        "move text out of an element somebody chose — a change to the structure "
        "rather than to the spelling."
    ),
    "hyphen.cut-by-markup.keep": "Leave it as it is",
    "hyphen.cut-by-markup.keep.why": (
        "The word stays cut exactly as it is in the source file"
    ),
    "hyphen.one.summary": "“{word}” — a hyphen inside a word",
    "hyphen.one.keep": "Leave it as it is",
    "hyphen.one.keep.why": (
        "The word keeps its hyphen, exactly as it is in the source file"
    ),
    "hyphen.one.join": "Join into “{joined}”",
    "hyphen.one.join.why": "The text will read “{joined}”",
    "hyphen.one.write": "Type the correct form",
    "hyphen.one.write.why": "The text will read whatever you type",
    "hyphen.group.summary": (
        "{count} hyphenated words — {label}, with no evidence in this book"
    ),
    "hyphen.group.detail": (
        "This book never spells these words without a hyphen, so there is no "
        "evidence that the hyphen is a conversion fault rather than the author's "
        "spelling. Many of them are real compounds.\n\n{shown}{more}"
    ),
    "hyphen.group.more": " … and {count} more",
    "hyphen.group.label.likely": "likely",
    "hyphen.group.label.uncertain": "uncertain",
    "hyphen.group.keep": "Leave all of them",
    "hyphen.group.keep.why": "None of these words will be changed — as until now",
    "hyphen.group.join": "Join all {count}",
    "hyphen.group.join.why": (
        "Every one of these words loses its hyphen; this changes the text and "
        "cannot be undone from the output alone"
    ),
    "render.unverified.summary": (
        "The appearance check is mandatory and could not be carried out"
    ),
    "render.unverified.detail": (
        "The program draws the pages before and after the rebuild and compares "
        "them, to catch a page that has lost content. This machine has no browser "
        "it can use for that, so the result has not been checked.\n\n"
        "Install Chromium or Chrome, or point at a browser of your own with "
        "{variable}, and the check runs by itself. You may also decline it "
        "knowingly — now, with this answer, or in advance for a whole batch with "
        "the “accept unverified” setting."
    ),
    "render.unverified.keep": "Do not write it",
    "render.unverified.keep.why": (
        "No file is produced, and whatever already sits under that name is left "
        "untouched. You lose nothing and can come back once a browser is installed."
    ),
    "render.unverified.publish": "Write it anyway",
    "render.unverified.publish.why": (
        "The file is produced, and the report will say the appearance was not "
        "checked. A knowing decision to go without the verification."
    ),
    "metadata.reconstructed.summary": "“{current}” — {label} read out of a damaged package",
    "metadata.reconstructed.detail": (
        "This book's package only parsed after recovery, so this field is the "
        "parser's reading rather than what the publisher wrote. It came out as: "
        "“{current}”."
    ),
    "metadata.reconstructed.keep": "Keep “{current}”",
    "metadata.reconstructed.keep.why": "The book keeps what the parser read",
    "metadata.reconstructed.write": "Type the correct value",
    "metadata.reconstructed.write.why": "The book will carry whatever you type",
}

CATALOGUES: dict[str, dict[str, str]] = {"pl": TEXTS_PL, "en": TEXTS_EN}


def say(key: str, **values) -> str:
    """The text for *key* in the active language, filled with *values*.

    Falls back to Polish and then to the key itself rather than raising, for the
    same reason `rules.describe` does: a question in the wrong language is still
    a question somebody can answer, and one that refuses to render leaves a
    person staring at a traceback instead of at their book.
    """
    catalogue = CATALOGUES.get(_ACTIVE, TEXTS_PL)
    text = catalogue.get(key) or TEXTS_PL.get(key, key)
    if not values:
        return text
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


__all__ = [
    "CATALOGUES",
    "ENV_LANGUAGE",
    "LANGUAGES",
    "language",
    "say",
    "set_language",
]
