"""Font handling: undo obfuscation and normalise declared media types.

Obfuscated fonts are keyed on the package's unique identifier. Because the
rebuild may legitimately rewrite that identifier, this stage must run before
metadata normalisation and must use the identifier captured from the source.
"""

from __future__ import annotations

import hashlib
import re

from ..reader import ADOBE_OBFUSCATION, IDPF_OBFUSCATION
from ..report import Level
from .base import Context, Stage

IDPF_PREFIX_LENGTH = 1040
ADOBE_PREFIX_LENGTH = 1024

FONT_SIGNATURES = (
    (b"\x00\x01\x00\x00", "font/ttf"),
    (b"true", "font/ttf"),
    (b"ttcf", "font/collection"),
    (b"OTTO", "font/otf"),
    (b"wOFF", "font/woff"),
    (b"wOF2", "font/woff2"),
)


def idpf_key(identifier: str) -> bytes:
    """SHA-1 of the identifier with all whitespace stripped (OCF 3, §4.3)."""
    normalized = re.sub(r"\s+", "", identifier)
    return hashlib.sha1(normalized.encode("utf-8")).digest()


def adobe_key(identifier: str) -> bytes | None:
    """The 16 raw bytes of the identifier's UUID, or ``None`` if it isn't one."""
    match = re.search(
        r"([0-9a-fA-F]{8})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{12})",
        identifier,
    )
    if not match:
        return None
    return bytes.fromhex("".join(match.groups()))


def deobfuscate(data: bytes, key: bytes, prefix_length: int) -> bytes:
    """XOR the leading bytes with the repeating key; the algorithm is its own inverse."""
    if not key:
        return data
    limit = min(prefix_length, len(data))
    head = bytearray(data[:limit])
    for index in range(limit):
        head[index] ^= key[index % len(key)]
    return bytes(head) + data[limit:]


def sniff_font_type(data: bytes) -> str | None:
    for signature, media_type in FONT_SIGNATURES:
        if data.startswith(signature):
            return media_type
    return None


class FontStage(Stage):
    name = "fonts"

    def run(self, ctx: Context) -> None:
        book = ctx.book
        identifier = book.metadata.primary_identifier
        ctx.original_identifier = identifier.value if identifier else None

        if book.encrypted:
            self._handle_encrypted(ctx)

        for resource in book.resources.values():
            if not resource.is_font and not resource.path.lower().endswith(
                (".ttf", ".otf", ".woff", ".woff2", ".ttc")
            ):
                continue
            sniffed = sniff_font_type(resource.data)
            if sniffed and sniffed != resource.media_type:
                self.note(
                    ctx,
                    Level.FIX,
                    f"corrected font media type to {sniffed} (was {resource.media_type})",
                    rule="font.type-corrected",
                    values={"actual": sniffed, "declared": resource.media_type},
                    location=resource.path,
                )
                resource.media_type = sniffed
            elif not sniffed and resource.is_font:
                self.note(
                    ctx,
                    Level.WARN,
                    "font has no recognisable signature; it may still be obfuscated or corrupt", rule="font.unrecognised",
                    location=resource.path,
                )

    def _handle_encrypted(self, ctx: Context) -> None:
        book = ctx.book
        if book.has_drm:
            self.note(
                ctx,
                Level.ERROR,
                "content is DRM-encrypted; rebuild cannot proceed safely", rule="font.drm",
                detail="Remove DRM with a tool you are licensed to use before running EPUB-Forge.",
            )
            return
        if not ctx.policy.deobfuscate_fonts:
            self.note(ctx, Level.PRESERVED, "font obfuscation left in place by policy", rule="font.obfuscation-kept")
            return

        identifier = ctx.original_identifier
        if not identifier:
            self.note(
                ctx,
                Level.ERROR,
                "fonts are obfuscated but the package has no unique identifier to key on", rule="font.obfuscation-unkeyed",
            )
            return

        recovered = 0
        for path, algorithm in book.encrypted.items():
            resource = book.get(path)
            if resource is None:
                continue
            if algorithm == IDPF_OBFUSCATION:
                plain = deobfuscate(resource.data, idpf_key(identifier), IDPF_PREFIX_LENGTH)
            elif algorithm == ADOBE_OBFUSCATION:
                key = adobe_key(identifier)
                if key is None:
                    self.note(
                        ctx,
                        Level.ERROR,
                        "Adobe-obfuscated font needs a UUID identifier, which this book lacks", rule="font.obfuscation-unkeyed",
                        location=path,
                    )
                    continue
                plain = deobfuscate(resource.data, key, ADOBE_PREFIX_LENGTH)
            else:
                continue

            if sniff_font_type(plain) is None:
                self.note(
                    ctx,
                    Level.ERROR,
                    "deobfuscation did not yield a valid font; leaving the file untouched", rule="font.deobfuscation-failed",
                    location=path,
                    detail="The source identifier likely differs from the one used to obfuscate it.",
                )
                continue
            resource.data = plain
            recovered += 1

        if recovered:
            # encryption.xml is never carried into the output, so the fonts must
            # be plain by the time the writer runs.
            book.encrypted.clear()
            self.note(
                ctx,
                Level.FIX,
                f"deobfuscated {recovered} embedded font(s) and dropped META-INF/encryption.xml",
                rule="font.deobfuscated",
                values={"count": recovered},
                detail="Fonts render identically and the container no longer depends on the identifier.",
            )
