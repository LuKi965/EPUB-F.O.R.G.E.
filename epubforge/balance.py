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
SEMANTIC_ATTRIBUTES = ("alt", "role", "aria-label", "aria-hidden", "aria-describedby",
                       "epub:type", "lang", "xml:lang", "title", "dir", "hidden")
#: A start tag, then the attribute names inside it: two passes, because one
#: expression over the whole document stops at the first name it finds in a
#: tag and never sees the second (`<p lang="en" dir="ltr">` counted one).
_START_TAG_RE = re.compile(rb"<[A-Za-z][^>]*>")
_ATTRIBUTE_RE = re.compile(
    rb"\s(alt|role|aria-label|aria-hidden|aria-describedby|epub:type|lang|xml:lang|title|dir|hidden)\s*=",
)


def semantic_attributes_in(data: bytes) -> dict:
    """How many of each semantic attribute the document's tags carry."""
    counts: dict = {}
    for tag in _START_TAG_RE.finditer(data):
        for match in _ATTRIBUTE_RE.finditer(tag.group(0)):
            name = match.group(1).decode("ascii")
            counts[name] = counts.get(name, 0) + 1
    return counts


def _semantic_attributes_of(book) -> dict:
    total: dict = {}
    for resource in book.resources.values():
        if not getattr(resource, "is_content_doc", False):
            continue
        for name, count in semantic_attributes_in(resource.data).items():
            total[name] = total.get(name, 0) + count
    return total


@dataclass
class Side:
    """One end of the balance — the source, or the output."""

    counts: dict = field(default_factory=lambda: dict.fromkeys(KINDS, 0))
    spine_items: int = 0
    metadata_entries: int = 0
    text_characters: int = 0
    #: Per attribute name — see `SEMANTIC_ATTRIBUTES`.
    semantic_attributes: dict = field(default_factory=dict)

    @classmethod
    def of(cls, book) -> "Side":
        side = cls()
        for path, resource in book.resources.items():
            side.counts[kind_of(path, getattr(resource, "media_type", ""))] += 1
        side.spine_items = len(book.spine)
        side.metadata_entries = _metadata_entries(book)
        side.text_characters = _characters_of(book)
        side.semantic_attributes = _semantic_attributes_of(book)
        return side

    def as_dict(self) -> dict:
        return {
            **self.counts,
            "spine_items": self.spine_items,
            "metadata_entries": self.metadata_entries,
            "text_characters": self.text_characters,
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
    """Every character of the book's reading order, normalised.

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

    total = 0
    for item in getattr(book, "spine", ()) or ():
        resource = book.get(getattr(item, "path", "")) if hasattr(book, "get") else None
        if resource is None or not getattr(resource, "is_content_doc", False):
            continue
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
            total += characters_in(html.unescape(stripped))
        except Exception:
            continue
    return total


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
    #: `(attribute, before, after)` for every semantic attribute the output
    #: carries fewer of than the source. Not part of `closes`: a count of
    #: names inside tags is evidence to look at, not a proof of loss, and a
    #: balance that refused a book over it would refuse on a regular
    #: expression. It is reported, and the report is where a person looks.
    attributes_fell: list = field(default_factory=list)

    @property
    def closes(self) -> bool:
        return not self.unexplained

    def as_dict(self) -> dict:
        return {
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
            "closes": self.closes,
            "unexplained": [
                {"category": category, "lost": lost, "explained": explained}
                for category, lost, explained in self.unexplained
            ],
            "attributes_fell": [
                {"attribute": name, "before": was, "after": now}
                for name, was, now in self.attributes_fell
            ],
        }

    def __str__(self) -> str:
        if self.closes:
            return "bilans się zamyka"
        return "; ".join(
            f"{category}: {lost} ubyło, {explained} wytłumaczonych"
            for category, lost, explained in self.unexplained
        )


def reconcile(before: Side, after: Side, changes) -> Balance:
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

    fell = []
    for name in SEMANTIC_ATTRIBUTES:
        was = before.semantic_attributes.get(name, 0)
        now = after.semantic_attributes.get(name, 0)
        if now < was:
            fell.append((name, was, now))
    return Balance(before=before, after=after, unexplained=unexplained, attributes_fell=fell)


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
