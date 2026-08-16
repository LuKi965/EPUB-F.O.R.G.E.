"""H.1's two absent rows: fuzz, and properties that must hold for any input.

The audit's test-gap table marks **Fuzz: ABSENT** and **Property-based: ABSENT**,
and it is right that neither existed. Everything else in this suite asks "does
this book come out correctly" about a book somebody wrote on purpose. Nothing
asked the other question: *what does this program do when handed something
nobody wrote on purpose.*

There is no Hypothesis here, and that is a decision rather than a shortcut. This
project's dependencies are locked with hashes for a Windows release build, and a
test-only dependency that must be resolved on the runner is a real cost against
a generator that fits in forty lines. The mutations are drawn from a fixed seed
so a failure is reproducible by its seed number, which is most of what a
shrinking engine buys here.

**What is asserted is a property, not an output.** For a damaged archive there
is no correct book, so demanding one would be nonsense. What must hold for
*every* input, correct or not:

1. It does not raise. A crash is the one outcome that tells a person nothing.
2. It does not write a file it then calls a failure — no half-book on disk.
3. It answers. A hang is worse than a refusal, because a batch of a thousand
   stops at the ninth.
4. What it does write, it can read back.
"""

from __future__ import annotations

import io
import os
import random
import time
import warnings
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import make_modern_epub

#: How many mutations to run. Small enough for every test run, large enough to
#: reach each mutation kind several times; the nightly value belongs in CI.
ROUNDS = 60

#: Fixed, so a failure names the seed that produced it and can be re-run.
SEED = 20260813

#: What every mutated archive is stamped with. The generator's output has to be
#: a function of the seed and of nothing else — see `_mutations`.
FROZEN_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def _mutations(data: bytes, rng: random.Random) -> bytes:
    """One damaged archive, by one of the ways archives are damaged.

    Every kind here has been seen on a real book except the deliberate
    truncations, which are what a failed download leaves.
    """
    kind = rng.choice(
        [
            "truncate",
            "flip",
            "drop-entry",
            "rename-entry",
            "empty-entry",
            "corrupt-xml",
            "duplicate-entry",
            "junk-prefix",
        ]
    )
    if kind == "truncate":
        return data[: rng.randrange(1, len(data))]
    if kind == "flip":
        position = rng.randrange(len(data))
        return data[:position] + bytes([data[position] ^ (1 << rng.randrange(8))]) + data[position + 1 :]
    if kind == "junk-prefix":
        return bytes(rng.randrange(256) for _ in range(rng.randrange(1, 64))) + data

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = [(name, archive.read(name)) for name in archive.namelist()]
    except Exception:  # noqa: BLE001 — already damaged beyond reading
        return data

    if kind == "drop-entry" and len(entries) > 1:
        entries.pop(rng.randrange(len(entries)))
    elif kind == "rename-entry" and entries:
        index = rng.randrange(len(entries))
        name, payload = entries[index]
        entries[index] = (name + rng.choice([".bak", "%2F", "#", " ", "ł"]), payload)
    elif kind == "empty-entry" and entries:
        index = rng.randrange(len(entries))
        entries[index] = (entries[index][0], b"")
    elif kind == "corrupt-xml":
        candidates = [i for i, (name, _) in enumerate(entries) if name.endswith((".xhtml", ".opf", ".xml"))]
        if candidates:
            index = rng.choice(candidates)
            name, payload = entries[index]
            cut = rng.randrange(1, max(2, len(payload)))
            entries[index] = (name, payload[:cut] + b"<<>&nie-encja;")
    elif kind == "duplicate-entry" and entries:
        entries.append(entries[rng.randrange(len(entries))])

    buffer = io.BytesIO()
    with warnings.catch_warnings():
        # `duplicate-entry` writes a name twice on purpose — an archive real
        # tools do produce — and zipfile says so every time. Silenced here
        # rather than suite-wide: a warning nobody reads is a warning that will
        # be missed when it matters.
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries:
                # A fixed timestamp, because a test below compares whole
                # archives byte for byte and calls the generator repeatable.
                # `writestr` with a bare name stamps each entry with the clock,
                # so "the same seed produces the same bytes" was true only while
                # both runs fell inside one two-second DOS tick — the archive
                # format's resolution. It passed nearly always, which is the bad
                # kind of nearly: a real loss of repeatability would have looked
                # exactly like the flake everyone had learned to re-run.
                entry = zipfile.ZipInfo(name, date_time=FROZEN_TIMESTAMP)
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, payload)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def seed_book(tmp_path_factory) -> bytes:
    room = tmp_path_factory.mktemp("fuzz")
    return open(make_modern_epub(str(room / "seed.epub")), "rb").read()


class TestNothingHandedToItCanMakeItCrash:
    """The property, over sixty deliberately damaged archives."""

    def test_the_rebuild_answers_for_every_mutation(self, tmp_path, seed_book):
        rng = random.Random(SEED)
        for round_number in range(ROUNDS):
            damaged = _mutations(seed_book, rng)
            source = tmp_path / f"fuzz-{round_number}.epub"
            source.write_bytes(damaged)
            destination = str(tmp_path / f"out-{round_number}.epub")

            started = time.monotonic()
            try:
                result = rebuild(str(source), destination, Policy.preset("preserve"))
            except Exception as exc:  # noqa: BLE001 — that is the finding
                raise AssertionError(
                    f"round {round_number} (seed {SEED}) raised {type(exc).__name__}: {exc}"
                ) from exc
            elapsed = time.monotonic() - started

            assert elapsed < 60, (
                f"round {round_number} took {elapsed:.0f}s — a batch of a thousand "
                f"stops at the ninth"
            )
            # A status that says nothing was written, with a file on disk, is
            # the shape of defect this program exists against.
            if not result.status.wrote_a_file:
                assert not os.path.exists(destination), (
                    f"round {round_number}: {result.status.value} and yet a file appeared"
                )
            else:
                assert os.path.getsize(destination) > 0

    def test_whatever_it_writes_it_can_read_back(self, tmp_path, seed_book):
        """Property 4, and the one that catches a rebuild that succeeded into
        nonsense rather than failing honestly."""
        from epubforge import pipeline

        rng = random.Random(SEED + 1)
        checked = 0
        for round_number in range(ROUNDS):
            source = tmp_path / f"read-{round_number}.epub"
            source.write_bytes(_mutations(seed_book, rng))
            destination = str(tmp_path / f"out-{round_number}.epub")
            result = rebuild(str(source), destination, Policy.preset("preserve"))
            if not result.status.wrote_a_file:
                continue
            checked += 1
            assert not pipeline._reread(destination), (
                f"round {round_number}: written and not readable again"
            )
        assert checked, "no mutation survived to be rebuilt — the generator is too violent"

    @pytest.mark.parametrize("mode", ["preserve", "strict", "minimal"])
    def test_every_mode_holds_the_same_properties(self, tmp_path, seed_book, mode):
        rng = random.Random(SEED + 2)
        for round_number in range(20):
            source = tmp_path / f"{mode}-{round_number}.epub"
            source.write_bytes(_mutations(seed_book, rng))
            destination = str(tmp_path / f"{mode}-out-{round_number}.epub")
            result = rebuild(str(source), destination, Policy.preset(mode))
            if not result.status.wrote_a_file:
                assert not os.path.exists(destination)


class TestTheGeneratorItself:
    """A fuzzer that produces nothing interesting passes everything."""

    def test_it_produces_something_different_every_round(self, seed_book):
        rng = random.Random(SEED)
        produced = {_mutations(seed_book, rng) for _ in range(20)}
        assert len(produced) >= 15, "the mutations are barely mutating"

    def test_and_the_seed_makes_it_repeatable(self, seed_book):
        first = [_mutations(seed_book, random.Random(SEED)) for _ in range(3)]
        second = [_mutations(seed_book, random.Random(SEED)) for _ in range(3)]
        assert first == second

    def test_repeatable_across_a_clock_tick_and_not_only_within_one(self, seed_book):
        """The claim above, asked properly.

        It compared two runs a microsecond apart, and the archive timestamp has
        a two-second resolution — so it agreed for the same reason a stopped
        clock agrees with itself. Both halves of a real failure, an entry
        stamped from the wall clock and a run straddling a tick, fell in the gap
        between the assertion and what it meant to assert.
        """
        import time

        first = _mutations(seed_book, random.Random(SEED))
        time.sleep(2.1)
        assert _mutations(seed_book, random.Random(SEED)) == first

    def test_nothing_in_a_mutated_archive_is_stamped_from_the_clock(self, seed_book):
        produced = _mutations(seed_book, random.Random(SEED))
        with zipfile.ZipFile(io.BytesIO(produced)) as archive:
            stamps = {entry.date_time for entry in archive.infolist()}
        assert stamps <= {FROZEN_TIMESTAMP}, stamps

    def test_some_mutations_still_rebuild(self, tmp_path, seed_book):
        """Both halves matter. A generator that only produces garbage tests the
        refusal path and never the one where a damaged book is repaired."""
        rng = random.Random(SEED)
        survived = 0
        for round_number in range(20):
            source = tmp_path / f"s-{round_number}.epub"
            source.write_bytes(_mutations(seed_book, rng))
            result = rebuild(
                str(source), str(tmp_path / f"s-out-{round_number}.epub"), Policy.preset("preserve")
            )
            survived += result.status.wrote_a_file
        assert 1 <= survived < 20, f"{survived}/20 rebuilt — that is not a spread"


class TestPropertiesOfTheParts:
    """Property-based in the small: functions whose contract is a statement
    about *all* inputs, checked over generated ones rather than three examples."""

    def test_a_container_path_never_escapes_the_container(self):
        from epubforge import ocf

        rng = random.Random(SEED)
        alphabet = "ab/.%\\:#? ł\0"
        for _ in range(500):
            raw = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 24)))
            name = ocf.canonical(raw)
            if name.rejected:
                continue
            assert not name.path.startswith("/")
            assert ".." not in name.path.split("/")
            assert "\\" not in name.path
            assert "\0" not in name.path

    def test_resolving_a_reference_never_escapes_it_either(self):
        from epubforge import paths

        rng = random.Random(SEED + 3)
        alphabet = "ab/.%#?~ł"
        for _ in range(500):
            href = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 20)))
            resolved = paths.resolve("EPUB/text/ch.xhtml", href)
            if resolved is None:
                continue
            assert not resolved.startswith("/")
            assert not resolved.startswith("..")

    def test_a_slug_is_always_usable_as_a_filename(self):
        from epubforge import paths

        rng = random.Random(SEED + 4)
        alphabet = "aĄ/.\\:*?\"<>| łж漢"
        for _ in range(500):
            name = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 20)))
            slug = paths.ascii_slug(name)
            assert slug
            assert not set(slug) & set('/\\:*?"<>|')
            assert slug.isascii()
