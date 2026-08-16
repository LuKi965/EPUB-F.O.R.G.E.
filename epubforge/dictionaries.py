"""A spelling dictionary as a *second* source of evidence, never the only one.

WP-10 / EF-028. The hyphen detector had one proof: *does this book itself write
the word without a hyphen somewhere else*. That is strong evidence and it is
absent exactly where it is needed — a word that occurs once. Six real artefacts
in Book 2 were being dropped without a trace for that reason, because the shape
`-o-` reads as a Polish compound and nothing could say otherwise.

A dictionary can say otherwise, and the measurement says how far:

    doboro-wym       'doboro' is not a word,  'doborowym' is    → an artefact
    przeko-naniem    'przeko'  is not a word, 'przekonaniem' is → an artefact
    wspo-minał       'wspo'    is not a word, 'wspominał' is    → an artefact

    czarno-czerwone  both halves are words, and so is the join  → cannot tell
    ciemno-włosej    both halves are words, and so is the join  → cannot tell

The first three are settled without asking anybody: **a compound whose first
half is not a word does not exist**, so the hyphen came from a converter and
not from a writer. The last two are genuinely ambiguous — a correct compound and
a broken word look identical to a dictionary — and the honest answer there is a
question, which is what `UNCERTAIN` is for.

That is the whole claim. The dictionary is not asked *is this a word*, which
would make every rare or inflected form a false positive; it is asked *is the
first half a word*, which is a question about Polish morphology rather than
about this book's vocabulary.

**Absence is not an error.** A build without dictionaries detects exactly as it
did before and says so in the report. A dictionary that fails to load is the
same case: this is evidence, and evidence that did not arrive means a weaker
answer, not a broken rebuild.
"""

from __future__ import annotations

import functools
import os
import pathlib

#: Where a dictionary may be pointed at by hand — a checkout, a distribution
#: that already ships hunspell dictionaries, somebody testing another language.
ENV_DICTIONARIES = "EPUBFORGE_DICTIONARIES"

#: The languages this build carries. Polish because the owner's shelf is Polish;
#: English because the program's interface is bilingual and the second shelf is
#: 67 books in Dutch and English.
LANGUAGES = ("pl_PL", "en_US")


def _search_paths() -> "list[pathlib.Path]":
    """Where a `<language>.dic` / `<language>.aff` pair may live, best first."""
    found: list[pathlib.Path] = []
    named = os.environ.get(ENV_DICTIONARIES)
    if named:
        found.append(pathlib.Path(named))
    from . import resources

    root = resources.bundle_root()
    if root is not None:
        found.append(root / "dictionaries")
    # The checkout, so that this project's own tests and a `pip` install can
    # find dictionaries somebody downloaded once.
    found.append(pathlib.Path(__file__).resolve().parent.parent / "dictionaries")
    return found


@functools.lru_cache(maxsize=4)
def _load(language: str):
    """The dictionary for *language*, or `None`.

    Cached because reading `pl_PL.dic` is five megabytes of parsing and the
    detector asks about a few hundred words per book. Cached on the language
    rather than the path so that two books in one batch share one load.
    """
    try:
        from spylls.hunspell import Dictionary
    except ImportError:
        return None
    for directory in _search_paths():
        stem = directory / language
        if stem.with_suffix(".dic").is_file() and stem.with_suffix(".aff").is_file():
            try:
                return Dictionary.from_files(str(stem))
            except Exception:  # noqa: BLE001 — a broken dictionary is no dictionary
                continue
    return None


def available(language: str = "pl_PL") -> bool:
    """Whether there is a dictionary to ask. Cheap after the first call."""
    return _load(_normalise(language)) is not None


def _normalise(language: str) -> str:
    """`pl`, `pl-PL`, `PL_pl` → `pl_PL`, and anything unknown left alone."""
    tag = (language or "").replace("-", "_").strip()
    if not tag:
        return LANGUAGES[0]
    head = tag.split("_")[0].lower()
    for known in LANGUAGES:
        if known.split("_")[0].lower() == head:
            return known
    return tag


def is_a_word(word: str, language: str = "pl_PL") -> "bool | None":
    """Whether *word* is in the dictionary. `None` when there is none to ask.

    Three-valued on purpose, and the third value is the point: `False` means
    *the dictionary says no*, which is evidence, and `None` means *nobody was
    asked*, which is not. Collapsing them into a boolean would turn a missing
    dictionary into a confident claim that nothing is a word — and that claim
    would mark every hyphenated word in the book as a converter's artefact.
    """
    dictionary = _load(_normalise(language))
    if dictionary is None:
        return None
    if not word:
        return False
    try:
        return bool(dictionary.lookup(word))
    except Exception:  # noqa: BLE001 — a lookup that raises is a lookup nobody made
        return None


def half_is_not_a_word(left: str, joined: str, language: str = "pl_PL") -> bool:
    """The one question worth asking: is this a compound that cannot exist?

    True only when the dictionary is present, the joined form **is** a word and
    the first half is **not**. Both halves of that matter:

    * without the joined form being a word, `wspo-minał` is indistinguishable
      from a typo, and joining a typo invents a word;
    * without the first half failing, `czarno-czerwone` looks exactly the same
      and joining it would destroy a compound the writer chose.

    Everything else answers False, including *no dictionary at all*, which keeps
    the detector's behaviour identical to what it was before this existed.
    """
    tongue = _normalise(language)
    if _load(tongue) is None:
        return False
    if is_a_word(joined, tongue) is not True:
        return False
    return is_a_word(left, tongue) is False


__all__ = [
    "ENV_DICTIONARIES",
    "LANGUAGES",
    "available",
    "half_is_not_a_word",
    "is_a_word",
]
