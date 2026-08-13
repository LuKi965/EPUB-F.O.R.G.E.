"""Rebuild policy — the knobs that decide standards-vs-appearance tradeoffs."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import watermark

#: Raster/vector formats EPUB 3 readers must support without a fallback.
#:
#: `image/webp` belongs here and was missing until 0.2.20. EPUB 3.3 lists it
#: among the core media types, and this is not a reading of the prose: the
#: EPUBCheck we ship validates a book containing a bare `image/webp` with no
#: fallback and reports zero errors, under EPUB 3.3 rules. A foreign resource
#: used without a fallback is an error, so the validator saying nothing is the
#: validator saying the type is core.
#:
#: Its absence was not cosmetic. Everything outside this set is transcoded to
#: PNG through a single-frame decode, so a two-frame animated WebP came out a
#: still picture — measured, not feared — with its ICC profile and its metadata
#: gone, in a book that needed none of it changed.
CORE_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/svg+xml",
    "image/webp",
}
CORE_FONT_TYPES = {
    "font/ttf",
    "font/otf",
    "font/woff",
    "font/woff2",
    "application/font-sfnt",
    "application/vnd.ms-opentype",
}


#: Characters that cannot appear in a path this program writes into an archive.
#: `"` and `&` are here because the path is also interpolated into the XML of
#: `container.xml`; the rest are here because they are how a path stops meaning
#: one file.
_FORBIDDEN_IN_PATH = set('"&<>\\\x00:|?*')


def _check_ocf_segment(field_name: str, value: str, *, allow_empty: bool) -> None:
    """Refuse a package path that cannot safely be a path.

    `content_dir` and `package_name` are interpolated into two places at once:
    the names of ZIP members and the text of `container.xml`. Neither was
    checked, and `Policy` is public API — so a library caller, a preset or a
    future configuration file could set `content_dir='../evil&dir'` and
    `package_name='p"q.opf'` and get exactly what it asked for. Measured on
    0.2.19: four archive members beginning `../`, a `container.xml` that lxml
    refuses to parse, and an internal verifier that pronounced the result good.
    An unescaped `&` is enough on its own; the `..` is how a zip-slip looks.

    Refused here rather than escaped later, because there is no book anywhere
    that needs a package document called `p"q.opf` and no honest reason to
    write one.
    """
    text = value or ""
    if not text.strip("/"):
        if allow_empty:
            return
        raise ValueError(f"{field_name} must not be empty")
    for segment in text.strip("/").split("/"):
        if not segment:
            raise ValueError(f"{field_name}: empty path segment in {value!r}")
        if segment in (".", ".."):
            raise ValueError(f"{field_name}: {segment!r} is not a directory this may write to")
        bad = sorted(set(segment) & _FORBIDDEN_IN_PATH)
        if bad:
            raise ValueError(f"{field_name}: {''.join(bad)!r} cannot appear in {value!r}")
        if len(segment.encode("utf-8")) > 255:
            raise ValueError(f"{field_name}: path segment longer than 255 bytes")


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

    #: Rebuild from a source the reader could not read all of.
    #:
    #: Off, and it is the only setting in this file whose default is chosen
    #: against convenience rather than for it. When an entry of the archive
    #: cannot be read — a monstrous member, a broken stream, a name with no
    #: usable form — the reader says so and the rebuild now stops. Until 0.2.19
    #: it did not: an EPUB whose only chapter exceeded the per-entry limit
    #: produced a file on disk, `succeeded-with-problems`, and no chapter. K1
    #: says no character of the book's text is lost; a rebuild that cannot see
    #: the text cannot keep that promise, and a status nobody reads is not a
    #: warning.
    #:
    #: Turning it on is the owner's standing rule applied to a refusal rather
    #: than to a deletion: the person holding the book gets the last word. It
    #: does not make the loss quiet — the finding stays, at WARN, naming what
    #: went missing.
    allow_incomplete: bool = False

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
        _check_ocf_segment("content_dir", self.content_dir, allow_empty=True)
        _check_ocf_segment("package_name", self.package_name, allow_empty=False)

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
