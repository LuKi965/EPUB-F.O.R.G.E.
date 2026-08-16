"""Rebuild policy — the knobs that decide standards-vs-appearance tradeoffs."""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from . import watermark

#: What `Policy.validate_before_publish` may say. Ordered least to most
#: refusing, which is the order they are offered in every interface.
GATES = ("off", "no-new-errors", "clean")

#: What `Policy.render_gate` may say, in the same order: least to most refusing.
RENDER_GATES = ("off", "report", "stop")

#: What `Policy.hyphen_review` may say: how far down the confidence classes
#: the questions go. Ordered least to most asking, like the gates above.
HYPHEN_REVIEWS = ("confirmed", "grouped", "each")

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

    #: What the render check does when it finds a page that lost content.
    #:
    #: F-028, and the owner chose `stop` as the default himself, knowing the
    #: cost: the check adds about thirty-six seconds to a rebuild, and a book it
    #: refuses is a book that has to be looked at.
    #:
    #: * `off` — do not render at all.
    #: * `report` — render, put what it found in the report, publish anyway.
    #: * `stop` — render, and where a page lost content, publish nothing; the
    #:   file already at that name is left exactly as it was.
    #:
    #: Measured across the owner's thirty-two books before this became a
    #: default: zero refusals. Measured with all forty-six of one book's hyphens
    #: joined — the case he asked about, where the text genuinely reflows — 7 of
    #: 130 page comparisons moved at all, the largest by 1.64% of pixels, and
    #: nothing was called a loss. Reflow moves ink; it does not remove it.
    render_gate: str = "stop"
    #: Whether the publication gate asks K1 — is every word of the source still
    #: in the output — before the file takes its name.
    #:
    #: WP-11. `fidelity.text_survives` existed and was reachable only from a
    #: separate command and from the corpus, so the gate that decides whether
    #: somebody's book is written asked the validator and the renderer and did
    #: not ask whether the text was still there. A book can lose a paragraph and
    #: validate perfectly; it can lose one and draw almost the same, because the
    #: page that lost it need not be among the ones sampled.
    #:
    #: On by default, and switchable like every other gate — the owner's rule is
    #: that a choice belongs to him, not to a constant in the code.
    verify_text_survives: bool = True

    #: How many spine documents the render check draws. `0` means all of them.
    #:
    #: Twelve by default and *his* choice of default, with the whole-book option
    #: kept because he asked for it in those words: the person deciding whether
    #: their book survived is entitled to look at all of it rather than at a
    #: sample somebody else picked.
    render_sample: int = 12

    #: Publish even though the appearance check could not be performed at all.
    #:
    #: Not the same setting as `render_gate` and the difference is the whole
    #: reason it exists. `render_gate` says what to do when the check *runs* and
    #: finds a page that lost content. This says what to do when the check
    #: cannot run — no browser on the machine, or a comparison that came back
    #: unavailable — which is a different question with a different answer.
    #:
    #: DELTA-2026-08-15-001 found `stop` publishing in exactly that case, on a
    #: warning. That was this program answering, on somebody's behalf, a
    #: question it had been told to ask: the owner's instruction was that the
    #: verification is mandatory and *may be knowingly declined*, and declining
    #: for him without saying so is not that.
    #:
    #: So with somebody there to ask, the rebuild asks. `True` here is the same
    #: consent given in advance, for the runs where nobody is watching — a
    #: batch over a shelf, a library caller, a machine that will never have a
    #: browser — because "a missing tool must not hold the book hostage" is his
    #: instruction too, and one flag is the price of it.
    accept_unverified_render: bool = False

    #: Publish metadata that came out of a damaged package document without
    #: anybody having looked at it.
    #:
    #: F-004 established that a package which only parsed after tag-soup
    #: recovery yields fields that are *the parser's reading* of somebody's book
    #: rather than the book's own words — crossed tags turned a title into
    #: `ORIGINALpl`, a string no publisher ever wrote. That has been asked about
    #: since the decision queue existed, and DELTA-2026-08-15-001 found the hole
    #: underneath the question: with nobody there to answer, the guess was
    #: published anyway.
    #:
    #: The same shape as `accept_unverified_render`, and deliberately so — one
    #: program, one rule about consent. Somebody who looks at `ORIGINALpl` and
    #: keeps it has decided, and this program has no vote. Silence has not
    #: decided anything, so the default refuses; `True` is that consent given in
    #: advance for a run nobody is watching.
    accept_reconstructed_metadata: bool = False

    #: What to do with hyphen candidates the book itself does not settle.
    #:
    #: BA-2026-001's remaining half, and the numbers decide the shape. Across
    #: the owner's 32 books: 67 `CONFIRMED` — the book writes the word without a
    #: hyphen somewhere else — against 101 `LIKELY` and 88 `UNCERTAIN`, and
    #: reading those two lists, almost every entry is a real compound
    #: (`marksizm-leninizm`, `savoir-vivre`, `ping-pong`).
    #:
    #: * `confirmed` — only the evidenced ones are asked about; the rest are
    #:   counted and reported. The default, and what 0.2.24 did.
    #: * `grouped` — one question per confidence class, carrying the words, so
    #:   189 candidates are one decision instead of 189.
    #: * `each` — every candidate individually, for going through them properly.
    hyphen_review: str = "confirmed"

    #: Read back and write down the answers a person gave about this book.
    #:
    #: BA-2026-002's "save/replay/undo". Kept beside the book, so a library that
    #: moves takes its judgements with it. On by default because the alternative
    #: is being asked the same forty-six questions on every rebuild, which is how
    #: a feature becomes something people switch off — and the store is refused
    #: outright if the book has changed since, so a stale answer cannot be
    #: replayed onto a page nobody has seen.
    remember_decisions: bool = True

    #: Look for hyphens a conversion left inside words, and count them.
    #:
    #: BA-2026-001. On by default because *detecting* changes nothing: the
    #: report gains a line saying how many broken words this book has, and one
    #: book on the owner's shelf has forty-six. Joining any of them takes an
    #: answer from a person — there is no setting that makes this rule act on
    #: its own, which is deliberate and is why the detector may be on.
    detect_hyphens: bool = True

    #: Rewrite absolute font sizes so the reader's own font setting works again.
    #:
    #: EF-029 / WP-13. A book that writes `font-size: 12px` has taken the size
    #: control off the person reading it: on a reader whose default is larger,
    #: that text stays twelve pixels. This is the single most common piece of
    #: print-era formatting on the owner's shelf, and the report now names it
    #: per file whether or not this is on.
    #:
    #: **Off by default**, and the reason is not caution about the units — it is
    #: that this rewrites a stylesheet the publisher wrote. `S-03` says losing an
    #: ornament is damage too, and a house sheet whose sizes were chosen against
    #: each other is an ornament. The conversion below is appearance-identical at
    #: the default reader setting and *deliberately* not identical away from it,
    #: because being adjustable is the entire point; that is a change to somebody
    #: else's book and therefore a decision, not a repair.
    relative_units: bool = False

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

    #: Take out the shop's *visible* leavings too — the order number, the buyer's
    #: name, the address the copy was generated for.
    #:
    #: WP-17 / D-019, and a deliberate reversal of what this program did before.
    #: `watermarks` above governs the opaque token, which nobody was meant to
    #: read; a visible notice was always kept, on the reasoning that a sentence
    #: the buyer is meant to read is the buyer's business. The owner's answer was
    #: that it is his business precisely because he bought the book: *"książki
    #: kupiłem legalnie i mam paragony"*, and the shop's sentence sits in the
    #: running text of Book 1 immediately in front of the novel's first
    #: sentence, where it spoils the page on every reader he owns.
    #:
    #: Separate from `watermarks` rather than a fifth mode of it, because it
    #: answers a different question — that one is *how visible may the token be*,
    #: this one is *may a sentence be deleted* — and folding them together would
    #: make one of the four existing modes silently start removing prose.
    #:
    #: **Off by default and reached by no preset.** This is the only switch in
    #: the program that deletes text somebody can read, so the report lists every
    #: removed sentence verbatim rather than counting them: a number is not
    #: something anybody can check, and this is a person's book.
    remove_shop_notices: bool = False

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
    def for_measurement(cls, name: str = "preserve", **overrides) -> "Policy":
        """A rebuild whose output is going to be thrown away.

        The survey, the fidelity harness and `render-check` all rebuild a book
        into a temporary directory, measure the result and delete it. The two
        gates exist to protect a *destination*, and here there is none — so they
        cost time and can only get in the way.

        This has a name rather than four copies of the same four overrides
        because the owner's own corpus run is what found it. On his machine,
        which has no browser, all 93 books reported `render.cannot-run`; once
        "cannot check" started meaning "do not write", a survey of his library
        would have come back as 93 refusals and no measurements. A tool that
        refuses to look at a library because it cannot verify an output it is
        about to delete is a tool nobody can run — and the same trap was set in
        three other places, which is exactly how many copies of a rule there
        should never be.
        """
        settings = {
            "render_gate": "off",
            "accept_unverified_render": True,
            "accept_reconstructed_metadata": True,
            "validate_before_publish": "off",
        }
        settings.update(overrides)
        return cls.preset(name, **settings)

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
