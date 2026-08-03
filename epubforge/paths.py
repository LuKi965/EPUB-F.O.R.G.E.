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
    decomposed = unicodedata.normalize("NFKD", stem)
    stripped = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = _UNSAFE.sub("-", stripped).strip("-.")
    slug = _DASHES.sub("-", slug)
    if not slug:
        slug = fallback
    ext_slug = _UNSAFE.sub("", unicodedata.normalize("NFKD", ext).encode("ascii", "ignore").decode()).lower()
    return f"{slug}.{ext_slug}" if ext_slug else slug


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
