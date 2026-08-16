"""The cover page: what makes one, and the rules that make it fit.

One module because there were two, and they disagreed. A cover page this
program **generates** was born with a full stylesheet — `html, body` given a
height, the body a centring flex box, the image limited and told to keep its
aspect ratio. A cover page the book **already had** was given two inline
declarations, `max-width: 100%` and `max-height: 100%`, and nothing else.

Those are not two ways of doing the same thing. `max-height: 100%` is a
percentage, and a percentage height resolves against the containing block; with
no height on `html` and `body` there is nothing to resolve against and the
declaration does nothing at all. So a tall cover in a book that already had a
cover page still came out across two screens, while the same image in a book
that had none came out right — and the difference was which of two code paths
happened to run (EF-026).

The other half of the same finding is how the cover is recognised.
`stages/content.py` resolved each `<img src>` against the document's *original*
path, at a point in the pipeline where `src` had already been rewritten to its
new one. That produces a path that names nothing, `path_map` answers `None` for
it, `None != None` is false — and a test meant to keep the cover rule on the
cover kept it on every unsized image in the book (EF-024). Here the question is
asked of the **manifest** instead: the package says which resource is the
cover, and that answer does not move when files do.
"""

from __future__ import annotations

#: What a cover page needs in order to show one page-sized image.
#:
#: `height: 100%` on both `html` and `body` is the load-bearing line: without
#: it the `max-height` below has no containing block to be a percentage of.
#: `object-fit: contain` keeps the aspect ratio when the limits do bite, which
#: is what stops a tall cover being squashed rather than shrunk.
COVER_STYLE = """html, body { margin: 0; padding: 0; height: 100%; }
      body { display: flex; align-items: center; justify-content: center; }
      img { max-width: 100%; max-height: 100%; object-fit: contain; }"""

#: The same rules, scoped to the images of a page that already exists, as a
#: `<style>` this program adds to that document's head. Written as a block
#: rather than inline for the reason in the module docstring: two of the three
#: rules are about `html` and `body`, and an inline style cannot say anything
#: about an ancestor.
COVER_STYLE_ADDED = """
      /* EPUB-Forge: nothing in this book sized the cover, so it was shown at
         its own pixel size — cropped on a small screen, a stamp on a large
         one. These are the same rules a generated cover page is born with.
         They can only ever make the image smaller than it already is. */
      html, body { height: 100%; }
      body { display: flex; align-items: center; justify-content: center; }
      img { max-width: 100%; max-height: 100%; object-fit: contain; }
    """


def cover_identities(book) -> "set[str]":
    """Every path that names this book's cover image.

    Both the path the manifest declares and whatever the rebuild renamed it to,
    because a document is examined after the rename and its `src` already points
    at the new name. Empty when the book declares no cover — and an empty set
    matches nothing, which is the point: the old code compared two `None`s and
    concluded they were the same thing.
    """
    declared = getattr(book, "cover_path", "") or ""
    if not declared:
        return set()
    identities = {declared}
    resource = book.get(declared)
    if resource is not None:
        for name in (resource.path, getattr(resource, "original_path", "")):
            if name:
                identities.add(name)
    return identities


def is_the_cover(book, candidate: str) -> bool:
    """Whether *candidate* is this book's cover image, per the manifest.

    A plain set membership, and that is the whole repair. What it replaces was
    an equality between two lookups that could both answer `None`.
    """
    return bool(candidate) and candidate in cover_identities(book)


__all__ = [
    "COVER_STYLE",
    "COVER_STYLE_ADDED",
    "cover_identities",
    "is_the_cover",
]
