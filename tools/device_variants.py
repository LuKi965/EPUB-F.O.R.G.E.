"""Rebuild the archive-level variants used to bisect a reader that refuses a book.

When a device rejects a file that EPUBCheck passes, the fault is not in the
specification — it is in some property the specification leaves free and the
reader does not. There are only a handful of those at the archive level, and
this produces one file per property so a human with the device can bisect them.

The variants change nothing a reader is supposed to see: same entries, same
bytes, same order. Only the ZIP metadata and the compression method move.

    python tools/device_variants.py book.epub warianty/

Each output keeps `mimetype` first and stored, because that is required.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import time
import zipfile

#: Every variant, and the one thing it changes relative to the input.
VARIANTS = {
    "E-realne-daty": "real modification times instead of the fixed 1980-01-01",
    "F-daty-i-atrybuty": "E, plus the regular-file bit in the Unix mode",
    "G-wszystko-skompresowane": "every entry deflated, the way Calibre writes them",
    "H-katalogi": "explicit directory entries, which Calibre emits and we do not",
}


def _rewrite(source: str, destination: str, variant: str) -> None:
    now = time.localtime()[:6]
    with zipfile.ZipFile(source) as reader, zipfile.ZipFile(destination, "w") as writer:
        seen_directories: set[str] = set()
        for info in reader.infolist():
            data = reader.read(info.filename)
            entry = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            entry.create_system = info.create_system
            entry.external_attr = info.external_attr
            entry.compress_type = info.compress_type

            if variant in ("E-realne-daty", "F-daty-i-atrybuty"):
                entry.date_time = now
            if variant == "F-daty-i-atrybuty":
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
            if variant == "G-wszystko-skompresowane" and info.filename != "mimetype":
                entry.compress_type = zipfile.ZIP_DEFLATED
            if variant == "H-katalogi":
                parts = info.filename.split("/")[:-1]
                for depth in range(len(parts)):
                    directory = "/".join(parts[: depth + 1]) + "/"
                    if directory in seen_directories:
                        continue
                    seen_directories.add(directory)
                    folder = zipfile.ZipInfo(directory, date_time=info.date_time)
                    folder.external_attr = (stat.S_IFDIR | 0o755) << 16 | 0x10
                    writer.writestr(folder, b"")

            writer.writestr(entry, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="an EPUB the device refuses")
    parser.add_argument("output", help="directory to write the variants into")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.source))[0]

    control = os.path.join(args.output, f"0-bez-zmian-{base}.epub")
    shutil.copy2(args.source, control)
    print(f"{os.path.basename(control):44s}  control — the file as it is")

    for variant, description in VARIANTS.items():
        destination = os.path.join(args.output, f"{variant}-{base}.epub")
        _rewrite(args.source, destination, variant)
        print(f"{os.path.basename(destination):44s}  {description}")

    print(
        "\nCopy all of them to the device over USB, not through Calibre, and note "
        "which open.\nWithout the control file a device fault cannot be told from "
        "a tool fault."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
