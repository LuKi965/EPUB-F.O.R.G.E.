"""What went in, what came out, and whether the difference is accounted for.

BA-2026-003's remaining criterion, and the one the change ledger did not answer.
The ledger says *what this rebuild did*; a reader who wants to know *whether
anything went missing* has to trust that every removal remembered to write
itself down — which is trusting the thing under suspicion.

A balance is the other direction. It counts the source, counts the output, and
requires the difference in each category to be explained by something in the
ledger. A resource that disappears with no ledger entry is then not a quiet
omission, it is a failed reconciliation, and it fails loudly:

    3 dokumenty weszły, 2 wyszły, 0 wpisów w bilansie tłumaczy brakujący

The categories are the ones where a missing item costs a reader something:
documents, images, fonts, stylesheets, other resources, spine items, metadata
entries, and the characters of the text. Text has its own invariant (K1) and is
carried here as well so that one number can be read against the others.

**What this deliberately does not do** is balance every element of every
document. A rebuild rewrites markup by design — that is the whole job — and a
count of `<div>`s in against `<div>`s out would fail on every book while saying
nothing about whether the reader lost anything.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

#: Resource kinds counted apart, because losing one of each means a different
#: thing to whoever is reading the book.
KINDS = ("documents", "images", "fonts", "stylesheets", "other")

#: Actions in the ledger that legitimately reduce a count.
#:
#: `ADDED` and `CARRIED` cannot explain a *loss* and are not here; `MOVED` and
#: `REPLACED` keep the item and change where or what it is, so they cannot
#: either. What is left is removal and reconstruction, which is exactly the set
#: the audit names as high-risk — the balance and the ledger agree about which
#: operations are dangerous because they are looking at the same list.
EXPLAINS_A_LOSS = ("removed", "reconstructed")


def kind_of(path: str, media_type: str = "") -> str:
    """Which bucket a resource counts in, from its type and then its name."""
    media = (media_type or "").lower()
    if "xhtml" in media or "html" in media:
        return "documents"
    if media.startswith("image/"):
        return "images"
    if media.startswith("font/") or "font" in media or "opentype" in media:
        return "fonts"
    if "css" in media:
        return "stylesheets"
    suffix = path.rpartition(".")[2].lower()
    if suffix in ("xhtml", "html", "htm"):
        return "documents"
    if suffix in ("jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "tif", "tiff"):
        return "images"
    if suffix in ("ttf", "otf", "woff", "woff2"):
        return "fonts"
    if suffix == "css":
        return "stylesheets"
    return "other"


#: The attributes a reader who cannot see the page depends on, and which
#: neither K1 (prose) nor the resource counts (files) would notice losing.
#: The audit of 2026-09-03 (A-03) asked for them to be counted before and
#: after; the first count found EF-071 within sixty books. Counted by name
#: inside tags, over the bytes, because a full parse of every document twice
#: more is a cost the largest book on the shelf would feel and a count is
#: not a parse: a decrease here is a reason to look, never a verdict.
SEMANTIC_ATTRIBUTES = ("alt", "role", "aria-*", "epub:type", "lang", "xml:lang", "title", "dir", "hidden")
#: A start tag, then the attribute names inside it: two passes, because one
#: expression over the whole document stops at the first name it finds in a
#: tag and never sees the second (`<p lang="en" dir="ltr">` counted one).
#: The tag expression steps over quoted values, so a raw `>` inside one does
#: not end the tag early and hide the attributes after it (EF-075).
#: `aria-*` is every ARIA attribute by name, not three picked by hand: the
#: independent audit of 2026-09-04 found `aria-labelledby` on the shelf that
#: the hand-picked list did not see — a ratchet narrower than the measurement
#: that found the fall it was built for.
_START_TAG_RE = re.compile(rb"<[A-Za-z](?:[^>\"']|\"[^\"]*\"|'[^']*')*>")
_ATTRIBUTE_RE = re.compile(
    rb"\s(alt|role|aria-[a-z]+|epub:type|lang|xml:lang|title|dir|hidden)\s*=",
)


def semantic_attributes_in(data: bytes) -> dict:
    """How many of each semantic attribute the document's tags carry."""
    counts: dict = {}
    for tag in _START_TAG_RE.finditer(data):
        for match in _ATTRIBUTE_RE.finditer(tag.group(0)):
            name = match.group(1).decode("ascii")
            counts[name] = counts.get(name, 0) + 1
    return counts


#: The same attribute with its value, inside a named tag: what the count by
#: name cannot see. EF-089's second half (DROGA-DO-1.0, 6.3): an `alt` moved
#: from the picture it described to a different one, or an `aria-label`
#: reworded, leaves every name's count exactly where it was. Counted as
#: `(tag, name, value)` — the value in either quote style, the tag as
#: written, lower-cased, so that a rewrite of markup that keeps every
#: attribute where it belongs balances and one that moves it does not.
_ATTRIBUTE_VALUE_RE = re.compile(
    rb"\s(alt|role|aria-[a-z]+|epub:type|lang|xml:lang|title|dir|hidden)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')",
)
_TAG_NAME_RE = re.compile(rb"<([A-Za-z][\w:.-]*)")


def semantic_attribute_triples_in(data: bytes) -> dict:
    """How many times each `(tag, name, value)` the document's tags carry."""
    counts: dict = {}
    for tag in _START_TAG_RE.finditer(data):
        start = tag.group(0)
        named = _TAG_NAME_RE.match(start)
        element = named.group(1).decode("ascii", "replace").lower() if named else "?"
        for match in _ATTRIBUTE_VALUE_RE.finditer(start):
            name = match.group(1).decode("ascii")
            raw = match.group(2) if match.group(2) is not None else match.group(3)
            # The value as a reader meets it: entities resolved (the source
            # writes `i&#160;Ian`, the rebuild writes the character, and the
            # first shelf run called that a lost `alt`), whitespace folded.
            value = " ".join(html.unescape((raw or b"").decode("utf-8", "replace")).split())
            key = (element, name, value)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _semantic_attributes_by_document(book) -> dict:
    """Per content document, keyed by its archive path."""
    by_document: dict = {}
    for resource in book.resources.values():
        if not getattr(resource, "is_content_doc", False):
            continue
        by_document[resource.path] = semantic_attributes_in(resource.data)
    return by_document


def _semantic_triples_by_document(book) -> dict:
    by_document: dict = {}
    for resource in book.resources.values():
        if not getattr(resource, "is_content_doc", False):
            continue
        by_document[resource.path] = semantic_attribute_triples_in(resource.data)
    return by_document


def _summed(counts_per_document) -> dict:
    total: dict = {}
    for counts in counts_per_document:
        for name, count in counts.items():
            total[name] = total.get(name, 0) + count
    return total


@dataclass
class Side:
    """One end of the balance — the source, or the output."""

    counts: dict = field(default_factory=lambda: dict.fromkeys(KINDS, 0))
    spine_items: int = 0
    metadata_entries: int = 0
    text_characters: int = 0
    #: Characters per content document, keyed by the name the document had in
    #: the source. Not serialised, for the same reason as the maps below: the
    #: totals are the balance, a map per document is a log.
    text_characters_by_document: dict = field(default_factory=dict)
    #: Documents of the reading order this side could not count at all (6.14).
    #: Named rather than skipped: a document counted on one side and not on the
    #: other moves `text_characters` in a direction nobody put there.
    text_uncounted: tuple = ()
    #: Per attribute name — see `SEMANTIC_ATTRIBUTES`.
    semantic_attributes: dict = field(default_factory=dict)
    #: The same, per content document, so that a document the ledger says was
    #: removed can be taken out of the comparison. Not serialised: a map with
    #: an entry for every document of a 9 809-document book is a log, and the
    #: totals above are the balance.
    semantic_attributes_by_document: dict = field(default_factory=dict)
    #: `(tag, name, value)` counts per content document — the attribute
    #: where it stands and what it says (EF-089, second half). Not
    #: serialised, for the same reason as the map above.
    semantic_triples_by_document: dict = field(default_factory=dict)
    #: Every resource by the name it had in the *source*, whatever it is
    #: called now: the model records `original_path` on every rename, so an
    #: output resource is identified by where it came from. EF-084: counts per
    #: category let a generated NCX stand in for a lost text file — one
    #: `other` went out, one `other` came in, the balance closed. A bag of
    #: numbers cannot tell a replacement from a loss; a set of identities can.
    identities: dict = field(default_factory=dict)
    #: The names the resources carry *now*, for following a ledger that
    #: speaks of a file by the name it had at the moment of the entry.
    paths: set = field(default_factory=set)

    @classmethod
    def of(cls, book) -> "Side":
        side = cls()
        for path, resource in book.resources.items():
            side.counts[kind_of(path, getattr(resource, "media_type", ""))] += 1
            origin = getattr(resource, "original_path", None) or path
            side.identities[origin] = kind_of(path, getattr(resource, "media_type", ""))
            side.paths.add(path)
        side.spine_items = len(book.spine)
        side.metadata_entries = _metadata_entries(book)
        side.text_characters_by_document, side.text_uncounted = _characters_by_document(book)
        side.text_characters = sum(side.text_characters_by_document.values())
        side.semantic_attributes_by_document = _semantic_attributes_by_document(book)
        side.semantic_attributes = _summed(side.semantic_attributes_by_document.values())
        side.semantic_triples_by_document = _semantic_triples_by_document(book)
        return side

    def as_dict(self) -> dict:
        return {
            **self.counts,
            "spine_items": self.spine_items,
            "metadata_entries": self.metadata_entries,
            "text_characters": self.text_characters,
            "text_uncounted": len(self.text_uncounted),
            "semantic_attributes": dict(self.semantic_attributes),
        }


#: Every field on `Metadata` holding a collection, where its length is a number
#: of statements. `dict`s are here too: `len` of a mapping is the number of
#: things it says, which is the question.
_METADATA_LISTS = (
    "titles",
    "creators",
    "identifiers",
    "languages_extra",
    "subjects",
    "title_alternate_scripts",
    "accessibility",
    "media_durations",
    "media_classes",
    "collection_memberships",
    "extra_meta",
    "extra_properties",
    "extra_refinements",
    "dublin_core_extra",
    "links",
    "metadata_comments",
)

#: Every single-valued field that is a statement when it is set.
_METADATA_SINGLES = (
    "subtitle",
    "sort_title",
    "language",
    "direction",
    "title_language",
    "title_direction",
    "publisher",
    "published",
    "modified",
    "description",
    "rights",
    "source",
    "series",
    "series_index",
    "accessibility_summary",
    "conforms_to",
)


#: Fields of `Metadata` that are deliberately not statements about the book.
#: Named rather than left out, so `test_balance` can hold the two lists above to
#: the model and fail when a field is added to it and counted by neither.
_METADATA_BOOKKEEPING = ("title_ids", "prefixes")


def characters_in(text: str) -> int:
    """How many characters of text that is, once normalised.

    Through `typography.canonical`, which is what every other comparison in this
    program already means by "the same text". A rebuild collapses runs of
    whitespace and rewrites line endings by design; counting raw characters
    would report those as thousands lost on every book and the number would be
    useless within a release.

    The specification asked for `typography.fold`. There is no such function —
    `canonical` is the one this module has, and using it keeps one definition
    of sameness rather than adding a second that would drift from the first.
    """
    from . import typography

    return len(typography.canonical(text or ""))


_TAG_RE = None
_NOT_TEXT_RE = None


def _characters_of(book) -> int:
    """Every character of the book's reading order, normalised — as one number.

    The one-number form of `_characters_by_document`, which is what the balance
    itself uses: a total cannot say which document it failed to read, and that
    is exactly what the two sides have to agree on.
    """
    counted, _ = _characters_by_document(book)
    return sum(counted.values())


def _characters_by_document(book) -> "tuple[dict, tuple]":
    """Characters per content document of the reading order, and the documents
    that could not be counted at all.

    Keyed by the name the document had in the **source** (`original_path`),
    the same identity the resource counts use, so the two sides of the balance
    can be compared document by document even when the rebuild renamed
    everything.

    Only the spine, and in spine order: a document nothing points at carries no
    text a reader will meet, and K1 is a statement about the reading order.

    **Extracted with a regular expression rather than by parsing**, which is not
    a shortcut. Parsing here charges the document budget a second time, on
    documents the reader has already paid for — and `BudgetExceeded` is a
    `BaseException` by design, so it does not stop at the `except` below. The
    result was that a book with deeply nested markup stopped being refused by
    the stage that is supposed to refuse it and started blowing up in a counter
    that exists to put a number in a report. Three tests said so.

    A number in a report may not decide whether a book rebuilds. This counts
    what is there and never raises.
    """
    import html
    import re

    global _TAG_RE, _NOT_TEXT_RE
    if _TAG_RE is None:
        _TAG_RE = re.compile(rb"<[^>]*>")
    if _NOT_TEXT_RE is None:
        # `<style>` and `<script>` sit inside the body of a document and are not
        # read by anybody. Stripping tags alone leaves their **contents** behind,
        # and those contents were being counted as the book's text.
        #
        # Found by EF-041 rather than on purpose, which is worth writing down.
        # Fixing the cover template stopped a stylesheet block from being
        # injected into a chapter, and the character balance promptly reported
        # 431 → 388: a loss of 43 characters that were never text, on a rebuild
        # that had lost nothing. The count had been inflated by exactly the CSS
        # this program adds — so the closer the rebuild came to touching a
        # document, the more "text" it appeared to gain.
        _NOT_TEXT_RE = re.compile(
            rb"<(style|script)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
        )

    counted: dict = {}
    uncounted: list = []
    for item in getattr(book, "spine", ()) or ():
        path = getattr(item, "path", "")
        resource = book.get(path) if hasattr(book, "get") else None
        if resource is None or not getattr(resource, "is_content_doc", False):
            continue
        origin = getattr(resource, "original_path", None) or path
        try:
            readable = _NOT_TEXT_RE.sub(b" ", resource.data)
            stripped = _TAG_RE.sub(b" ", readable).decode("utf-8", "replace")
            # Character references resolved before counting, because the two
            # sides of this balance are written differently. A legacy source
            # spells the word `Rozdzia&#322;`; the rebuilt document spells it
            # `Rozdział`. Same word, same reading, twelve characters against
            # eight — and the balance was subtracting the difference and calling
            # it lost text.
            #
            # Measured on the suite's own legacy fixture: 431 → 388, a "loss" of
            # 43 characters on a rebuild that lost nothing, every one of them an
            # entity the rebuild had decoded. Most books this program is for are
            # legacy books full of `&#261;` and `&nbsp;`, so K1's number was
            # meaningless for exactly the books it matters most on.
            #
            # After stripping tags rather than before: `&lt;p&gt;` in somebody's
            # text is text, and unescaping first would turn it into a tag for
            # the stripper to eat.
            counted[origin] = counted.get(origin, 0) + characters_in(html.unescape(stripped))
        except Exception:  # noqa: BLE001 — a count is not worth a lost book
            # Nothing above raises in the ordinary way: the substitutions work
            # on bytes, the decode replaces what it cannot read, `html.unescape`
            # takes any string. What is left is the exhaustion kind —
            # `MemoryError` on a document larger than this machine — and a
            # resource whose `data` is not what it claims.
            #
            # Broad, but no longer silent (6.14): the document is named, and
            # `reconcile` takes it off **both** sides. This function counts one
            # side of the balance, so a document counted before and skipped
            # after used to look like lost text, and the other way round like
            # text appearing — a number wrong in a direction nobody sees. It
            # has not happened on the shelf (160 books, every balance
            # explained); now, if it does, it says so instead of leaning.
            uncounted.append(origin)
    return counted, tuple(uncounted)


def _metadata_entries(book) -> int:
    """Every distinct thing the package says about the book.

    Counted across the whole of `Metadata` rather than a handful of its fields,
    and the first version of this got that wrong in both directions at once.

    It read `metadata.extra`, which **does not exist** — the model spells it
    `extra_meta`, `extra_properties`, `extra_refinements` and
    `dublin_core_extra`. `getattr` with a default turned that into a silent
    zero, so the vendor vocabulary was never counted and the exact loss this was
    written for, F-011's, could have happened again without the balance saying a
    word. A default is how a typo becomes a check that passes.

    And it counted `titles` while ignoring `subtitle`, which is the same
    statement in a different slot. On a book whose EPUB 2 package carries two
    `<dc:title>` elements the reader keeps the first as the title and moves the
    second to `subtitle`; both are written out, both are in the file, and the
    balance reported a metadata entry lost. That is 21 of the 93 books in the
    owner's corpus — a quarter of them — every one told it had lost something it
    still had.

    A false alarm at that rate is worse than no check. It teaches whoever reads
    the report to skip the one line that means something.
    """
    metadata = book.metadata
    total = sum(
        len(getattr(metadata, name, None) or ()) for name in _METADATA_LISTS
    )
    total += sum(1 for name in _METADATA_SINGLES if getattr(metadata, name, None))
    return total


@dataclass
class Balance:
    """The two sides and what the ledger says about the gap between them."""

    before: Side
    after: Side
    #: `(category, lost, explained)` for every category that shrank.
    unexplained: list = field(default_factory=list)
    #: Source resources that are in the output under no name at all, and that
    #: no removal or reconstruction in the ledger names (EF-084). Held by
    #: identity, so a resource added elsewhere cannot stand in for one lost.
    unexplained_paths: list = field(default_factory=list)
    #: `(attribute, before, after)` for every semantic attribute the output
    #: carries fewer of than the source. Not part of `closes`: a count of
    #: names inside tags is evidence to look at, not a proof of loss, and a
    #: balance that refused a book over it would refuse on a regular
    #: expression. It is reported, and the report is where a person looks.
    attributes_fell: list = field(default_factory=list)
    #: Documents either side could not count the characters of (6.14). Not part
    #: of `closes`: failing to count a document is not evidence that anything
    #: was lost — it is evidence that this number does not know. What it must
    #: not do is lean, so the documents come off both sides and are named.
    text_uncounted: list = field(default_factory=list)

    @property
    def text_characters_compared(self) -> tuple:
        """The two character totals with every uncounted document taken off
        **both** sides, so they are numbers about the same documents."""
        def without(side: Side) -> int:
            return sum(
                count for path, count in side.text_characters_by_document.items()
                if path not in set(self.text_uncounted)
            )

        return without(self.before), without(self.after)

    @property
    def closes(self) -> bool:
        # Both: the counts per category, and the identities (EF-084). The
        # identity half was measured on the owner's 160 books before it
        # joined the verdict — the first run refused real books over the NCX
        # and the navigation document, which the ledger moves by the name
        # they had at the moment of the entry; `reconcile` follows that chain
        # now, and the second run had nothing unexplained.
        return not self.unexplained and not self.unexplained_paths

    def as_dict(self) -> dict:
        return {
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
            "closes": self.closes,
            "unexplained": [
                {"category": category, "lost": lost, "explained": explained}
                for category, lost, explained in self.unexplained
            ],
            "unexplained_paths": list(self.unexplained_paths),
            "attributes_fell": [
                {"attribute": name, "before": was, "after": now}
                for name, was, now in self.attributes_fell
            ],
            "text_uncounted": list(self.text_uncounted),
            # The comparable pair, always: on the ordinary book it is the two
            # totals unchanged, and the reader of the report never has to know
            # which case this was.
            "text_characters_compared": dict(
                zip(("before", "after"), self.text_characters_compared)
            ),
        }

    def __str__(self) -> str:
        if self.unexplained_paths and not self.unexplained:
            shown = ", ".join(self.unexplained_paths[:3])
            more = f" (+{len(self.unexplained_paths) - 3})" if len(self.unexplained_paths) > 3 else ""
            return f"{len(self.unexplained_paths)} zasobów źródła bez wpisu w bilansie zmian: {shown}{more}"
        if self.closes:
            return "bilans się zamyka"
        return "; ".join(
            f"{category}: {lost} ubyło, {explained} wytłumaczonych"
            for category, lost, explained in self.unexplained
        )


def reconcile(before: Side, after: Side, changes, rewrites: "dict | None" = None) -> Balance:
    """Compare the two sides and hold the ledger to the difference.

    A category that grew is not examined: a rebuild that generates a navigation
    document or a cover page adds resources on purpose, and `test_change_ledger`
    already holds those to their own entries. What must be explained is what
    went *missing*, because that is the direction in which a reader loses.
    """
    explained: dict[str, int] = {}
    for change in changes or ():
        if getattr(change.action, "value", change.action) not in EXPLAINS_A_LOSS:
            continue
        subject = getattr(change, "subject", "") or ""
        category = subject if subject in KINDS else _category_for(change)
        explained[category] = explained.get(category, 0) + 1

    # By identity (EF-084): a source resource that is in the output under no
    # name — its own or a new one — has to be named by a removal or a
    # reconstruction in the ledger. The ledger writes the path as the subject
    # or, for an orphan, at the head of `before` ("path (N B)"); both count.
    named: set[str] = set()
    moved: dict[str, str] = {}
    for change in changes or ():
        action = getattr(change.action, "value", change.action)
        subject = getattr(change, "subject", "") or ""
        before_text = getattr(change, "before", "") or ""
        after_text = getattr(change, "after", "") or ""
        if action == "moved" and before_text and after_text:
            # A file written again under a new name — the NCX, most often —
            # is the same resource; the ledger says where it went.
            moved[before_text] = after_text
            continue
        if action not in EXPLAINS_A_LOSS:
            continue
        for text in (subject, before_text):
            head = text.split(" (", 1)[0].strip()
            if head:
                named.add(head)
    # A ledger entry speaks of a file by the name it had *then*: the
    # relayout moves `EPUB/extra.txt` to `EPUB/misc/extra.txt` and a later
    # removal names the second. So every name a resource has carried is
    # followed, move by move, and any of them present in the output or named
    # by a removal explains the source identity.
    def names_of(path: str) -> set:
        chain = {path}
        while path in moved and moved[path] not in chain:
            path = moved[path]
            chain.add(path)
        return chain

    present = set(after.identities) | after.paths
    unexplained_paths = sorted(
        path for path in before.identities
        if not (names_of(path) & present) and not (names_of(path) & named)
    )

    unexplained = []
    for category in (*KINDS, "spine_items", "metadata_entries"):
        was = before.as_dict()[category]
        now = after.as_dict()[category]
        if now >= was:
            continue
        lost = was - now
        covered = explained.get(category, 0)
        if covered < lost:
            unexplained.append((category, lost, covered))

    fell = _attributes_that_fell(before, after, changes, rewrites or {})
    # 6.14: a document one side could not count is taken off both. Either side
    # is enough to disqualify it — the point is that the two numbers are about
    # the same documents, whichever side failed to read one.
    uncounted = sorted(set(before.text_uncounted) | set(after.text_uncounted))
    return Balance(
        before=before,
        after=after,
        unexplained=unexplained,
        unexplained_paths=unexplained_paths,
        attributes_fell=fell,
        text_uncounted=uncounted,
    )


def _attributes_that_fell(before: Side, after: Side, changes, rewrites: "dict | None" = None) -> list:
    """Every semantic attribute the output carries fewer of than the source,
    once the documents the ledger says were removed are taken out.

    A document removed with an entry — an orphan swept on request, junk from
    the archive — took its attributes with it, and the entry is the claim;
    warning about that fall would warn about a removal the report already
    states. A document that left *without* an entry keeps counting: that is
    the shape of EF-071, the old navigation document replaced by a regenerated
    one, and this count exists to see exactly that. Documents that were moved
    rather than removed are not matched by path and keep counting too, which
    is the same comparison as before this function knew about paths.
    """
    was = dict(before.semantic_attributes)
    for path, counts in before.semantic_attributes_by_document.items():
        if path in after.semantic_attributes_by_document:
            continue
        if not _ledger_says_removed(path, changes):
            continue
        for name, count in counts.items():
            was[name] = was.get(name, 0) - count
    fell = []
    # Every name either side counted — a name only the source carries is
    # exactly the one that fell to zero.
    for name in sorted(set(was) | set(after.semantic_attributes)):
        now = after.semantic_attributes.get(name, 0)
        if now < was.get(name, 0):
            fell.append((name, was[name], now))
    fell.extend(
        _attributes_that_moved(before, after, changes, {name for name, _, _ in fell}, rewrites or {})
    )
    return fell


def _attributes_that_moved(before: Side, after: Side, changes, already: set, rewrites: dict) -> list:
    """The same count taken with the tag and the value (EF-089, second half).

    A name's count can hold while the attribute itself did not: an `alt`
    moved from one picture to another, an `aria-label` reworded, a `role`
    that left a `<nav>` and turned up on a `<div>` — none of that moves a
    number by name, all of it is a change assistive software meets. So the
    same comparison is made once more on `(tag, name, value)`, with the
    documents the ledger says were removed taken out as above; a triple the
    output carries fewer of is reported as the attribute, its value and the
    element it stood on. A name already reported as fallen is not reported
    again in its own triples — one line says it.

    *rewrites* is what this program changed on purpose and said so: attribute
    name → the documents whose value of it a reported repair rewrote (the
    cover's `alt` described, a document's `lang` corrected on the evidence
    of its letters). Measured on the owner's 160 books before this joined
    the report: without it, 151 books "lost" an `alt` on the cover page and
    a `lang` on `<html>` — every one a repair with its own line. Those pairs
    of document and name are left out on both sides; everything else in the
    document still counts.
    """
    def counted(by_document: dict) -> dict:
        total: dict = {}
        for path, counts in by_document.items():
            for key, count in counts.items():
                if path in rewrites.get(key[1], ()):
                    continue
                total[key] = total.get(key, 0) + count
        return total

    was = counted(before.semantic_triples_by_document)
    for path, counts in before.semantic_triples_by_document.items():
        if path in after.semantic_triples_by_document:
            continue
        if not _ledger_says_removed(path, changes):
            continue
        for key, count in counts.items():
            if path in rewrites.get(key[1], ()):
                continue
            was[key] = was.get(key, 0) - count
    now_all = counted(after.semantic_triples_by_document)
    moved = []
    for key in sorted(was):
        element, name, value = key
        if name in already:
            continue
        now = now_all.get(key, 0)
        if now < was[key]:
            shown = value if len(value) <= 40 else value[:37] + "…"
            moved.append((f'{name}="{shown}" na <{element}>', was[key], now))
    return moved


def _ledger_says_removed(path: str, changes) -> bool:
    """Whether an entry in the ledger names this archive path as removed.

    The entries that remove a whole file put the path either in the subject
    (`structure.junk-removed`) or at the head of `before`, as
    "OEBPS/x.xhtml (1 234 B)" (`structure.orphan-removed`). A path that merely
    appears somewhere inside another path's entry is not a match.
    """
    for change in changes or ():
        if getattr(change.action, "value", change.action) != "removed":
            continue
        for text in (getattr(change, "subject", "") or "", getattr(change, "before", "") or ""):
            if text == path or text.startswith(f"{path} "):
                return True
    return False


def _category_for(change) -> str:
    """Which count a ledger entry is about, when its subject is not a category.

    Ledger subjects are written for a person — "stylesheet", "3 rules", a path
    — so this maps them back onto the buckets. A subject nothing recognises
    lands in `other`, which is the honest place for it: it explains a loss of
    something uncounted rather than silently excusing a document.
    """
    subject = (getattr(change, "subject", "") or "").lower()
    if "/" in subject or "." in subject:
        return kind_of(subject)
    for category, words in (
        ("documents", ("document", "dokument", "chapter", "rozdział")),
        ("images", ("image", "obraz", "picture", "cover", "okładka")),
        ("fonts", ("font", "czcionk")),
        ("stylesheets", ("stylesheet", "css", "arkusz", "rule", "reguł")),
        ("spine_items", ("spine", "kolejnoś", "reading order")),
        ("metadata_entries", ("metadata", "metadan", "identifier", "title", "tytuł")),
    ):
        if any(word in subject for word in words):
            return category
    return "other"
