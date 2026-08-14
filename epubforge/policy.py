"""Rebuild policy — the knobs that decide standards-vs-appearance tradeoffs."""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from . import watermark

#: What `Policy.validate_before_publish` may say. Ordered least to most
#: refusing, which is the order they are offered in every interface.
GATES = ("off", "no-new-errors", "clean")

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

    #: Refuse a book this machine is not expected to have the memory for.
    #:
    #: EF-020, after the benchmark it asked for. The reader's ceiling of 2 GiB
    #: of content is not a memory bound: text costs about twelve times its own
    #: size once it is an element tree, so that ceiling permits a process of
    #: twenty-four gigabytes. Between the two numbers the outcome is not a
    #: refusal but a kill — no report, no diagnosis, nothing to act on.
    #:
    #: On by default because the alternative default is that outcome. A switch
    #: because the estimate is a model: it is built from six books, it is
    #: deliberately 15% pessimistic, and the person in front of the machine
    #: knows things it does not — that the batch is the only thing running, that
    #: there is swap, that this book is unlike those six.
    check_memory: bool = True

    #: A fixed memory budget in bytes, instead of asking the machine.
    #:
    #: For somebody who wants the answer not to depend on what else happened to
    #: be running that minute — and for the tests, which otherwise measure the
    #: container rather than the program.
    memory_limit: "int | None" = None

    #: Remove files present in the archive but referenced by nothing.
    #:
    #: Off by default since 0.1.7. The three gaps that kept it off — `srcset`,
    #: `<picture><source srcset>` and references made from inside an SVG — are
    #: closed, and it stays off anyway. The graph is *better* and it is not
    #: complete: a script that builds a filename from two strings, a stylesheet
    #: reached only through a media query this program does not evaluate, a
    #: reference in a file type nobody here models. Every one of those is a
    #: picture somebody is still looking at, against a saving of a few kilobytes
    #: — and the trade has never been close.
    drop_orphans: bool = False

    #: Delete what the archive picked up on the way out of somebody's machine:
    #: `.DS_Store`, `Thumbs.db`, `__MACOSX/`, AppleDouble `._` shadows,
    #: `iTunesMetadata.plist`, `calibre_bookmarks.txt`, `.bak`.
    #:
    #: On, because none of it belongs in a publication and a reading system that
    #: opens the book has to skip it too. A switch all the same, and one that had
    #: to be argued for rather than assumed: this was the last thing in the
    #: program that deleted a file by *name*, with no test of whether the book
    #: used it, and `.bak` is a name a publisher can give a chapter. The removal
    #: now proves the file is unreferenced first; the switch is the owner's
    #: standing rule, which does not have exceptions for things that look
    #: obvious.
    remove_junk: bool = True

    # `allow_incomplete` used to live here: "rebuild from a source the reader
    # could not read all of". It is gone, by the owner's decision of 2026-08-14,
    # and the argument is worth keeping because it is the argument for the whole
    # program.
    #
    # The 2026-08-14 baseline reproduced it: switch on, one chapter unreadable,
    # and out came a file called `book.epub` with `succeeded-with-problems` and
    # no chapter in it. The defence written here was that the switch is a
    # deliberate one and the loss is in the report — which is the shape of
    # argument this project does not accept anywhere else.
    #
    # The owner's reasoning went past mine. My first proposal was to keep the
    # switch for losses that are "only" a font or a decorative image, on the
    # grounds that the text survives. His answer: *"Utrata ozdobnika to również
    # uszkodzenie książki i przeczy logice aplikacji, którą tworzymy."* He is
    # right. A program whose one promise is that the book still looks like
    # itself does not get to publish a book quietly missing its ornament.
    #
    # So: **any entry of the source that did not reach the model blocks the
    # rebuild.** There is no setting. What replaces the switch is a report worth
    # reading — see `_diagnose_losses` in `pipeline.py` — because the real fix
    # for a damaged source is a clean copy of it, and this program's job is to
    # say precisely what is damaged so somebody can go and get one.

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

    #: Produce the same bytes every time this book is rebuilt.
    #:
    #: The audit's F-022, and the reason it was filed as "did not reproduce":
    #: the *mechanism* was already here — every ZIP entry carries a fixed
    #: timestamp and `modified_override` pins the one field that moves — but
    #: there was no way to *ask for* a reproducible build. A mechanism nobody
    #: can switch on is not a feature; it is a thing the author knows.
    #:
    #: Two things move between runs and this pins both. `dcterms:modified` is
    #: taken from the source rather than from the clock. And a book with no
    #: identifier at all had one minted with `uuid4`, which is a different book
    #: every time; under this it is derived from the content, so the same input
    #: gets the same identifier and two different books never collide.
    #:
    #: Off by default because the honest `dcterms:modified` for a file produced
    #: now is now. This is for comparing two builds, for a corpus measurement,
    #: and for anybody who wants to check that what they downloaded is what the
    #: source produces.
    reproducible: bool = False

    #: Ask EPUBCheck **before** the file is published, and refuse on the answer.
    #:
    #: The audit's K.2 invariant 12, and the only one of the fourteen left
    #: unimplemented. The argument against it was cost: a JVM per book, a few
    #: seconds each. That argument is gone — the JVM was never the cost, and one
    #: held open validates eight books in 8.4 s instead of 35.3 s.
    #:
    #: Three settings, because two would force a bad choice:
    #:
    #: ``"off"``
    #:     Validate if somebody asks, after the fact, and report. What this
    #:     program did until now.
    #: ``"no-new-errors"``
    #:     Refuse to publish if the rebuild carries an EPUBCheck error the
    #:     source did not already have — this program may carry a publisher's
    #:     defect, but not add one of its own. Costs a second validation, the
    #:     source's, which is why it needed the shared JVM to be reasonable.
    #:
    #:     **Read the answer knowing what it compares.** A 2.0 source is judged
    #:     by EPUB 2 rules and a 3.3 rebuild by EPUB 3 rules, so "new" here can
    #:     also mean "EPUB 3 has a rule EPUB 2 did not". Tried as the preserve
    #:     default and withdrawn within the hour: a chapter linking to a file
    #:     the book does not contain passes as EPUB 2, fails as EPUB 3, and
    #:     arrived that way from the publisher. The report names the source's
    #:     version alongside the refusal so the difference is visible rather
    #:     than inferred.
    #: ``"clean"``
    #:     Refuse to publish anything EPUBCheck calls an error, whoever made it.
    #:     The literal invariant, and the default in `strict` — a strict mode
    #:     that publishes an invalid file is not strict. Wrong as a general
    #:     default for the same reason as above: it refuses most real books over
    #:     defects they arrived with.
    #:
    #: **When the validator is missing**, `"clean"` refuses and `"no-new-errors"`
    #: warns. That asymmetry is deliberate rather than a compromise: `"clean"` is
    #: an absolute claim about the file, and a claim nobody checked is not a
    #: claim — passing it would be the 0.2.19 fail-open defect wearing a gate's
    #: name. `"no-new-errors"` is a *comparison*, and with no validator there is
    #: no comparison to make; the invariant gate, the read-back and the
    #: fidelity checks still ran, so the file is not unexamined.
    validate_before_publish: str = "off"

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
        # Same reasoning as above, and it matters more here: a misspelt gate
        # setting would mean "no gate", which is the one outcome that looks like
        # everything is fine.
        if self.validate_before_publish not in GATES:
            raise ValueError(
                f"unknown validation gate: {self.validate_before_publish!r} "
                f"(expected one of {', '.join(GATES)})"
            )
        _check_ocf_segment("content_dir", self.content_dir, allow_empty=True)
        _check_ocf_segment("package_name", self.package_name, allow_empty=False)

    @classmethod
    def preset(cls, name: str, **overrides) -> "Policy":
        if name == "strict":
            # Strict already refuses a book over a reference it cannot resolve.
            # Refusing one EPUBCheck calls invalid is the same posture, and a
            # strict mode that publishes an invalid file is not strict.
            base = cls(
                strict=True,
                strip_scripts=False,
                remove_dead=True,
                validate_before_publish="clean",
            )
        elif name == "preserve":
            # Not gated, and that is preserve's whole promise rather than a
            # concession. Measured on the suite's own fixtures the moment the
            # gate went in: a book referencing a file it does not contain is
            # invalid EPUB 3, was tolerated as EPUB 2, and arrives that way from
            # the publisher. Preserve exists to publish that book with the
            # defect intact and the report saying so.
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
        # A name that is not a field is refused rather than set. `setattr` on a
        # plain object takes anything, so `Policy.preset("preserve", strickt=True)`
        # used to produce a policy that was not strict and said nothing — and
        # after `allow_incomplete` was removed, every caller still passing it
        # would have gone on believing the setting existed. A misspelt setting
        # that silently means "the default" is the quietest way for a program to
        # do something other than what it was told.
        known = {field.name for field in fields(base)}
        unknown = sorted(set(overrides) - known)
        if unknown:
            raise TypeError(
                f"Policy has no setting called {', '.join(repr(name) for name in unknown)}"
            )
        for key, value in overrides.items():
            setattr(base, key, value)
        # The overrides go on after construction, so they have not been checked
        # yet; checking again costs nothing and closes the gap.
        base.__post_init__()
        return base
