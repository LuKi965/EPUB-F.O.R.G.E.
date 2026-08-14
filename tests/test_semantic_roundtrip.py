"""What the package said going in, and what it says coming out.

`test_package_completeness.py` asks whether the *name* of a construct survived.
This asks whether the *statement* survived — the value, the qualifiers, and what
it was about. The difference is the whole reason EF-004 lived through three
hundred tests: a book with two `<collection>` elements that comes back with one
still contains the word `collection`.

Every difference this finds must be listed below with a reason, and every entry
must still match something. That is a ratchet in both directions: a new loss
fails the first rule, and a loss that gets fixed fails the second, which forces
its entry to be deleted rather than left as folklore.

The list is split in two on purpose. `BY_DECISION` are things the rebuild
deliberately does not carry, each already argued somewhere. `STILL_BROKEN` are
defects — open, confirmed, and the reason `CONTRIBUTING.md`'s third alpha
condition is false. Keeping them in one list would let a defect quietly become
a decision, which is how they usually die.
"""

from __future__ import annotations

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .kitchen_sink import make_kitchen_sink
from .opf_graph import compare, graph_of

PRESETS = ("preserve", "strict", "minimal")

#: Pinned so `dcterms:modified` does not report itself as changed every run.
PINNED = "2020-01-01T00:00:00Z"

#: Differences the rebuild produces on purpose. The reasons are the same ones
#: `test_package_completeness.py` records against `DROPPED_ON_PURPOSE`.
BY_DECISION: dict[str, str] = {
    "package attribute changed: prefix": (
        "regenerated from what the output actually uses; carrying the source's "
        "declarations forward would keep prefixes nothing references"
    ),
    "dc:format": "always application/epub+zip for the output, so restating it is noise",
    # `meta[calibre:timestamp]` stood here, described as "EPUB 2 bookkeeping
    # from another tool, deliberately not carried over". It is carried now: the
    # deliberate part was one `startswith("calibre:")` in the writer, and what
    # it actually removed was every calibre entry this model does not consume —
    # custom order, ratings, somebody's own workflow fields. The two it *does*
    # consume, series and series index, never reached that line. F-011.
    "meta[cover]": "EPUB 2 cover convention; regenerated from the model when a profile asks",
    "properties='scripted'": (
        "removed because it was not true. The fixture declares `scripted` on a "
        "document containing no script, and EPUBCheck calls that an error on the "
        "*source*: \"The property 'scripted' should not be declared in the OPF "
        "file\". Manifest properties are derived from the document rather than "
        "copied, so a false declaration does not survive — see "
        "`ContentStage._properties`"
    ),
}

#: Open defects. Each one is a statement the source made and the output does
#: not, with nothing said about it in the report.
#:
#: Empty as of 0.2.3. EF-004 was the whole of this list and closed in 0.2.2;
#: the two entries that outlived it were both mine and neither was a defect —
#: one was a fixture declaring a property that was not true, the other was this
#: oracle comparing an unordered token list as a string. The list stays because
#: the two tests around it are the ratchet.
STILL_BROKEN: dict[str, str] = {}


@pytest.fixture(scope="module")
def sink(tmp_path_factory):
    return make_kitchen_sink(str(tmp_path_factory.mktemp("sink") / "kitchen-sink.epub"))


@pytest.fixture(scope="module")
def differences(sink, tmp_path_factory) -> dict[str, list[str]]:
    """Every difference, per preset, computed once."""
    folder = tmp_path_factory.mktemp("rebuilt")
    found: dict[str, list[str]] = {}
    for preset in PRESETS:
        result = rebuild(
            sink,
            str(folder / f"{preset}.epub"),
            Policy.preset(preset, modified_override=PINNED),
        )
        assert result.output_path, result.report.to_text()
        found[preset] = [str(d) for d in compare(graph_of(sink), graph_of(result.output_path))]
    return found


def _unexplained(lines: list[str]) -> list[str]:
    known = list(BY_DECISION) + list(STILL_BROKEN)
    return [line for line in lines if not any(marker in line for marker in known)]


@pytest.mark.parametrize("preset", PRESETS)
def test_every_difference_is_accounted_for(differences, preset):
    """The rule. Anything the package said and the output does not is either an
    argued decision or a listed defect — never a surprise."""
    surprises = _unexplained(differences[preset])
    assert not surprises, "\n  ".join(["unexplained losses in " + preset + ":"] + surprises)


def test_no_entry_describes_something_that_no_longer_happens():
    """The other half of the ratchet. When B3/B4 close one of these, this test
    goes red and the entry has to be deleted — which is the point. A fixed
    defect that keeps its entry becomes folklore."""
    # Computed here rather than taken from the fixture so the failure names the
    # entry rather than a preset.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        source = make_kitchen_sink(f"{tmp}/sink.epub")
        seen: list[str] = []
        for preset in PRESETS:
            result = rebuild(
                source, f"{tmp}/{preset}.epub", Policy.preset(preset, modified_override=PINNED)
            )
            seen += [str(d) for d in compare(graph_of(source), graph_of(result.output_path))]

    dead = [
        marker
        for marker in list(BY_DECISION) + list(STILL_BROKEN)
        if not any(marker in line for line in seen)
    ]
    assert not dead, (
        "listed as a known difference but no longer happening — delete the entry: "
        f"{sorted(dead)}"
    )


def test_every_entry_says_why():
    unexplained = [
        name
        for name, reason in list(BY_DECISION.items()) + list(STILL_BROKEN.items())
        if not reason.strip()
    ]
    assert not unexplained, unexplained


class TestTheOracleCanSeeWhatTheOldOneCouldNot:
    """Each of these is a loss the name-based oracle passes.

    Without them this file would be trusted for something it had never been
    shown to do, which is the same mistake as the oracle it replaces.
    """

    def test_losing_one_of_two_collections_is_a_difference(self, sink, tmp_path):
        from lxml import etree

        from .opf_graph import Graph

        before = graph_of(sink)
        after = Graph(
            package=before.package,
            nodes=before.nodes.copy(),
            edges=before.edges.copy(),
            spine=before.spine,
            collections=before.collections[:1],
        )
        for node in list(after.nodes):
            if node.kind == "collection" and node.subject == "index":
                del after.nodes[node]
        assert etree is not None  # the graph is built from lxml; keep the import honest
        assert [d for d in compare(before, after) if "collection" in str(d)]

    def test_a_changed_value_is_a_difference(self, sink):
        before = graph_of(sink)
        after = graph_of(sink)
        for node in list(after.nodes):
            if node.kind == "meta" and node.subject == "media:duration":
                del after.nodes[node]
                break
        assert [d for d in compare(before, after) if "media:duration" in str(d)]

    def test_a_broken_edge_is_a_difference_even_when_both_ends_survive(self, sink):
        before = graph_of(sink)
        after = graph_of(sink)
        for edge in list(after.edges):
            if edge.kind == "media-overlay":
                del after.edges[edge]
                break
        found = compare(before, after)
        assert [d for d in found if "media-overlay" in str(d)]
        # Both the document and the SMIL file are still there. Only the link is
        # gone, and that is exactly the shape of the real defect.
        assert not [d for d in found if d.kind == "node"]

    def test_a_reordered_spine_is_a_difference(self, sink):
        before = graph_of(sink)
        after = graph_of(sink)
        after.spine = tuple(reversed(before.spine))
        assert [d for d in compare(before, after) if "order" in d.kind]

    def test_an_addition_is_not_a_difference(self, sink):
        """A rebuild may say more — it generates navigation and stamps metadata.
        An oracle that reported those would be noise, and noise gets muted."""
        from .opf_graph import Node

        before = graph_of(sink)
        after = graph_of(sink)
        after.nodes[Node("meta", "schema:accessMode", "auditory")] += 1
        assert not compare(before, after)

class TestTheOracleDoesNotCryWolf:
    """The other failure mode, and the one this file actually hit.

    Two entries sat in `STILL_BROKEN` describing losses that were not losses:
    a fixture declaring `scripted` on a document with no script, and this
    oracle comparing `properties` as a string when it is an unordered set of
    tokens. Both were reported as findings neither audit had caught. Neither
    was real. An oracle that produces false findings spends the credibility the
    true ones need.
    """

    @staticmethod
    def _with_tokens_reordered(sink, destination):
        """A copy of the book whose `properties` say the same in another order."""
        import re
        import shutil
        import zipfile

        shutil.copyfile(sink, destination)
        with zipfile.ZipFile(sink) as archive:
            names = archive.namelist()
            contents = {name: archive.read(name) for name in names}

        opf_name = next(n for n in names if n.endswith(".opf"))
        opf = contents[opf_name].decode()
        opf = re.sub(
            r'properties="([^"]+)"',
            lambda m: 'properties="' + " ".join(reversed(m.group(1).split())) + '"',
            opf,
        )
        contents[opf_name] = opf.encode()

        with zipfile.ZipFile(destination, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            for name in names:
                if name != "mimetype":
                    archive.writestr(name, contents[name])
        return str(destination)

    def test_reordered_tokens_are_not_a_loss(self, sink, tmp_path):
        from .opf_graph import compare, graph_of

        other = self._with_tokens_reordered(sink, tmp_path / "reordered.epub")
        differences = compare(graph_of(sink), graph_of(other))
        assert not differences, [str(d) for d in differences]

    def test_a_genuinely_different_property_is_still_a_loss(self, sink):
        """The reordering rule must not swallow a token that actually went."""
        from .opf_graph import Node, compare, graph_of

        before = graph_of(sink)
        after = graph_of(sink)
        for node in list(after.nodes):
            qualifiers = dict(node.qualifiers)
            tokens = qualifiers.get("properties", "").split()
            if len(tokens) < 2:
                continue
            del after.nodes[node]
            after.nodes[
                Node(
                    node.kind,
                    node.subject,
                    node.value,
                    tuple(sorted({**qualifiers, "properties": tokens[0]}.items())),
                )
            ] += 1
            break
        assert [d for d in compare(before, after) if "properties" in str(d)]
