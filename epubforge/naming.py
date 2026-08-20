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


def categorize(tags: "set[str]", properties: "set[str]") -> str:
    """The category a class belongs to, from what carries it in this book.

    Every branch is a subset test on purpose: a class seen on a heading *and*
    on a body paragraph proves neither and lands in `inne`. The one softening
    is `span` beside headings — converters wrap heading fragments in spans,
    and the heading is still what the class is about.
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
        return "akapit"
    return "inne"


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


__all__ = ["ATOMS", "CATEGORY_WORDS", "categorize", "language_of", "speaking_name", "word"]
