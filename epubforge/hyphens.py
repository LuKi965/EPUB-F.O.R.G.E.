"""Hyphens a conversion left inside words, and the evidence for saying so.

BA-2026-001. A PDF or a scan is laid out in lines, and a word broken across two
of them carries a hyphen that belongs to the *typesetting* and not to the word.
Convert that file badly and the hyphen survives into the text: `obo-jętna`,
`doboro-wym`, `po-klepała`. The reader sees them, they are wrong, and no rule
this program had could see them at all.

They cannot be repaired by rule, and that is the whole difficulty. Polish is
full of hyphens that are the author's: `biało-czerwony`, `polsko-niemiecki`,
`Bielsko-Biała`, `1939-1945`, `e-mail`, `SMS-a`. A regular expression that
joins hyphenated words would destroy every one of them, and it would do it
silently, in a program whose entire point is not damaging books.

So this module **detects and does not decide**. It answers one question about
each candidate — *what evidence is there that this hyphen is not the author's* —
and the honest answer is that only one strong kind of evidence exists inside a
single file:

    the same word appears elsewhere in this book without the hyphen

That is not a guess. If a book contains both `obo-jętna` and `obojętna`, one of
them is the conversion's doing, and the unhyphenated one is the word. Where the
book says so, this says `CONFIRMED`.

Everything else is `LIKELY` or `UNCERTAIN`, and neither is ever acted on
without a person. The recommendation on a `CONFIRMED` candidate is to join; a
recommendation is an opinion, and `decisions.Queue` will not apply one nobody
answered. A book rebuilt with nobody watching comes out with every hyphen the
publisher put in it.

The guards below matter more than the detector. Each of them was written
against a real shape of Polish word that a naive rule would have eaten.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

#: A hyphen with a letter on each side and no space anywhere near it. Only
#: HYPHEN-MINUS: an en dash between words is a range or an interval and is
#: somebody's punctuation, and a soft hyphen is a *hint* rather than a
#: character of the text — a different repair with a different argument.
_CANDIDATE = re.compile(r"(?<![\w-])(\w+)-(\w+)(?![\w-])", re.UNICODE)

#: Words split by this, for the "does the joined form appear elsewhere" test.
_WORD = re.compile(r"\w+(?:-\w+)*", re.UNICODE)

#: Confidence, and each value names the evidence rather than a number. A score
#: of 0.82 says nothing anybody can check; "the book contains the joined word
#: fourteen times" is a fact somebody can go and look at.
CONFIRMED = "confirmed"
LIKELY = "likely"
UNCERTAIN = "uncertain"

def _fold(word: str) -> str:
    """Case- and accent-insensitive, for counting occurrences only.

    Never for writing anything back. A book that writes `Obojętna` at the start
    of a sentence and `obo-jętna` in the middle of one is still evidence about
    the same word.
    """
    stripped = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


#: Left-hand parts that make a compound rather than a broken word. `-o` is the
#: Polish linking vowel — `biało-czerwony`, `polsko-niemiecki`, `słodko-gorzki`
#: — and it is the single most common false positive there is.
_LINKING_VOWELS = ("o", "io", "sko", "cko")

#: Prefixes and particles commonly joined by a hyphen. Held **folded**, because
#: that is how they are looked up — `_fold("pół")` is `"po\u0142"`, not `"pol"`,
#: and a list written in the unfolded spelling silently matches nothing.
_BOUND_PARTICLES = frozenset(
    _fold(particle)
    for particle in (
        "eks", "wice", "vice", "pseudo", "quasi", "arcy", "super", "eko",
        "nie", "pół", "mini", "maxi", "makro", "mikro", "auto", "anty",
    )
)


@dataclass(frozen=True)
class Candidate:
    """One hyphen, where it is, and what the book says about it."""

    word: str
    left: str
    right: str
    #: Container path of the document it is in.
    where: str
    #: The sentence around it, so a person can decide without opening the book.
    context: str
    confidence: str
    #: Why — in words, because this is what a person is shown.
    reason: str
    #: How often the joined form appears elsewhere in the book.
    joined_elsewhere: int = 0

    @property
    def joined(self) -> str:
        return f"{self.left}{self.right}"

    def __str__(self) -> str:
        return f"{self.where}: {self.word} → {self.joined} ({self.confidence})"


def _never_a_candidate(left: str, right: str) -> "str | None":
    """Shapes that are the author's whatever the rest of the book says.

    Structural rather than statistical, which is why these are checked first and
    cannot be overridden by evidence. A digit on one side is a range; a capital
    on the right is a name. No amount of counting makes `1939-1945` a broken
    word, and a program that could be argued into thinking so is one nobody
    should point at their library.
    """
    if any(character.isdigit() for character in left + right):
        return "po którejś stronie jest cyfra — to zakres albo numer"
    if right[:1].isupper():
        return "prawa część zaczyna się wielką literą — nazwa własna"
    if left.isupper() or right.isupper():
        return "któraś część jest wersalikami — skrót z końcówką"
    if len(left) == 1 or len(right) == 1:
        return "jedna litera po którejś stronie — to nie jest złamane słowo"
    if _fold(left) == _fold(right):
        # `dum-dum`, `Es-es`, `ping-pong` after folding is not one of these but
        # the shape is the same: a reduplication is a word, and a line break
        # does not produce two identical halves.
        return "obie części są tym samym słowem — to podwojenie, nie złamanie"
    return None


def _reads_as_a_compound(left: str) -> "str | None":
    """Why this *looks* like a compound — checked only when nothing else knows.

    The Polish linking vowel `-o-` is the most common false positive there is:
    `biało-czerwony`, `polsko-niemiecki`, `słodko-gorzki`. It is also, and this
    is the trap, how two of the audit's three real examples end — `obo-jętna`
    and `doboro-wym`. The first version of this module checked it before
    weighing evidence and therefore found neither of them.

    So it is a tie-breaker and not a guard. Where the book itself writes the
    joined word, the book wins: a real compound essentially never appears
    unhyphenated in the same text, and a broken one very often does.

    The bound particles are the same shape of guess and moved here from the
    absolute list for the same reason. `pół-` was in that list and never fired,
    because folding `pół` gives `poł` and the list held `pol` — and the accident
    was doing the right thing: measured on the owner's shelf, `Pół-nocy` sits in
    a book that writes `Północy` twenty-two times, so it is a broken line.
    Fixing the fold without moving the check would have traded a true positive
    for a tidier-looking table.
    """
    if _fold(left) in _BOUND_PARTICLES:
        return f"„{left}-” bywa przedrostkiem łączonym łącznikiem"
    folded = _fold(left)
    for ending in _LINKING_VOWELS:
        if folded.endswith(ending) and len(left) > len(ending) + 1:
            return f"lewa część kończy się na „-{ending}” — wygląda na spójkę złożenia"
    return None


def vocabulary(texts) -> Counter:
    """Every word in the book, folded, counted. The evidence base.

    Built from the whole book on purpose: a word broken in chapter four is
    almost always written whole in chapter nine, and that is the only place the
    answer can come from.
    """
    counts: Counter = Counter()
    for text in texts:
        for word in _WORD.findall(text):
            counts[_fold(word)] += 1
    return counts


def _context(text: str, start: int, end: int, width: int = 40) -> str:
    left = text[max(0, start - width):start].replace("\n", " ")
    right = text[end:end + width].replace("\n", " ")
    return f"…{left.strip()}{text[start:end]}{right.strip()}…"


def find(text: str, *, where: str, words: Counter) -> "list[Candidate]":
    """Candidates in one text node's worth of text.

    Called per text node rather than per document, which is what makes this
    DOM-aware: `<em>obo</em>-<em>jętna</em>` is markup that happens to contain a
    hyphen, and joining across it would move text between elements — a
    structural change dressed up as a spelling fix.
    """
    found: list[Candidate] = []
    for match in _CANDIDATE.finditer(text):
        left, right = match.group(1), match.group(2)
        if _never_a_candidate(left, right) is not None:
            continue

        elsewhere = words.get(_fold(left + right), 0)
        hyphenated = words.get(_fold(f"{left}-{right}"), 0)

        compound_shape = _reads_as_a_compound(left) is not None
        # One occurrence is thin evidence where both spellings are legitimate
        # Polish. Measured on the owner's shelf: `czerwonawo-złote` against a
        # single `czerwonawozłote`, `złocisto-brązowe` against a single
        # `złocistobrązowe` — both compounds a writer may set either way, and
        # both were being called confirmed on a count of one. Two is the
        # threshold, and it applies only to the shape that needs it.
        enough = elsewhere >= (2 if compound_shape else 1)

        if enough:
            # The book's own answer, and it outranks the heuristic below —
            # including the linking vowel, which is how the first version of
            # this module missed two of the audit's three examples.
            confidence = CONFIRMED
            reason = (
                f"ta książka pisze „{left}{right}” bez łącznika "
                f"{elsewhere}× — więc to jest to słowo"
            )
        elif compound_shape:
            # Nothing in the book says otherwise and the shape says compound.
            # Not a low-confidence candidate: not a candidate. Offering to join
            # `biało-czerwony` is not a question worth a person's time.
            continue
        elif hyphenated > 3:
            # The same hyphenation four times over is a spelling this book uses.
            # A line break does not fall in the same place four times.
            continue
        else:
            confidence = LIKELY if words.get(_fold(left), 0) == 0 else UNCERTAIN
            reason = (
                "nigdzie w książce nie ma ani „{0}{1}”, ani „{0}” osobno".format(left, right)
                if confidence == LIKELY
                else f"„{left}” występuje w książce samodzielnie — może być złożeniem"
            )
        found.append(
            Candidate(
                word=match.group(0),
                left=left,
                right=right,
                where=where,
                context=_context(text, match.start(), match.end()),
                confidence=confidence,
                reason=reason,
                joined_elsewhere=elsewhere,
            )
        )
    return found


def question_for(candidate: Candidate):
    """The candidate as something a person can be asked.

    Built here rather than in the stage so that the detector owns both halves of
    what it knows: the evidence and how it is put. `recommended` is `join` only
    where the book itself supplied the answer.
    """
    from .decisions import HYPHEN, KEEP, Option, Question
    from .report import Risk

    return Question(
        kind=HYPHEN,
        where=candidate.where,
        summary=f"„{candidate.word}” — łącznik w środku słowa",
        detail=f"{candidate.context}\n\n{candidate.reason}",
        options=(
            Option(
                KEEP,
                "Zostaw jak jest",
                "Słowo zostaje z łącznikiem, dokładnie tak jak w pliku źródłowym",
            ),
            Option(
                "join",
                f"Złącz w „{candidate.joined}”",
                f"W tekście będzie „{candidate.joined}”",
            ),
            Option(
                "write",
                "Wpisz poprawną formę",
                "W tekście będzie to, co wpiszesz",
                needs_value=True,
            ),
        ),
        recommended="join" if candidate.confidence == CONFIRMED else KEEP,
        reversible=False,
        risk=Risk.CONTENT,
        group=f"hyphen:{candidate.confidence}",
        subject=candidate.word,
    )


__all__ = [
    "CONFIRMED",
    "Candidate",
    "LIKELY",
    "UNCERTAIN",
    "find",
    "question_for",
    "vocabulary",
]
