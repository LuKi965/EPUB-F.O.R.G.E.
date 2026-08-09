"""Rebuild policy — the knobs that decide standards-vs-appearance tradeoffs."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import watermark

#: Raster/vector formats EPUB 3 readers must support without a fallback.
CORE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/svg+xml"}
CORE_FONT_TYPES = {
    "font/ttf",
    "font/otf",
    "font/woff",
    "font/woff2",
    "application/font-sfnt",
    "application/vnd.ms-opentype",
}


@dataclass
class Policy:
    """Controls how aggressively the rebuild normalises content.

    In the default (preserve) mode a construct that renders correctly but
    deviates from the specification is kept and reported. Under ``strict`` the
    same construct is rewritten to the conforming equivalent even when that can
    change how the book looks.
    """

    strict: bool = False

    #: Directory layout inside the container.
    content_dir: str = "EPUB"
    #: File name of the package document inside `content_dir`. EPUB 3 lets it
    #: be anything — `container.xml` says where it is — but readers exist that
    #: never read `container.xml` and look for `OEBPS/content.opf` outright.
    #: Together with `content_dir` this reproduces the layout every EPUB had
    #: before the specification stopped caring, which is a diagnostic worth
    #: being able to produce.
    package_name: str = "package.opf"

    #: Rewrite filenames to ASCII slugs and regroup them into typed folders.
    reorganize_files: bool = True

    #: Emit a legacy NCX alongside the EPUB 3 nav document for old readers.
    write_ncx: bool = True

    #: Deobfuscate embedded fonts and drop META-INF/encryption.xml.
    deobfuscate_fonts: bool = True

    #: Transcode non-core image formats (WebP, BMP, TIFF) to PNG.
    transcode_images: bool = True

    #: Normalise the XHTML and CSS inside the book. Off only in ``minimal``,
    #: where the promise is that content files come out byte for byte as they
    #: went in and just the container is regenerated.
    rewrite_content: bool = True

    #: Drop scripting. Off by default: some fixed-layout books need it.
    strip_scripts: bool = False

    #: Delete what the analysis found to have no effect — stylesheet rules for
    #: markup the book does not contain, and `<span>`s whose every rule says
    #: nothing. On in `strict`, where conformance and tidiness are the point;
    #: off everywhere else.
    #:
    #: It is a switch rather than a consequence of `strict` because the owner
    #: asked for one, as a standing rule and not about this feature: *whatever
    #: the application ever deletes should be either optional to untick, or
    #: something it asks about first.* He is right, and the reason is in this
    #: file's own history — every removal here looked obviously safe until a
    #: real book showed it was not. A switch costs one line and gives the person
    #: holding the book the last word.
    remove_dead: bool = False

    #: Remove files present in the archive but referenced by nothing.
    #:
    #: Off by default since 0.1.7, and it stays off until the dependency graph
    #: can prove a file is unused. Today it cannot: references reached only
    #: through ``img@srcset``, ``<picture><source srcset>`` or from inside an
    #: SVG are invisible to it, so the file goes and the markup that needs it
    #: stays. The output validates and renders a hole.
    #:
    #: The saving was never the point — a handful of kilobytes against deleting
    #: a picture somebody is still looking at.
    drop_orphans: bool = False

    #: What to do with a publisher's opaque watermark marker — one of
    #: :data:`epubforge.watermark.MODES`.
    #:
    #: The default is the strongest thing that takes nothing out of the reading
    #: order, because K1 — no character of the book's text is lost — is this
    #: tool's spine and no default gets to bend it. ``gather`` and ``remove``
    #: both do take the token out, on purpose, and both are therefore something
    #: a person chooses. No preset reaches either.
    watermarks: str = "consolidate"

    #: Repair the typography of the text itself — roadmap [7].
    #:
    #: Off everywhere, reached by no preset, and that is the point rather than
    #: caution about an unfinished feature. Every other switch in this file
    #: decides how markup is arranged around a text nothing may touch; this one
    #: lets a stage retype the text. A book comes back with characters it did
    #: not have, and no reader should discover that because a default changed.
    typography: bool = False

    #: Emit EPUB Accessibility 1.1 discovery metadata derived from the content.
    accessibility_metadata: bool = True

    #: Assert conformance ("wcag-a" / "wcag-aa" / "wcag-aaa"). Off by default:
    #: WCAG cannot be verified mechanically, and under the European
    #: Accessibility Act the claim is the publisher's to make, not the tool's.
    claim_conformance: str | None = None

    #: Reader-family compatibility profiles to apply — see :mod:`epubforge.compat`.
    #: Empty by default: the standards-clean output is the product, and every
    #: profile is a concession to a device that does not follow it.
    compat_profiles: tuple[str, ...] = ()

    #: Pin ``dcterms:modified`` instead of stamping the current time. Every ZIP
    #: entry already carries a fixed timestamp, so this is the last thing that
    #: differs between two runs on the same input; setting it makes the output
    #: byte-for-byte reproducible. An ISO 8601 UTC string, e.g.
    #: ``"2026-01-01T00:00:00Z"``.
    modified_override: str | None = None

    #: Force a language tag when the source has none or an invalid one.
    default_language: str = "en"

    #: Extra dc:* values supplied by the caller, applied verbatim.
    metadata_overrides: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A misspelt mode must not silently mean "leave the watermark alone":
        # that is the one outcome the caller would not notice in the report.
        if self.watermarks not in watermark.MODES:
            raise ValueError(
                f"unknown watermark mode: {self.watermarks!r} "
                f"(expected one of {', '.join(watermark.MODES)})"
            )

    @classmethod
    def preset(cls, name: str, **overrides) -> "Policy":
        if name == "strict":
            base = cls(strict=True, strip_scripts=False, remove_dead=True)
        elif name == "preserve":
            base = cls(strict=False)
        elif name == "minimal":
            # Container-only rebuild: content files come out byte-identical.
            # Nothing here may rename a file either, or the untouched documents
            # would be left pointing at paths that no longer exist.
            base = cls(
                strict=False,
                reorganize_files=False,
                transcode_images=False,
                drop_orphans=False,
                rewrite_content=False,
            )
        else:
            raise ValueError(f"unknown policy preset: {name!r}")
        for key, value in overrides.items():
            setattr(base, key, value)
        # The overrides go on after construction, so they have not been checked
        # yet; checking again costs nothing and closes the gap.
        base.__post_init__()
        return base
