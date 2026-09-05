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
#:
#: `max-height: 100vh`, not `100%`, and the unit is the repair (EF-062). A
#: percentage max-height resolves against the containing block, and when the
#: image sits inside a `<div>` whose height is `auto` — the shape both refused
#: books actually have — the percentage computes to *none* and the limit never
#: applies. Nobody saw it, because the gate compares against the source and the
#: source overflowed identically. It took the ink-measuring test the fifth
#: audit asked for to catch the promise not being kept: the fitted cover it
#: demanded came out blank-measured, a full-bleed overflow. `vh` resolves
#: against the viewport, which is always definite, wrapper or no wrapper.
#:
#: `margin: 0` is load-bearing too, and its absence from the *other* block cost
#: two books on the owner's shelf (EF-057). A body with `height: 100%` and the
#: browser's default 8px margin makes a page **taller than the window**; the
#: flex centring below then centres against that taller box, so the cover sits
#: lower than the window and its bottom edge falls off. The comment on the
#: other block claimed these rules "can only ever make the image smaller".
#: Measured, without this line they also **move** it — `91.2% → 82.0%` and
#: `56.2% → 44.5%` of the page's ink, and the render gate refused both books.
COVER_STYLE = """html, body { margin: 0; padding: 0; height: 100%; }
      body { display: flex; align-items: center; justify-content: center; }
      img { max-width: 100%; max-height: 100vh; object-fit: contain; }"""

#: The same rules, scoped to the images of a page that already exists, as a
#: `<style>` this program adds to that document's head. Written as a block
#: rather than inline for the reason in the module docstring: two of the three
#: rules are about `html` and `body`, and an inline style cannot say anything
#: about an ancestor.
COVER_STYLE_ADDED = """
      /* EPUB-Forge: nothing in this book sized the cover, so it was shown at
         its own pixel size — cropped on a small screen, a stamp on a large
         one. These are the same rules a generated cover page is born with,
         margin included — see the note on `margin: 0` below. */
      html, body { margin: 0; padding: 0; height: 100%; }
      body { display: flex; align-items: center; justify-content: center; }
      img { max-width: 100%; max-height: 100vh; object-fit: contain; }
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


#: The first line of the comment `COVER_STYLE_ADDED` carries — and, since
#: EF-063, a *signal*: it is how the render gate recognises, from the output
#: file alone, that this program refitted this cover page on purpose. A fact
#: the program wrote down beats a fact guessed back out of pixels — the same
#: principle `references.py` states for `REPAIRED`.
REFIT_MARK = "EPUB-Forge: nothing in this book sized the cover"

assert REFIT_MARK in COVER_STYLE_ADDED

__all__ = [
    "COVER_STYLE",
    "COVER_STYLE_ADDED",
    "REFIT_MARK",
    "cover_identities",
    "is_the_cover",
]


def cover_page_missing(book) -> bool:
    """Whether the navigation stage is going to synthesise a cover page: the
    book names a cover image that exists, and no landmark points at a content
    document as the cover.

    One predicate for two stages, on purpose. The structure stage numbers the
    reading-order files by spine position, and the navigation stage later
    puts a synthesised cover page at position 0 — so on a second rebuild
    every chapter's name moved up by one (K3, found on 14 of 60 shelf books
    by `tools/idempotencja.py` after the independent audit of 2026-09-04,
    EF-080). The structure stage now leaves position 0 for the page it
    knows is coming, and it knows by asking the same question this function
    answers for the navigation stage.
    """
    if not book.cover_path or book.cover_path not in book.resources:
        return False
    existing = next(
        (landmark for landmark in book.landmarks if landmark.epub_type == "cover"), None
    )
    cover_page = existing.target.split("#")[0] if existing else None
    if cover_page and cover_page in book.resources and book.resources[cover_page].is_content_doc:
        return False
    return True


#: The page this program writes for a book that names a cover image and has
#: no page showing it. `<meta>` and `<title>` on one line, because that is the
#: form the content stage serialises a head into: a page written in any other
#: shape came back different from the next rebuild (K3, EF-080).
COVER_PAGE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{xhtml}" xmlns:epub="{epub}" lang="{lang}" xml:lang="{lang}">
  <head>
    <meta charset="utf-8"/><title>{title}</title>
    <style>
      {cover_style}
    </style>
  </head>
  <body epub:type="cover">
    <section epub:type="cover">
      <img src="{href}" alt="{alt}"/>
    </section>
  </body>
</html>
"""


def synthesise_cover_page(book, policy) -> "tuple[str | None, str | None]":
    """Put a cover page into the book when `cover_page_missing` says one is
    due. Returns ``(page_path, warning)``: the path of the page written, or
    None; and ``"nav.cover-image-missing"`` when the book names a cover
    image it does not carry (the claim is dropped, so nothing points at a
    file that is not there).

    Called by the structure stage before the files are numbered and before
    any text stage runs — the page then gets a name like every other page
    and the same repairs in the same pass, which is what a second rebuild
    has to find unchanged (K3; 14 of 60 shelf books renamed every chapter,
    3 of 60 changed the cover's title, before this moved). The navigation
    stage calls it too, for a pipeline without the structure stage; the
    second call finds the page and does nothing.
    """
    from . import paths, xhtml
    from .model import Landmark, Resource, SpineItem

    if book.cover_path and book.cover_path not in book.resources:
        book.cover_path = None
        return None, "nav.cover-image-missing"
    if book.cover_path:
        # The manifest property, whether or not a page is written: a
        # reading system finds the cover by it.
        book.resources[book.cover_path].properties.add("cover-image")
    if not cover_page_missing(book):
        return None, None
    page_path = paths.content_path(policy, "text/0000-cover.xhtml")
    page_path = paths.unique(page_path, set(book.resources))
    markup = COVER_PAGE_TEMPLATE.format(
        xhtml=xhtml.XHTML_NS,
        epub=xhtml.EPUB_NS,
        lang=_escape(book.metadata.language or policy.default_language),
        title=_escape(book.metadata.title),
        href=paths.relative(page_path, book.cover_path),
        alt=_escape(book.metadata.title),
        cover_style=COVER_STYLE,
    )
    data = xhtml.serialize(xhtml.parse_document(markup.encode("utf-8"), page_path).root)
    book.add(Resource(path=page_path, media_type="application/xhtml+xml", data=data))
    book.spine.insert(0, SpineItem(page_path, linear=True))
    book.landmarks = [l for l in book.landmarks if l.epub_type != "cover"]
    book.landmarks.insert(0, Landmark("cover", "Cover", page_path))
    return page_path, None


def _escape(text: str) -> str:
    import html

    return html.escape(text or "", quote=True)

