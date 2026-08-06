"""Find which file a reader refuses, by changing one at a time.

When a device opens a publisher's file and refuses ours, and the archive-level
guesses have all been spent — timestamps, attributes, layout, compression —
what is left is the content. This narrows that down without a debugger on the
device, which nobody has.

It works because a container-only rebuild changes almost nothing: on the book
that started the InkBOOK case, 71 of 75 entries come out byte for byte as they
went in. Four do not. So build five files that are *our* archive throughout and
differ from each other in exactly one of those four, and the device answers the
question by opening four of them and refusing one.

    python tools/bisect_reader.py oryginal.epub nasz.epub warianty/

The control matters as much as the rest: an archive written by us but holding
only the original's files. If the device refuses that one too, the fault is in
how we write the archive and none of the other four tell you anything.
"""

from __future__ import annotations

import argparse
import pathlib
import zipfile


def _entries(path: pathlib.Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _order(path: pathlib.Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(path) as archive:
        return archive.infolist()


def differing(original: pathlib.Path, ours: pathlib.Path) -> list[str]:
    """The entries the rebuild did not leave alone, in archive order."""
    before, after = _entries(original), _entries(ours)
    shared = [name for name in _order(ours) if name.filename in before]
    return [
        info.filename
        for info in shared
        if before[info.filename] != after[info.filename]
    ]


def write(destination: pathlib.Path, template: pathlib.Path, contents: dict[str, bytes]) -> None:
    """Write *contents* using *template*'s archive shape — ours, in every variant.

    Keeping the packaging identical across the set is the whole point. A
    variant that differed in two things at once would answer nothing.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as out:
        for info in _order(template):
            entry = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            entry.compress_type = info.compress_type
            entry.create_system = info.create_system
            entry.external_attr = info.external_attr
            out.writestr(entry, contents[info.filename])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", help="the file the device opens")
    parser.add_argument("ours", help="our rebuild of it, which the device refuses")
    parser.add_argument("output", help="where to write the variants")
    args = parser.parse_args()

    original = pathlib.Path(args.original)
    ours = pathlib.Path(args.ours)
    folder = pathlib.Path(args.output)

    changed = differing(original, ours)
    if not changed:
        print("Nothing differs; there is nothing to bisect.")
        return 1

    before, after = _entries(original), _entries(ours)
    if set(before) != set(after):
        print("The two archives do not hold the same entries; rebuild with a")
        print("layout matching the original before bisecting.")
        return 1

    print(f"{len(before)} entries, of which {len(changed)} differ:")
    for name in changed:
        print(f"    {name}")
    print()

    # The control: our archive, the original's files. If the device refuses
    # this, the packaging is the fault and the rest of the set proves nothing.
    write(folder / "K0-tylko-nasze-pakowanie.epub", ours, dict(before))
    print(f"{'K0-tylko-nasze-pakowanie.epub':44s} nasze pakowanie, pliki oryginału")

    for index, name in enumerate(changed, start=1):
        contents = dict(before)
        contents[name] = after[name]
        label = name.rsplit("/", 1)[-1].replace(".", "-")
        destination = folder / f"K{index}-nasz-{label}.epub"
        write(destination, ours, contents)
        print(f"{destination.name:44s} tylko {name} nasze")

    print(
        "\nWgraj wszystkie przez USB, z pominięciem Calibre, i zanotuj, "
        "który się nie otwiera.\nJeżeli nie otwiera się K0 — wina jest w "
        "pakowaniu i reszta niczego nie mówi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
