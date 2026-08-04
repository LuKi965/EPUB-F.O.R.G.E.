"""Package metadata normalisation to what EPUB 3.3 actually requires."""

from __future__ import annotations

import datetime as dt
import re
import uuid

from ..model import Identifier
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
            self.note(ctx, Level.INFO, f"applied caller override for {key}", detail=value)

    def _titles(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        metadata.titles = [t.strip() for t in metadata.titles if t and t.strip()]
        if not metadata.titles:
            metadata.titles = ["Untitled"]
            self.note(
                ctx,
                Level.WARN,
                "no dc:title in the source; inserted a placeholder",
                detail="Pass --title to set the real one.",
            )
        elif len(metadata.titles) > 1:
            # A package may carry several titles, but only the first is the
            # main one; the rest become subtitles rather than being dropped.
            extra = metadata.titles[1:]
            metadata.titles = metadata.titles[:1]
            if not metadata.subtitle and extra:
                metadata.subtitle = extra[0]
            self.note(ctx, Level.FIX, f"collapsed {len(extra) + 1} dc:title elements to one main title")

    def _language(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        raw = (metadata.language or "").strip().replace("_", "-")
        if raw and _BCP47_RE.match(raw):
            canonical = raw.split("-")[0].lower()
            rest = raw.split("-")[1:]
            metadata.language = "-".join([canonical] + [p.upper() if len(p) == 2 else p for p in rest])
            return
        if raw:
            self.note(
                ctx,
                Level.FIX,
                f"language tag {raw!r} is not valid BCP 47; replaced with {ctx.policy.default_language!r}",
            )
        else:
            self.note(
                ctx,
                Level.WARN,
                f"no dc:language in the source; defaulted to {ctx.policy.default_language!r}",
            )
        metadata.language = ctx.policy.default_language

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
            generated = f"urn:uuid:{uuid.uuid4()}"
            metadata.identifiers = [Identifier(generated, None, primary=True)]
            self.note(
                ctx,
                Level.FIX,
                "no dc:identifier in the source; minted a UUID",
                detail=generated,
            )
            return

        if not any(i.primary for i in metadata.identifiers):
            metadata.identifiers[0].primary = True
            self.note(ctx, Level.FIX, "package declared no unique-identifier; promoted the first one")

    def _dates(self, ctx: Context) -> None:
        metadata = ctx.book.metadata
        if metadata.published:
            normalized = normalize_date(metadata.published)
            if normalized != metadata.published:
                if normalized:
                    self.note(
                        ctx,
                        Level.FIX,
                        f"normalised dc:date to ISO 8601: {metadata.published!r} -> {normalized!r}",
                    )
                else:
                    self.note(ctx, Level.WARN, f"could not parse dc:date {metadata.published!r}; dropped it")
                metadata.published = normalized

        # EPUB 3 requires a dcterms:modified timestamp, to the second, in UTC.
        # It is the one field that is *meant* to differ between two runs on the
        # same input, so it is also the one thing standing between this tool and
        # byte-for-byte reproducible output. Pinning it is therefore a supported
        # choice rather than something to work around.
        metadata.modified = ctx.policy.modified_override or dt.datetime.now(
            dt.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

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
            self.note(ctx, Level.WARN, "no dc:creator in the source")
