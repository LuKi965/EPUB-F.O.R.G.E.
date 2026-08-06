"""Image normalisation: correct mistyped files and transcode non-core formats.

EPUB 3 readers are only required to support JPEG, PNG, GIF and SVG. WebP, BMP
and TIFF appear in the wild and render on some devices but not others, so they
are converted rather than trusted.
"""

from __future__ import annotations

import io

from ..model import guess_media_type
from ..policy import CORE_IMAGE_TYPES
from ..report import Level
from .base import Context, Stage

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - Pillow is a hard dependency in practice
    PIL_AVAILABLE = False

PIL_FORMAT_TO_MEDIA = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}

EXTENSION_FOR = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/svg+xml": "svg",
}


class ImageStage(Stage):
    name = "images"

    def run(self, ctx: Context) -> None:
        if not PIL_AVAILABLE:
            self.note(
                ctx,
                Level.WARN,
                "Pillow is unavailable; images passed through unchecked",
                rule="image.pillow-unavailable",
            )
            return

        for resource in list(ctx.book.resources.values()):
            if not resource.is_image or resource.media_type == "image/svg+xml":
                continue
            self._inspect(ctx, resource)

    def _inspect(self, ctx: Context, resource) -> None:
        try:
            with Image.open(io.BytesIO(resource.data)) as image:
                actual_format = image.format
                image.verify()
        except Exception as exc:
            self.note(
                ctx,
                Level.ERROR,
                f"image is unreadable and was kept as-is: {type(exc).__name__}",
                rule="image.unreadable",
                values={"error": type(exc).__name__},
                location=resource.path,
            )
            return

        actual_media = PIL_FORMAT_TO_MEDIA.get(actual_format or "", resource.media_type)
        if actual_media != resource.media_type:
            self.note(
                ctx,
                Level.FIX,
                f"file is really {actual_media} though it was declared {resource.media_type}",
                rule="image.type-corrected",
                values={"actual": actual_media, "declared": resource.media_type},
                location=resource.path,
            )
            resource.media_type = actual_media

        if resource.media_type in CORE_IMAGE_TYPES:
            self._fix_extension(ctx, resource)
            return

        if not ctx.policy.transcode_images:
            self.note(
                ctx,
                Level.PRESERVED,
                f"{resource.media_type} is not a core EPUB 3 type but was kept by policy",
                rule="image.type-kept",
                values={"media_type": resource.media_type},
                location=resource.path,
            )
            return

        self._transcode(ctx, resource)

    def _fix_extension(self, ctx: Context, resource) -> None:
        expected = EXTENSION_FOR.get(resource.media_type)
        if not expected:
            return
        current = resource.path.rpartition(".")[2].lower()
        if current == expected or (expected == "jpg" and current in {"jpeg", "jpe"}):
            return
        new_path = f"{resource.path.rpartition('.')[0] or resource.path}.{expected}"
        if new_path in ctx.book.resources:
            return
        ctx.book.rename(resource.path, new_path)
        self.note(ctx, Level.FIX, f"renamed to match its real format (.{expected})",
            rule="image.renamed",
            values={"suffix": expected}, location=new_path)

    def _transcode(self, ctx: Context, resource) -> None:
        try:
            with Image.open(io.BytesIO(resource.data)) as image:
                has_alpha = image.mode in ("RGBA", "LA", "P") and "transparency" in image.info
                target_mode = "RGBA" if has_alpha or image.mode in ("RGBA", "LA") else "RGB"
                converted = image.convert(target_mode)
                buffer = io.BytesIO()
                converted.save(buffer, format="PNG", optimize=True)
        except Exception as exc:
            self.note(
                ctx,
                Level.ERROR,
                f"could not transcode to PNG, keeping the original: {type(exc).__name__}",
                rule="image.transcode-failed",
                values={"error": type(exc).__name__},
                location=resource.path,
            )
            return

        old_path = resource.path
        old_type = resource.media_type
        resource.data = buffer.getvalue()
        resource.media_type = "image/png"
        stem = old_path.rpartition(".")[0] or old_path
        new_path = f"{stem}.png"
        counter = 2
        while new_path in ctx.book.resources and new_path != old_path:
            new_path = f"{stem}-{counter}.png"
            counter += 1
        ctx.book.rename(old_path, new_path)
        self.note(
            ctx,
            Level.FIX,
            f"transcoded {old_type} to PNG for universal reader support",
            rule="image.transcoded",
            values={"media_type": old_type, "was": old_path},
            location=new_path,
            detail=f"was {old_path}",
        )
