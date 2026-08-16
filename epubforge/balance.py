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


@dataclass
class Side:
    """One end of the balance — the source, or the output."""

    counts: dict = field(default_factory=lambda: dict.fromkeys(KINDS, 0))
    spine_items: int = 0
    metadata_entries: int = 0
    text_characters: int = 0

    @classmethod
    def of(cls, book) -> "Side":
        side = cls()
        for path, resource in book.resources.items():
            side.counts[kind_of(path, getattr(resource, "media_type", ""))] += 1
        side.spine_items = len(book.spine)
        side.metadata_entries = _metadata_entries(book)
        return side

    def as_dict(self) -> dict:
        return {
            **self.counts,
            "spine_items": self.spine_items,
            "metadata_entries": self.metadata_entries,
            "text_characters": self.text_characters,
        }


def _metadata_entries(book) -> int:
    """Every distinct thing the package says about the book.

    Counted rather than summed from one field, because the loss this exists to
    catch — F-011's — was a whole vocabulary vanishing while the title stayed
    put.
    """
    metadata = book.metadata
    total = len(getattr(metadata, "titles", []) or [])
    total += len(getattr(metadata, "creators", []) or [])
    total += len(getattr(metadata, "identifiers", []) or [])
    total += len(getattr(metadata, "extra", []) or [])
    total += 1 if getattr(metadata, "language", "") else 0
    return total


@dataclass
class Balance:
    """The two sides and what the ledger says about the gap between them."""

    before: Side
    after: Side
    #: `(category, lost, explained)` for every category that shrank.
    unexplained: list = field(default_factory=list)

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
    return Balance(before=before, after=after, unexplained=unexplained)


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
