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
    "meta[calibre:timestamp]": "EPUB 2 bookkeeping from another tool, deliberately not carried over",
    "meta[cover]": "EPUB 2 cover convention; regenerated from the model when a profile asks",
    "display-seq": "not modelled; title ordering is the model's own",
    "link[record]": (
        "an external metadata record is not read into the model, so re-emitting it "
        "would mean copying a reference this tool cannot verify"
    ),
}

#: Open defects. Each one is a statement the source made and the output does
#: not, with nothing said about it in the report.
#:
#: EF-004 was the whole of this list and is closed as of 0.2.2. What is left
#: are two losses this oracle found itself, which is the argument for having
#: written it.
STILL_BROKEN: dict[str, str] = {
    "properties='scripted'": (
        "not in either audit's table; found by this oracle. `preserve` drops the "
        "manifest property that says the document contains scripting, while "
        "`minimal` keeps it. A reading system uses it to decide whether to allow "
        "scripting at all"
    ),
    "itemref[file:cover.xhtml]": (
        "not in either audit's table; found by this oracle. `itemref/@properties` "
        "is dropped, so `page-spread-center` is lost — a fixed-layout instruction "
        "about which side of the fold a page belongs on"
    ),
}


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
