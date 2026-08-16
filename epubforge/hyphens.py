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

#: The two halves of a word cut by markup: a hyphen at the very end of one text
#: node, and a word starting the next. Deliberately anchored — a hyphen with
#: anything after it inside the same node is `_CANDIDATE`'s business.
_CUT_AT_END = re.compile(r"(?<![\w-])(\w+)-$", re.UNICODE)
_STARTS_A_WORD = re.compile(r"^(\w+)(?![-])", re.UNICODE)

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


@dataclass(frozen=True)
class CrossCandidate(Candidate):
    """A candidate whose halves are in two different text nodes.

    Carries the nodes themselves, because the stage has to write into both, and
    `joinable` — whether the element between the halves is a converter's bare
    wrapper or something somebody chose. A candidate that is not joinable is
    still worth showing: it is the one shape where the person can see that the
    book is fine and the markup is odd.
    """

    first: tuple = ()
    second: tuple = ()
    joinable: bool = False
    carrier: str = ""


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


def wanted_words(texts) -> "set[str]":
    """The only words the evidence base has to be able to count.

    A first pass over the book, collecting the words each candidate would need
    an answer about: the joined form, the hyphenated form and the left part.
    Nothing else is ever looked up, so nothing else needs to be remembered.
    """
    wanted: set[str] = set()
    for text in texts:
        if "-" not in text:
            continue
        for match in _CANDIDATE.finditer(text):
            left, right = match.group(1), match.group(2)
            wanted.add(_fold(left + right))
            wanted.add(_fold(f"{left}-{right}"))
            wanted.add(_fold(left))
    return wanted


def vocabulary(texts, wanted: "set[str] | None" = None) -> Counter:
    """How often each word appears in the book, folded. The evidence base.

    Built from the whole book on purpose: a word broken in chapter four is
    almost always written whole in chapter nine, and that is the only place the
    answer can come from.

    `wanted` bounds what is remembered, and on a large book it has to. EF-020,
    measured: counting *every* word of a 120 MB text held eleven million
    distinct keys and cost well over a gigabyte. A real book is nothing like
    that — one of the owner's has 103 000 words and 18 000 distinct, 17.6% —
    but "real books have small vocabularies" is an assumption about somebody
    else's library, and a dictionary, a concordance or a bad OCR pass breaks it.

    With `wanted` the cost is the number of *candidates*, which is measured in
    tens: 67 across the owner's thirty-two books. The answers are identical —
    `find` only ever looks up those three forms per candidate.
    """
    counts: Counter = Counter()
    for text in texts:
        for word in _WORD.findall(text):
            folded = _fold(word)
            if wanted is None or folded in wanted:
                counts[folded] += 1
    return counts


def _context(text: str, start: int, end: int, width: int = 40) -> str:
    left = text[max(0, start - width):start].replace("\n", " ")
    right = text[end:end + width].replace("\n", " ")
    return f"…{left.strip()}{text[start:end]}{right.strip()}…"


#: Elements a word may be cut by without the cut meaning anything.
#:
#: Exactly one tag, and it must carry no attributes at all. The shape this
#: exists for is a converter that wrapped every *line* of a PDF in a bare
#: `<span>` and left the line-break hyphen inside it — machinery, not writing.
#: An element with a `class`, a `style` or an `id` is presenting its half of the
#: word differently from the other half, and an `<em>` or an `<a>` means
#: something; joining across either of those does not fix a word, it moves text
#: out of an element somebody chose.
NEUTRAL_CARRIERS = ("span",)

#: Where a flow of text ends. A word cannot be cut across two of these, so no
#: candidate is ever built across one — `<p>koń-</p><p>ski</p>` is two
#: paragraphs, not a broken word, and gluing them would invent a sentence.
BLOCKS = frozenset({
    "p", "div", "li", "td", "th", "dd", "dt", "blockquote", "section", "article",
    "aside", "nav", "figure", "figcaption", "header", "footer", "main", "body",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table", "tr", "ul", "ol", "dl",
    "br",
})


def find(text: str, *, where: str, words: Counter) -> "list[Candidate]":
    """Candidates in one text node's worth of text.

    Per text node, which is what makes this DOM-aware, and `find_across` is the
    other half. The note that used to be here said joining across markup would
    move text between elements and left it at that — right about the danger and
    wrong to conclude blindness from it. `<em>obo</em>-<em>jętna</em>` really is
    markup containing a hyphen; `<span>obo-</span>jętna` is the very defect this
    module exists for, produced by converters that wrap each line of a PDF.
    Telling them apart is `find_across`'s job; not looking was this one's bug.
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

    # A word cut by markup somebody chose can be seen and kept and nothing more.
    # Joining it would move text out of an element with a class or a meaning on
    # it, and that is a structural change wearing a spelling fix's clothes — the
    # thing the per-node rule was originally right to be afraid of.
    if isinstance(candidate, CrossCandidate) and not candidate.joinable:
        return Question(
            kind=HYPHEN,
            where=candidate.where,
            summary=f"„{candidate.word}” — słowo przecięte znacznikiem <{candidate.carrier}>",
            detail=(
                f"{candidate.context}\n\n{candidate.reason}\n\n"
                f"Nie proponuję złączenia: obie połowy siedzą w różnych "
                f"elementach, a <{candidate.carrier}> niesie własne "
                f"formatowanie albo znaczenie. Złączenie przeniosłoby tekst "
                f"poza element, który ktoś wybrał — to zmiana struktury, a nie "
                f"pisowni."
            ),
            options=(
                Option(
                    KEEP,
                    "Zostaw jak jest",
                    "Słowo zostaje przecięte dokładnie tak, jak w pliku źródłowym",
                ),
            ),
            recommended=KEEP,
            reversible=True,
            risk=Risk.NONE,
            group="hyphen:cut-by-markup",
            subject=candidate.word,
        )

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


def _tag(element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return "?"
    return tag.rpartition("}")[2].lower()


def _is_neutral(element) -> bool:
    """Can a word be joined across this element without moving anything?"""
    return _tag(element) in NEUTRAL_CARRIERS and not element.attrib


def _same_flow(one, other, root) -> bool:
    """Are these two text nodes inside the same block of running text?

    Walked from the root rather than with `getparent()` chains so that a tree
    built by any parser answers the same way. Two nodes separated by a block
    element are two flows, and a hyphen at the end of one is the end of a line
    of prose rather than half a word.
    """
    seen_one = seen_other = False
    for element in root.iter():
        if element is one:
            seen_one = True
        if element is other:
            seen_other = True
            break
        if seen_one and _tag(element) in BLOCKS:
            return False
    return seen_one and seen_other


def find_across(nodes, *, root, where: str, words: Counter) -> "list[CrossCandidate]":
    """Candidates whose two halves live in different text nodes.

    DELTA-2026-08-15-001. `<span>obo-</span>jętna` produced nothing at all,
    while the same word inside one node was `CONFIRMED` — so a book converted by
    the one tool that makes this mistake hardest was the book this module could
    not see.

    Measured before writing it, on both mandatory fixtures and the six rebuilt
    copies of them: **not one text node in any of the eight ends in a hyphen.**
    The class is real and these two books are not in it, which is the honest
    reason this detects and does not go hunting: it costs a walk that is already
    happening, and it changes nothing without an answer.

    Whether the join is *offered* is a second question and the answer is the
    element in the middle. A bare `<span>` is a converter's line wrapper and
    joining across it moves nothing anybody chose; anything with a class, a
    style or a meaning of its own gets a candidate that can be seen and kept but
    not silently joined.
    """
    found: list[CrossCandidate] = []
    for index in range(len(nodes) - 1):
        element, attribute = nodes[index]
        text = getattr(element, attribute) or ""
        cut = _CUT_AT_END.search(text)
        if not cut:
            continue
        following, next_attribute = nodes[index + 1]
        after = getattr(following, next_attribute) or ""
        rest = _STARTS_A_WORD.match(after)
        if not rest:
            continue
        if not _same_flow(element, following, root):
            continue

        left, right = cut.group(1), rest.group(1)
        if _never_a_candidate(left, right) is not None:
            continue
        elsewhere = words.get(_fold(left + right), 0)
        if not elsewhere:
            # Cross-node needs the book's own word for it and nothing weaker.
            # Inside one node a shape argument can carry a candidate to
            # `LIKELY`; here the reader is also being asked about markup, and a
            # maybe about two things at once is not a question worth putting.
            continue

        carrier = element if attribute == "text" else following
        found.append(
            CrossCandidate(
                word=f"{left}-{right}",
                left=left,
                right=right,
                where=where,
                context=(text[-40:] + after[:40]).strip(),
                confidence=CONFIRMED,
                reason=(
                    f"ta książka pisze „{left}{right}” bez łącznika {elsewhere}×, "
                    f"a tutaj słowo jest przecięte znacznikiem "
                    f"<{_tag(carrier)}>"
                ),
                joined_elsewhere=elsewhere,
                first=(element, attribute),
                second=(following, next_attribute),
                joinable=_is_neutral(carrier),
                carrier=_tag(carrier),
            )
        )
    return found


def review_question(confidence: str, words: list):
    """One question for a whole class of candidates, carrying the words.

    The alternative — a question per word — was measured before it was rejected:
    101 `LIKELY` and 88 `UNCERTAIN` across 32 books, of which almost every entry
    read as a real compound. A queue of a hundred and eighty-nine questions that
    are mostly not defects is a queue nobody finishes, and the finding that asked
    for this detector warned about exactly that over-eagerness.
    """
    from .decisions import HYPHEN, KEEP, Option, Question
    from .report import Risk

    shown = ", ".join(f"„{word}”" for word in words[:40])
    more = f" … i jeszcze {len(words) - 40}" if len(words) > 40 else ""
    label = "prawdopodobne" if confidence == LIKELY else "niepewne"
    return Question(
        kind=HYPHEN,
        where="",
        summary=f"{len(words)} słów z łącznikiem — {label}, bez dowodu w tej książce",
        detail=(
            f"Ta książka nigdzie nie pisze tych słów bez łącznika, więc nie ma "
            f"dowodu, że łącznik jest usterką konwersji, a nie pisownią autora. "
            f"Wiele z nich to prawdziwe wyrazy złożone.\n\n{shown}{more}"
        ),
        options=(
            Option(
                KEEP,
                "Zostaw wszystkie",
                "Żadne z tych słów nie zostanie zmienione — tak jak dotąd",
            ),
            Option(
                "join",
                f"Złącz wszystkie {len(words)}",
                "Każde z tych słów straci łącznik; to zmiana treści i nie da się "
                "jej cofnąć z samego wyniku",
            ),
        ),
        recommended=KEEP,
        reversible=False,
        risk=Risk.CONTENT,
        group=f"hyphen-review:{confidence}",
        subject=f"{confidence}:{len(words)}",
    )


__all__ = [
    "CONFIRMED",
    "Candidate",
    "CrossCandidate",
    "LIKELY",
    "UNCERTAIN",
    "find",
    "find_across",
    "question_for",
    "review_question",
    "vocabulary",
    "wanted_words",
]
