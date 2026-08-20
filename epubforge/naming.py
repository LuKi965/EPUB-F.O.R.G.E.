"""Class names a person can read: the epubforge dictionary (D-031).

A converter names its classes after itself (`calibre7`, `sgc-1`,
`Hoofdtekst9a`) and the person who opens the file later learns nothing from
any of them. This module is the other half of the owner's decision: a closed
dictionary of **categories**, each with a Polish and an English word, and a
small table of **atoms** for the rules simple enough to carry their meaning
in the name itself.

Two properties the whole design leans on, both negotiated explicitly:

* **The category comes from evidence, never from a guess.** `categorize`
  answers from what the class is actually attached to in this book — the
  tags that carry it — with the properties only breaking ties between block
  shapes. When the evidence is ambiguous the answer is `inne`, never a wrong
  specific category: the owner's acceptance line was that `ef-akapit-20`
  must never turn out to be the book's title.
* **The name's language follows the interface**, because the person opening
  the file in an editor later is the person who built it — the owner's
  argument verbatim: nobody hand-editing in Calibre will read a
  Polish-English dictionary first. Other languages get English.
"""

from __future__ import annotations

import re

#: Category keys are the Polish, diacritic-free words; the table maps a key to
#: its word per interface language. Keys are stable identifiers — reports and
#: tests may rely on them — and the order here is the order the help section
#: documents.
CATEGORY_WORDS: dict[str, dict[str, str]] = {
    "naglowek": {"pl": "naglowek", "en": "heading"},
    "akapit": {"pl": "akapit", "en": "paragraph"},
    "wyroznienie": {"pl": "wyroznienie", "en": "emphasis"},
    "czcionka": {"pl": "czcionka", "en": "font"},
    "wyrownanie": {"pl": "wyrownanie", "en": "align"},
    "lista": {"pl": "lista", "en": "list"},
    "tabela": {"pl": "tabela", "en": "table"},
    "obraz": {"pl": "obraz", "en": "image"},
    "ozdobnik": {"pl": "ozdobnik", "en": "ornament"},
    "podstawa": {"pl": "podstawa", "en": "base"},
    "przypis": {"pl": "przypis", "en": "footnote"},
    "inne": {"pl": "inne", "en": "other"},
}

#: Declarations simple enough to *be* the name. A rule qualifies for a
#: speaking name only when **every** declaration in it appears here and there
#: are at most three (the owner's soup limit) — anything else falls back to
#: category-and-number, which never lies. Values are compared normalised
#: (lower-case, collapsed whitespace).
ATOMS: dict[tuple[str, str], dict[str, str]] = {
    ("text-align", "center"): {"pl": "srodek", "en": "center"},
    ("text-align", "right"): {"pl": "do-prawej", "en": "right"},
    ("text-align", "justify"): {"pl": "justowanie", "en": "justify"},
    ("font-style", "italic"): {"pl": "kursywa", "en": "italic"},
    ("font-weight", "bold"): {"pl": "pogrubienie", "en": "bold"},
    ("font-weight", "700"): {"pl": "pogrubienie", "en": "bold"},
    ("text-transform", "uppercase"): {"pl": "wersaliki", "en": "uppercase"},
    ("font-variant", "small-caps"): {"pl": "kapitaliki", "en": "smallcaps"},
    ("text-decoration", "underline"): {"pl": "podkreslenie", "en": "underline"},
    ("text-decoration", "line-through"): {"pl": "przekreslenie", "en": "strikeout"},
}

#: Role words a generator writes into its own class names (D-033). The owner's
#: observation, seconded by the seventh audit: `sgc-toc-title` is Sigil's own
#: record that it generated a table of contents — the name is the tool's note
#: of purpose, the same class of fact as the cover repair's `REFIT_MARK`, and
#: throwing it away to write `ef-akapit-1` loses information the old name
#: carried. Measured over the shelf's 566 distinct generator names: 96 carry
#: any word at all, and after machine vocabulary (normal, spacing, default,
#: chp, acetate) is set aside these five families are what remains. `list` is
#: deliberately absent — Google's `lst-kix_list_…` are numbering counters and
#: the `lista` category already answers from evidence.
ROLE_WORDS: dict[str, dict[str, str]] = {
    "toc": {"pl": "spis-tresci", "en": "contents"},
    "hyperlink": {"pl": "odnosnik", "en": "hyperlink"},
    "table": {"pl": "tabela", "en": "table"},
    "header": {"pl": "naglowek-strony", "en": "page-header"},
    "footer": {"pl": "stopka", "en": "footer"},
}

#: Words inside a generator's class name: hyphen/underscore pieces, camelCase
#: halves (`MsoHyperlink` → `Mso`, `Hyperlink`), digits their own token.
_NAME_TOKENS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")

#: A fixed composition order for speaking names, so the same combination is
#: always the same name — layout first, then face, then decoration.
_ATOM_ORDER = [
    "srodek", "do-prawej", "justowanie",
    "kursywa", "pogrubienie", "kapitaliki", "wersaliki",
    "podkreslenie", "przekreslenie",
]
_ATOM_RANK = {word: rank for rank, word in enumerate(_ATOM_ORDER)}

#: The tag families `categorize` reasons from. Deliberately coarse: a family
#: answers "what kind of thing carries this class", not "what does it do".
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_INLINE = {"span", "i", "b", "em", "strong", "small", "sub", "sup", "a", "code"}
_BLOCKS = {"p", "div", "blockquote", "section"}
_LISTS = {"li", "ul", "ol", "dt", "dd", "dl"}
_TABLES = {"td", "th", "tr", "table", "tbody", "thead", "tfoot", "caption", "col", "colgroup"}
_IMAGES = {"img", "figure", "figcaption", "svg"}
_FACE_PROPERTIES = {
    "font-family", "font-size", "font-weight", "font-style", "font-variant",
    "text-transform", "letter-spacing", "color",
}


def language_of(code: str) -> str:
    """The dictionary's language for an interface code: `pl` stays Polish,
    everything else — including codes this program may speak one day — gets
    English, per the owner's rule."""
    return "pl" if code == "pl" else "en"


def word(category: str, language: str) -> str:
    return CATEGORY_WORDS[category][language_of(language)]


def categorize(
    tags: "set[str]",
    properties: "set[str]",
    declarations: "list[tuple[str, str]] | None" = None,
) -> str:
    """The category a class belongs to, from what carries it in this book.

    Every branch is a subset test on purpose: a class seen on a heading *and*
    on a body paragraph proves neither and lands in `inne`. The one softening
    is `span` beside headings — converters wrap heading fragments in spans,
    and the heading is still what the class is about.

    The `akapit` branch carries one extra guard, from the seventh audit's
    measurement: converters compose titles out of `<div>` and `<p>`, so a
    class whose declarations *style like a heading* — bold, uppercase, or a
    font a third larger — may well be a title the tag family cannot see.
    Fourteen such classes on the owner's shelf were being named `ef-akapit-*`
    while titling things; `akapit` there is a lie and `inne` is not, which is
    the same acceptance line the whole function was built on. The guard needs
    declaration *values*, so it only fires when the caller passes them.
    """
    if not tags:
        return "inne"
    if tags <= _HEADINGS or (tags & _HEADINGS and tags <= _HEADINGS | {"span"}):
        return "naglowek"
    if tags <= _LISTS:
        return "lista"
    if tags <= _TABLES:
        return "tabela"
    if tags <= _IMAGES:
        return "obraz"
    if tags <= {"hr"}:
        return "ozdobnik"
    if tags <= {"body", "html"}:
        return "podstawa"
    if tags <= _INLINE:
        return "wyroznienie"
    if tags <= _BLOCKS | _INLINE:
        if properties and properties <= {"text-align"}:
            return "wyrownanie"
        if properties and properties <= _FACE_PROPERTIES:
            return "czcionka"
        if declarations and _heading_styled(declarations):
            return "inne"
        return "akapit"
    return "inne"


def _heading_styled(declarations: "list[tuple[str, str]]") -> bool:
    """Whether these declarations dress a block the way a heading dresses.

    The audit's three signals, verbatim: `font-weight` bold (or 600 and up),
    `text-transform: uppercase`, or a `font-size` of 1.3em or more — em, rem,
    percent, or the large keywords. Absolute units are deliberately not
    judged: 14pt is a heading in one book and body text in another, and a
    guard that guesses is the thing this dictionary exists to avoid.
    """
    for prop, value in declarations:
        name = prop.strip().lower()
        text = " ".join(value.split()).lower()
        if name == "font-weight" and text in {"bold", "bolder", "600", "700", "800", "900"}:
            return True
        if name == "text-transform" and text == "uppercase":
            return True
        if name == "font-size":
            if text in {"large", "x-large", "xx-large", "xxx-large"}:
                return True
            measured = re.match(r"([0-9.]+)\s*(em|rem|%)$", text)
            if measured:
                size = float(measured.group(1))
                if measured.group(2) == "%":
                    size /= 100.0
                if size >= 1.3:
                    return True
    return False


def role_name(class_name: str, tags: "set[str]", language: str) -> "str | None":
    """The name a generator's own role word earns, or `None` (D-033).

    `sgc-toc-title` → `ef-spis-tresci`; `sgc-toc-level-2` → `ef-spis-tresci-2`,
    where the digit is the **source name's own level**, carried over because
    the generator recorded it — it is not this program's first-use counter,
    and the report's map is where that difference is visible. The one
    contradiction that is cheap and certain closes the door: a class carried
    only by images is not a table of contents whatever its name says, and a
    role that cannot be true falls back to evidence.
    """
    if tags and tags <= _IMAGES:
        return None
    tokens = [token.lower() for token in _NAME_TOKENS.findall(class_name)]
    role = next((token for token in tokens if token in ROLE_WORDS), None)
    if role is None:
        return None
    stem = "ef-" + ROLE_WORDS[role][language_of(language)]
    if role == "toc" and tokens and tokens[-1].isdigit():
        return f"{stem}-{int(tokens[-1])}"
    return stem


def speaking_name(declarations: "list[tuple[str, str]]", language: str) -> "str | None":
    """A name that *is* the rule, or `None` when honesty needs a number.

    Only when every declaration is an atom and there are one to three of
    them — the owner's limit, so a speaking name can never become the soup
    it was meant to replace. Composition order is fixed (`_ATOM_ORDER`), so
    the same combination is the same name in every book, forever.
    """
    if not 1 <= len(declarations) <= 3:
        return None
    keys = []
    for prop, value in declarations:
        atom = ATOMS.get((prop.strip().lower(), " ".join(value.split()).lower()))
        if atom is None:
            return None
        keys.append(atom["pl"])  # rank by the stable Polish key
    keys = sorted(set(keys), key=_ATOM_RANK.__getitem__)
    lang = language_of(language)
    return "ef-" + "-".join(_translated_atom(key, lang) for key in keys)


def _translated_atom(pl_key: str, language: str) -> str:
    for atom in ATOMS.values():
        if atom["pl"] == pl_key:
            return atom[language]
    raise KeyError(pl_key)


__all__ = [
    "ATOMS",
    "CATEGORY_WORDS",
    "ROLE_WORDS",
    "categorize",
    "language_of",
    "role_name",
    "speaking_name",
    "word",
]
