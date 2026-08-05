"""Container-path arithmetic.

Every resource in the in-memory model is keyed by its container-absolute POSIX
path (``EPUB/text/ch1.xhtml``), never by an OPF-relative one. Hrefs found in
source files are relative and percent-encoded; these helpers move between the
two representations so no other module has to think about it.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit

REMOTE_SCHEMES = ("http:", "https:", "ftp:", "mailto:", "tel:", "data:", "file:")

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_DASHES = re.compile(r"-{2,}")

#: Letters with no canonical decomposition, which NFKD therefore leaves whole
#: and the ASCII encoder then drops without trace: `okładka.png` became
#: `okadka.png`. Applied *before* normalisation, so the rest still works the
#: usual way. Polish `ł` is the one that matters here; the others are the same
#: defect in other alphabets and cost nothing to cover.
_TRANSLITERATION = str.maketrans(
    {
        "ł": "l", "Ł": "L",
        "đ": "d", "Đ": "D",
        "ø": "o", "Ø": "O",
        "æ": "ae", "Æ": "AE",
        "œ": "oe", "Œ": "OE",
        "ß": "ss",
        "þ": "th", "Þ": "Th",
        "ð": "d", "Ð": "D",
        "ı": "i", "İ": "I",
        "ħ": "h", "Ħ": "H",
        "ŋ": "n", "Ŋ": "N",
        "ĸ": "k",
        "ŧ": "t", "Ŧ": "T",
    }
)


def is_remote(href: str) -> bool:
    lowered = href.strip().lower()
    return any(lowered.startswith(scheme) for scheme in REMOTE_SCHEMES) or lowered.startswith("//")


def split_fragment(href: str) -> tuple[str, str]:
    """Return ``(path_part, fragment_with_hash_or_empty)``."""
    parts = urlsplit(href)
    path = parts.path
    if parts.query:
        path = f"{path}?{parts.query}"
    return path, (f"#{parts.fragment}" if parts.fragment else "")


def resolve(base_file: str, href: str) -> str | None:
    """Resolve *href*, as written inside *base_file*, to a container path.

    Returns ``None`` for remote or non-resolvable references so callers can
    treat them as "leave alone" without a second check.
    """
    if not href or is_remote(href) or href.startswith("#"):
        return None
    path, _ = split_fragment(href)
    if not path:
        return None
    decoded = unquote(path)
    base_dir = posixpath.dirname(base_file)
    joined = posixpath.normpath(posixpath.join(base_dir, decoded))
    # normpath can escape the container root on malformed input (../../x).
    if joined.startswith("..") or joined.startswith("/"):
        joined = joined.lstrip("./")
    return joined


def relative(from_file: str, to_path: str) -> str:
    """Build the percent-encoded href pointing at *to_path* from *from_file*."""
    from_dir = posixpath.dirname(from_file)
    rel = posixpath.relpath(to_path, from_dir or ".")
    return quote(rel, safe="/-_.~!$&'()*+,;=:@")


def ascii_slug(name: str, fallback: str = "file") -> str:
    """Fold a filename to a portable ASCII slug, preserving the extension.

    Non-Latin scripts frequently transliterate to nothing; the *fallback* keeps
    those files addressable rather than dropping them.
    """
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    slug = _fold(stem)
    slug = _UNSAFE.sub("-", slug).strip("-.")
    slug = _DASHES.sub("-", slug)
    if not slug:
        slug = fallback
    ext_slug = _UNSAFE.sub("", _fold(ext)).lower()
    return f"{slug}.{ext_slug}" if ext_slug else slug


def _fold(text: str) -> str:
    """Transliterate what NFKD cannot decompose, then fold the rest to ASCII."""
    return (
        unicodedata.normalize("NFKD", text.translate(_TRANSLITERATION))
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def unique(candidate: str, taken: set[str]) -> str:
    """Disambiguate *candidate* against *taken* by appending ``-2``, ``-3``, ..."""
    if candidate not in taken:
        return candidate
    stem, dot, ext = candidate.rpartition(".")
    if not dot:
        stem, ext = candidate, ""
    counter = 2
    while True:
        probe = f"{stem}-{counter}.{ext}" if ext else f"{stem}-{counter}"
        if probe not in taken:
            return probe
        counter += 1


def content_path(policy, name: str) -> str:
    """A path inside the content directory, which may be the archive root.

    `f"{policy.content_dir.strip('/')}/{name}"` produces "/nav.xhtml" when the
    directory is empty — a leading slash, and not a container path at all.
    """
    directory = policy.content_dir.strip("/")
    return f"{directory}/{name}" if directory else name
