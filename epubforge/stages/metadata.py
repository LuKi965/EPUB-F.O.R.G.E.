"""Package metadata normalisation to what EPUB 3.3 actually requires."""

from __future__ import annotations

import datetime as dt
import re
import uuid

from ..model import Identifier
from .. import typography
from ..report import Level
from .base import Context, Stage

_BCP47_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y-%m",
    "%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%B %d, %Y",
    "%d %B %Y",
)

_ISBN_RE = re.compile(r"^(?:97[89])?[\d-]{9,17}[\dXx]$")


def normalize_date(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    cleaned = re.sub(r"[+-]\d{2}:?\d{2}$", "", value).replace("Z", "")
    for fmt in _DATE_FORMATS:
        try:
            parsed = dt.datetime.strptime(cleaned.strip(), fmt.replace("Z", ""))
        except ValueError:
            continue
        if fmt == "%Y":
            return parsed.strftime("%Y")
        if fmt == "%Y-%m":
            return parsed.strftime("%Y-%m")
        return parsed.strftime("%Y-%m-%d")
    match = re.search(r"\b(1\d{3}|20\d{2})\b", value)
    return match.group(1) if match else None


def guess_scheme(value: str) -> str | None:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered.startswith("urn:uuid:") or re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", lowered):
        return None  # A UUID needs no scheme declaration.
    if lowered.startswith(("urn:isbn:", "isbn:")) or _ISBN_RE.match(stripped.replace(" ", "")):
        return "ISBN"
    if lowered.startswith("urn:doi:") or lowered.startswith("10."):
        return "DOI"
    return None


class MetadataStage(Stage):
    name = "metadata"

    def run(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        self._titles(ctx)
        self._language(ctx)
        self._identifier(ctx)
        self._dates(ctx)
        self._creators(ctx)

        for key, value in ctx.policy.metadata_overrides.items():
            if key == "title":
                metadata.titles = [value]
            elif key == "language":
                metadata.language = value
            elif key == "author":
                from ..model import Creator

                metadata.creators = [Creator(value, "aut")] + [c for c in metadata.creators if c.role != "aut"]
            elif key == "publisher":
                metadata.publisher = value
            elif key == "series":
                metadata.series = value
            self.note(
                ctx,
                Level.INFO,
                "metadata.override-applied",
                values={"field": key},
                detail=value,
            )

    def _titles(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        metadata.titles = [t.strip() for t in metadata.titles if t and t.strip()]
        if not metadata.titles:
            metadata.titles = ["Untitled"]
            self.note(ctx, Level.WARN, "metadata.title-missing")
        elif len(metadata.titles) > 1:
            # A package may carry several titles, but only the first is the main
            # one. The second becomes the subtitle, which is the ordinary shape
            # of a book with a colon in its name.
            #
            # The rest are kept. They were dropped — `titles = titles[:1]` after
            # taking `extra[0]`, so a book with three `dc:title` elements came
            # out with two and the finding said "3 collapsed", which reads like
            # an accounting of where they went. Nothing needs them gone: EPUB 3
            # allows as many `dc:title` as the publisher wrote, and the one this
            # threw away is the kind a distributor put there — a collection
            # title, a short title, an edition.
            extra = metadata.titles[1:]
            if not metadata.subtitle and extra:
                metadata.subtitle = extra[0]
                extra = extra[1:]
            metadata.titles = metadata.titles[:1] + extra
            self.note(
                ctx,
                Level.FIX,
                "metadata.titles-collapsed",
                values={"count": len(metadata.titles) + (1 if metadata.subtitle else 0)},
            )

    def _language(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        raw = (metadata.language or "").strip().replace("_", "-")
        if raw and _BCP47_RE.match(raw):
            canonical = raw.split("-")[0].lower()
            rest = raw.split("-")[1:]
            metadata.language = "-".join([canonical] + [p.upper() if len(p) == 2 else p for p in rest])
            self._contradicted(ctx, canonical)
            return
        if raw:
            self.note(
                ctx,
                Level.FIX,
                "metadata.language-invalid",
                values={"was": raw, "now": ctx.policy.default_language},
            )
        else:
            self.note(
                ctx,
                Level.WARN,
                "metadata.language-missing",
                values={"now": ctx.policy.default_language},
            )
        metadata.language = ctx.policy.default_language

    #: Characters of the book's own text below which a language rate is
    #: arithmetic rather than evidence. A page of prose is about two thousand.
    ENOUGH_TEXT = 500

    def _contradicted(self, ctx: Context, declared: str) -> None:
        """Correct a declared language the text plainly contradicts.

        Found on a library of 2 200 books: 2 187 declared `en`, and 1 815 of
        those carried `„` — a mark English typesetting does not use at all.
        Calibre had left `dc:language` at its default and nothing had ever
        looked.

        The first version of this only *reported* it, on the argument that
        knowing a declaration is wrong is not the same as knowing the right
        answer. The owner overruled that, and he is right: *if a book declares
        `en` and is plainly written in Polish, then barring English insertions
        the declaration is simply wrong.* Leaving a wrong one in place is not
        neutrality — a reading system speaks `dc:language` to its
        text-to-speech engine and hyphenates by it, so the book is read aloud
        in an English voice and broken across lines by English rules until
        somebody fixes it by hand.

        Narrow on purpose. It fires only where the evidence is decisive: over
        the book's own documents, never the navigation this tool generates,
        never below a page of prose, and only for a language whose letters are
        its own proof. `--language` still wins — the overrides are applied
        after this.
        """
        if declared == "pl":
            return
        text = self._book_text(ctx)
        if len(text) < self.ENOUGH_TEXT or not typography.looks_polish(text):
            return
        ctx.book.metadata.language = "pl"
        self.note(
            ctx,
            Level.FIX,
            "metadata.language-corrected",
            values={
                "was": declared,
                "now": "pl",
                "rate": round(typography.polish_share(text), 1),
            },
        )

    def _book_text(self, ctx: Context) -> str:
        """The book's text, and nothing this tool wrote.

        Markup dilutes the rate and cannot fake it: tag and attribute names are
        ASCII, so they move the denominator and never the numerator. Parsing
        every document twice to be tidier about that would cost a second full
        pass for an answer that does not change.
        """
        parts = []
        for resource in ctx.book.content_docs():
            if resource.path == ctx.book.nav_path:
                continue
            parts.append(resource.data.decode("utf-8", "replace"))
        return "".join(parts)

    def _identifier(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        cleaned: list[Identifier] = []
        seen: set[str] = set()
        for identifier in metadata.identifiers:
            value = identifier.value.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            identifier.value = value
            identifier.scheme = identifier.scheme or guess_scheme(value)
            cleaned.append(identifier)
        metadata.identifiers = cleaned

        if not metadata.identifiers:
            generated = (
                self._derived_identifier(ctx)
                if ctx.policy.reproducible
                else f"urn:uuid:{uuid.uuid4()}"
            )
            metadata.identifiers = [Identifier(generated, None, primary=True)]
            self.note(ctx, Level.FIX, "metadata.identifier-minted", detail=generated)
            return

        if not any(i.primary for i in metadata.identifiers):
            metadata.identifiers[0].primary = True
            self.note(ctx, Level.FIX, "metadata.identifier-promoted")

    @staticmethod
    def _derived_identifier(ctx: Context) -> str:
        """A UUID that is a function of the book rather than of the clock.

        `uuid4` mints a different identifier every run, which makes a book with
        no identifier of its own unreproducible by construction — and the
        identifier is also what font obfuscation is keyed on, so it is not a
        cosmetic difference. UUID version 5 over a digest of every resource
        gives one identifier per set of bytes: the same book twice gets the same
        one, two different books never get the same one, and nothing about the
        machine it ran on gets into it.
        """
        import hashlib

        digest = hashlib.sha256()
        for path in sorted(ctx.book.resources):
            digest.update(path.encode("utf-8"))
            digest.update(hashlib.sha256(ctx.book.resources[path].data).digest())
        return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, digest.hexdigest())}"

    def _pinned_modified(self, ctx: Context) -> str:
        """`dcterms:modified` for a reproducible build.

        The source's own value if it has one — that is a fact about the book and
        it does not move. Failing that the publication date, which is a weaker
        fact and still a fact. Failing both, the epoch, which is the
        reproducible-builds convention and is obviously not a real date: a
        fabricated timestamp that *looked* plausible would be this program
        inventing a fact about somebody's book to keep a promise about bytes.
        """
        for candidate in (ctx.book.metadata.modified, ctx.book.metadata.published):
            if candidate and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", candidate):
                return candidate
        self.note(ctx, Level.INFO, "metadata.modified-pinned-to-epoch")
        return "1970-01-01T00:00:00Z"

    def _dates(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        if metadata.published:
            normalized = normalize_date(metadata.published)
            if normalized != metadata.published:
                if normalized:
                    self.note(
                        ctx,
                        Level.FIX,
                        "metadata.date-normalised",
                        values={"was": metadata.published, "now": normalized},
                    )
                else:
                    self.note(
                        ctx,
                        Level.WARN,
                        "metadata.date-unparseable",
                        values={"was": metadata.published},
                    )
                metadata.published = normalized

        # EPUB 3 requires a dcterms:modified timestamp, to the second, in UTC.
        # It is the one field that is *meant* to differ between two runs on the
        # same input, so it is also the one thing standing between this tool and
        # byte-for-byte reproducible output. Pinning it is therefore a supported
        # choice rather than something to work around.
        if ctx.policy.modified_override:
            metadata.modified = ctx.policy.modified_override
        elif ctx.policy.reproducible:
            metadata.modified = self._pinned_modified(ctx)
        else:
            metadata.modified = dt.datetime.now(dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

    def _creators(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        seen: set[tuple[str, str]] = set()
        cleaned = []
        for creator in metadata.creators:
            name = re.sub(r"\s+", " ", creator.name).strip()
            if not name:
                continue
            key = (name.lower(), creator.role)
            if key in seen:
                continue
            seen.add(key)
            creator.name = name
            if not re.fullmatch(r"[a-z]{3}", creator.role or ""):
                creator.role = "aut"
            if not creator.file_as and "," not in name and " " in name:
                given, _, family = name.rpartition(" ")
                creator.file_as = f"{family}, {given}"
            cleaned.append(creator)
        metadata.creators = cleaned
        if not cleaned:
            self.note(ctx, Level.WARN, "metadata.creator-missing")
