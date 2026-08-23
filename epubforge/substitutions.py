"""One letter standing for another, all through a book.

Filar D, in the shape the measurement gave it rather than the one the plan
assumed. The plan expected per-word corrections; the shelf says otherwise.

Measured on 25 Polish books, 12 264 words the dictionary does not know:

* 35,8% are capitalised — characters, places, invented things, and a name
  is not a typo;
* 28,4% the book itself uses three times or more — its own vocabulary, and
  a program that "corrected" a name written seventy-two times would be
  vandalising somebody's novel;
* 24,8% appear once with nothing near them — a rare word, and silence is
  the honest answer;
* 11,0% appear once while the book writes a form one edit away, often.

Only the last class is worth anything, and inside it the shape is not what
a spell checker expects. Of its substitutions **79,6% are one letter for
another**, and reading the sample showed almost every one to be the same
letter: `phawda`, `dobhe`, `wphost`, `najbahdziej`, `któhym`, `bahdzo` —
one book where `r` was read as `h`, 35 times.

So the strong evidence is not the word. It is **the pattern**: this book
writes `h` where it means `r`, over and over, and writes the correct form
elsewhere. That is one question with a whole book behind it instead of
thirty-five guesses, and it is why this module counts pairs rather than
words.

**The threshold is measured, not chosen.** Across the shelf the affected
book's dominant pair is 35 of its 39 candidates — ninety per cent. The
next most concentrated book has 16 of 826 — two per cent, and that is
noise, not a pattern. Anything between those is empty, so the line is
drawn where nothing lives: at least ten occurrences *and* at least half
of the book's candidates.
"""

from __future__ import annotations

import collections
import re

from . import dictionaries

#: Letters a Polish word can be made of. The candidate has to be spellable
#: before it is worth asking a dictionary about.
_WORD = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŻŹąćęłńóśżź]+")

#: A word this rare is a candidate; the book's own frequent spelling is what
#: it is compared against. Both numbers are the hyphen work's shape — the
#: book's own usage is the first evidence and the dictionary the second.
RARE = 2
OFTEN = 5

#: How concentrated a pair must be before it is a pattern rather than a
#: coincidence. See the module docstring: the shelf leaves the whole range
#: between 2% and 90% empty, so the line sits in the gap.
LEAST_OCCURRENCES = 10
LEAST_SHARE = 0.5


class Pattern:
    """One letter standing for another, with the words that show it."""

    def __init__(self, wrong: str, right: str):
        self.wrong = wrong
        self.right = right
        #: Misspelling → the book's own spelling, for every word that shows it.
        #: This is the evidence: each entry is a word the book writes wrong and
        #: also, elsewhere and often, writes right.
        self.words: "dict[str, str]" = {}
        #: Every word the established pattern repairs, the evidence included.
        #: Wider than the evidence on purpose — see `spread`.
        self.repairs: "dict[str, str]" = {}

    @property
    def count(self) -> int:
        return len(self.words)

    def __str__(self) -> str:
        return f"{self.wrong} → {self.right} ({self.count}/{len(self.repairs)})"


def _counts(texts: "list[str]") -> "collections.Counter":
    counted: "collections.Counter" = collections.Counter()
    for text in texts:
        counted.update(word for word in _WORD.findall(text) if len(word) > 2)
    return counted


def _neighbours(often: "dict[str, int]") -> "dict[tuple[str, int, str], list]":
    """Every frequent word filed under each of its one-letter holes.

    `prawda` is filed under `(_rawda)`, `(p_awda)`, `(pr_wda)` and so on, so
    asking *what frequent word is one letter away from `phawda`* is a handful
    of dictionary lookups instead of a walk over the book's whole vocabulary.
    On a novel that is fifteen thousand words against one and a half thousand,
    per candidate — the difference between seconds and minutes on a shelf.

    A hole can hold several words — `dobre` and `dobry` share `dobr_` — and all
    of them are kept, sorted, so that which one answers does not depend on the
    order the book happened to introduce them in.
    """
    filed: "dict[tuple[str, int, str], list]" = {}
    for word in sorted(often):
        for index in range(len(word)):
            filed.setdefault((word[:index], index, word[index + 1:]), []).append(word)
    return filed


def find(texts: "list[str]", language: str = "pl_PL") -> "Pattern | None":
    """The one substitution this book makes systematically, or None.

    None is the answer for almost every book, and that is the point: a
    pattern is rare, and inventing one where there is none would put a
    question in front of somebody about their own author's spelling.
    """
    if not dictionaries.available(language):
        return None
    counted = _counts(texts)
    if not counted:
        return None
    often = {word.lower(): number for word, number in counted.items() if number >= OFTEN}
    if not often:
        return None
    neighbours = _neighbours(often)
    known: "dict[str, bool]" = {}

    def is_a_word(word: str) -> bool:
        if word not in known:
            known[word] = bool(dictionaries.is_a_word(word, language))
        return known[word]

    pairs: "dict[tuple[str, str], Pattern]" = {}
    candidates = 0
    for word in sorted(counted):
        if counted[word] > RARE or word[:1].isupper():
            continue
        low = word.lower()
        hit = place = None
        # The cheap half first: a word one letter away from something this book
        # writes often. Only then the dictionary, which is the slow half — and
        # asking it about every rare word in a novel is most of the cost.
        for index, letter in enumerate(low):
            near = [
                other
                for other in neighbours.get((low[:index], index, low[index + 1:]), ())
                if other[index] != letter
            ]
            if not near:
                continue
            # Both dictionary answers matter: the book's usage rules out a
            # coincidence, and the dictionary rules out the book being
            # consistently wrong about a word it invented itself.
            if is_a_word(low) or is_a_word(word):
                break
            hit = next((other for other in near if is_a_word(other)), None)
            if hit is not None:
                place = index
                break
        if hit is None or place is None:
            continue
        candidates += 1
        key = (low[place], hit[place])
        pairs.setdefault(key, Pattern(low[place], hit[place])).words[word] = hit

    if not pairs or not candidates:
        return None
    best = max(pairs.values(), key=lambda pattern: pattern.count)
    if best.count < LEAST_OCCURRENCES or best.count / candidates < LEAST_SHARE:
        return None
    spread(best, counted, is_a_word)
    return best


def rewrite(text: str, repairs: "dict[str, str]") -> str:
    """*text* with each whole word in *repairs* replaced by its repair.

    Whole words by construction: the same expression that found the words is
    what finds them again, so `phawda` inside some longer string that is not a
    word boundary is never touched. It matters that this is one function rather
    than two: the stage applies it to a text node and states its postcondition
    by applying it to the document's whole text, and those two only mean the
    same thing while they are literally the same code.
    """
    if not text or not repairs:
        return text
    return _WORD.sub(lambda found: repairs.get(found.group(0), found.group(0)), text)


def apart_from(pieces, repairs: "dict[str, str]") -> str:
    """The text of *pieces* with the agreed words normalised away.

    How the repair states what it did: run this over a document before the pass
    and after it, and the two are equal exactly when nothing changed except
    words on the agreed list. A sentence that went missing, a word repaired that
    nobody agreed to — either makes them differ.

    *pieces* is one string per text node rather than the document's whole text,
    and that is not a detail: joining first invents words at the seams, so a
    paragraph ending in `bahdzo` followed by one starting with a capital would
    read as a single token that is on nobody's list.
    """
    return "".join(rewrite(piece, repairs) for piece in pieces)


def _cases(word: str, repaired: str) -> str:
    """*repaired* wearing *word*'s capitals. `Phawda` → `Prawda`, not `prawda`."""
    if word.isupper():
        return repaired.upper()
    if word[:1].isupper():
        return repaired[:1].upper() + repaired[1:]
    return repaired


def spread(pattern: Pattern, counted: "collections.Counter", is_a_word) -> None:
    """Every other word the established pattern repairs, filled in.

    The evidence is deliberately narrow — a lower-case word the book writes
    rarely and whose correct form the book itself writes often — and a book
    repaired only there would come out half mended: `Phawda` at the start of a
    sentence is capitalised, so the evidence pass never looks at it, and a word
    the conversion broke *everywhere* is frequent rather than rare.

    Once the pattern is proven, most of that narrowness is not needed any more.
    What each further word still has to show is both halves of the same proof:
    the dictionary does not know the word as written, and does know it with the
    substitution undone. `chuda` is a Polish word and is never touched; most
    names fail the second half — undo the substitution and the result is not a
    word either — so they are never touched.

    **One piece of the narrowness stays, and it was measured rather than
    assumed.** A first draft of this swept every word and offered to rename a
    character: the affected book has a man whose name begins with the wrong
    letter, and undoing the substitution happens to produce another dictionary
    word. What separates him from a real repair is not spelling — it is that
    the book writes his name seventeen times, while every genuine repair on
    that book appears once, twice or three times, and not one of them reaches
    five. A word a book uses that often is the book's own vocabulary, which is
    the same argument the evidence pass makes with `OFTEN`, so the same line is
    drawn here.
    """
    for word in sorted(counted):
        low = word.lower()
        if counted[word] >= OFTEN:
            continue
        if pattern.wrong not in low or is_a_word(low) or is_a_word(word):
            continue
        # Whole-word first, then one place at a time: a word the conversion
        # broke twice — `phawdha` — is repaired by the first, and a word where
        # only one of the letters is wrong by the second.
        forms = [low.replace(pattern.wrong, pattern.right)]
        forms += [
            low[:index] + pattern.right + low[index + 1:]
            for index, letter in enumerate(low)
            if letter == pattern.wrong
        ]
        repaired = next((form for form in forms if is_a_word(form)), None)
        if repaired is not None:
            pattern.repairs[word] = _cases(word, repaired)
