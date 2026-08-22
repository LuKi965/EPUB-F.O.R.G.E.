"""The package document as a graph, so that a loss cannot hide behind a name.

`test_package_completeness.py` asks whether the *name* of a construct still
appears somewhere in the output. That question is too weak, and it is why
EF-004 survived three hundred tests: a book with two `<collection>` elements
that comes back with one still contains the name `collection`, so the set-based
oracle sees no difference. The same blindness covers a `<meta>` whose value
changed, a `fallback` chain that now points somewhere else, and a spine whose
order was rearranged.

This module answers a harder question: *what does the package say, and about
what*. Three things follow from that.

**Multiset, not set.** Two collections are two nodes. Losing one is a
difference.

**Values and qualifiers, not just names.** A node carries its text, its
`scheme`, its `xml:lang`, its `dir`. Changing `role` from `aut` to `trl` is a
difference.

**Edges, resolved.** `refines`, `fallback`, `media-overlay`, spine membership
and collection membership are recorded as edges between nodes — and resolved
through the `id` attribute rather than stored as the id itself, because the
rebuild regenerates identifiers. An edge that used to point at the narration
file and now points at nothing is a difference; an edge that points at the same
resource under a new id is not.

## What identity means here, and what it costs

A rebuild moves files (`OEBPS/ch1.xhtml` → `EPUB/text/0001-ch1.xhtml`), renames
identifiers, and may transcode an image. So a resource cannot be identified by
its href, its id, or its bytes. It is identified by its **file name**, with two
normalisations, each of which exists because the rebuild does the thing it
undoes:

* a leading ordinal — `0001-ch1.xhtml` is `ch1.xhtml`, because `preserve`
  numbers documents by reading order;
* an image's extension — `cover.png` and `cover.webp` are one resource,
  because transcoding is a policy decision and not a loss.

The extension is otherwise kept, and that matters: `ch1.xhtml` and `ch1.smil`
are a chapter and its narration, and an oracle that treats them as one node
cannot see the narration disappear — which is the defect this was written for.

The cost is stated rather than hidden: a rebuild that renamed a file for any
other reason would read as a loss here. That is a better failure than the one
this replaces, which was silence.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from lxml import etree

OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XML = "http://www.w3.org/XML/1998/namespace"

#: Attributes that name something rather than say something. Excluded from a
#: node's identity because the rebuild is entitled to regenerate them; the
#: edges they carry are resolved and compared separately.
IDENTIFIERS = {"id", "idref", "refines", "fallback", "media-overlay", "toc"}


def _local(name: str) -> str:
    return name.rpartition("}")[2]


def _is_remote(href: str) -> bool:
    return bool(urlsplit(href).scheme) and not href.startswith("file:")


#: What `preserve` prefixes documents with, in reading order.
ORDINAL = re.compile(r"^\d{4}-")

#: Interchangeable by policy, so not an identity. `transcode_images` is a
#: decision the user makes; the resource is the same picture either way.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}


def resource_key(href: str) -> tuple[str, str]:
    """The identity of whatever an href points at.

    Remote resources keep their full URL — a remote resource has no local file
    to be moved or transcoded, and the URL is the whole of what the package
    said about it.
    """
    href = unquote(href.split("#", 1)[0])
    if _is_remote(href):
        return ("url", href)
    name = ORDINAL.sub("", posixpath.basename(href))
    stem, suffix = posixpath.splitext(name)
    if suffix.lower() in IMAGE_SUFFIXES:
        return ("file", f"{stem}.image")
    return ("file", stem + suffix.lower())


@dataclass(frozen=True)
class Node:
    """One statement the package makes."""

    #: "dc:title", "meta", "item", "itemref", "link", "collection".
    kind: str
    #: The text, or the defining value: a `meta`'s property, an item's key.
    subject: str
    #: What is asserted: the text of a meta, an item's media type.
    value: str = ""
    #: Everything else the element said, minus the identifier attributes.
    qualifiers: tuple[tuple[str, str], ...] = ()

    def __str__(self) -> str:
        rendered = f"{self.kind}[{self.subject}]"
        if self.value:
            rendered += f" = {self.value!r}"
        if self.qualifiers:
            rendered += " " + " ".join(f"{k}={v!r}" for k, v in self.qualifiers)
        return rendered


@dataclass(frozen=True)
class Edge:
    """One statement about the relation between two of them."""

    kind: str
    source: str
    target: str

    def __str__(self) -> str:
        return f"{self.source} --{self.kind}--> {self.target}"


@dataclass
class Graph:
    """Everything the package document says, in a form that can be subtracted."""

    package: tuple[tuple[str, str], ...] = ()
    nodes: Counter = field(default_factory=Counter)
    edges: Counter = field(default_factory=Counter)
    #: Order is a statement in its own right: the spine is a reading order, and
    #: a collection's links are sequenced. Compared separately from membership
    #: so that "reordered" and "lost" are different failures.
    spine: tuple[str, ...] = ()
    collections: tuple[tuple[str, tuple[str, ...]], ...] = ()


#: Attributes whose value is an unordered set of tokens rather than a string.
#: Comparing them as written reported `"a b"` becoming `"b a"` as a loss — the
#: writer sorts them, so the oracle claimed `itemref/@properties` was being
#: dropped when every token was still there. An oracle that cries wolf about
#: whitespace is worse than none, because the next real finding is read as
#: another one of those.
TOKEN_LISTS = {"properties", "rel"}


def _qualifiers(element) -> tuple[tuple[str, str], ...]:
    found = []
    for key, value in element.attrib.items():
        name = _local(key) if key.startswith("{") else key
        if key.startswith(f"{{{XML}}}"):
            name = f"xml:{name}"
        if name in IDENTIFIERS:
            continue
        if name in TOKEN_LISTS:
            value = " ".join(sorted(value.split()))
        found.append((name, value))
    return tuple(sorted(found))


def _key_of(element) -> str:
    """The canonical name of a node, used as the endpoint of an edge."""
    tag = _local(element.tag)
    if tag == "item":
        kind, name = resource_key(element.get("href", ""))
        return f"{kind}:{name}"
    if tag == "meta":
        prop = element.get("property") or element.get("name") or ""
        return f"meta:{prop}={(element.text or '').strip()}"
    if element.tag.startswith(f"{{{DC}}}"):
        return f"dc:{tag}={(element.text or '').strip()}"
    if tag == "collection":
        return f"collection:{element.get('role', '')}"
    return tag


def _read_package(path: str) -> tuple[etree._Element, str]:
    with zipfile.ZipFile(path) as archive:
        container = etree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        opf_name = rootfile.get("full-path")
        return etree.fromstring(archive.read(opf_name)), opf_name


def graph_of(path: str) -> Graph:
    """Build the graph for the package document inside an EPUB."""
    root, _ = _read_package(path)

    by_id: dict[str, etree._Element] = {}
    for element in root.iter():
        if isinstance(element.tag, str) and element.get("id"):
            by_id[element.get("id")] = element

    def resolve(reference: str | None) -> str | None:
        """An id reference, as the thing it points at rather than as a name."""
        if not reference:
            return None
        target = by_id.get(reference.lstrip("#"))
        return _key_of(target) if target is not None else None

    graph = Graph(package=_qualifiers(root))
    nodes: Counter = Counter()
    edges: Counter = Counter()

    metadata = root.find(f"{{{OPF}}}metadata")
    for element in metadata if metadata is not None else []:
        if not isinstance(element.tag, str):
            continue  # a comment; carried by the reader, not a package statement
        tag = _local(element.tag)
        text = (element.text or "").strip()
        if element.tag.startswith(f"{{{DC}}}"):
            nodes[Node(f"dc:{tag}", tag, text, _qualifiers(element))] += 1
        elif tag == "meta":
            subject = element.get("property") or element.get("name") or ""
            value = text or element.get("content") or ""
            nodes[Node("meta", subject, value, _qualifiers(element))] += 1
        elif tag == "link":
            nodes[Node("link", element.get("rel", ""), element.get("href", ""),
                       _qualifiers(element))] += 1
        # A refinement says something *about* another statement, and losing the
        # thing it refined is a different defect from losing the refinement.
        refined = resolve(element.get("refines"))
        if refined:
            edges[Edge("refines", _key_of(element), refined)] += 1

    manifest = root.find(f"{{{OPF}}}manifest")
    for item in manifest if manifest is not None else []:
        if not isinstance(item.tag, str):
            continue
        href = item.get("href", "")
        kind, name = resource_key(href)
        nodes[
            Node(
                "item",
                f"{kind}:{name}",
                item.get("media-type", ""),
                tuple(
                    q for q in _qualifiers(item)
                    # The href moves by design; its identity is already in the
                    # subject, and keeping the path here would report every
                    # reorganisation as a loss.
                    if q[0] != "href"
                ),
            )
        ] += 1
        for attribute, relation in (("fallback", "fallback"), ("media-overlay", "media-overlay")):
            target = resolve(item.get(attribute))
            if target:
                edges[Edge(relation, f"{kind}:{name}", target)] += 1

    spine_element = root.find(f"{{{OPF}}}spine")
    order: list[str] = []
    if spine_element is not None:
        nodes[Node("spine", "spine", "", _qualifiers(spine_element))] += 1
        toc = resolve(spine_element.get("toc"))
        if toc:
            edges[Edge("spine-toc", "spine", toc)] += 1
        for itemref in spine_element:
            if not isinstance(itemref.tag, str):
                continue
            target = resolve(itemref.get("idref")) or "?"
            order.append(target)
            nodes[Node("itemref", target, "", _qualifiers(itemref))] += 1
            edges[Edge("spine", "spine", target)] += 1

    collections: list[tuple[str, tuple[str, ...]]] = []
    for collection in root.findall(f"{{{OPF}}}collection"):
        role = collection.get("role", "")
        nodes[Node("collection", role, "", _qualifiers(collection))] += 1
        members = []
        for link in collection.findall(f"{{{OPF}}}link"):
            kind, name = resource_key(link.get("href", ""))
            members.append(f"{kind}:{name}")
            edges[Edge("collection", f"collection:{role}", f"{kind}:{name}")] += 1
        collections.append((role, tuple(members)))

    graph.nodes = nodes
    graph.edges = edges
    graph.spine = tuple(order)
    graph.collections = tuple(collections)
    return graph


@dataclass
class Difference:
    """One way in which the rebuilt package says less, or says it differently."""

    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}"


#: D-035: the relaying presets name content documents by their role — the
#: contents' chapters as `chapter-NN`, the guide's cover page as `cover`, and
#: so on. A document's identity survives that rename the same way it survives
#: the ordinal prefix: the reading order pairs the old name with the new one.
ROLE_NAMED = re.compile(
    r"^(?:cover|titlepage|toc|copyright|dedication|foreword|preface|prologue"
    r"|epilogue|afterword|appendix|glossary|index|bibliography|acknowledgments"
    r"|colophon|epigraph|footnotes|illustrations|tables|part|chapter)"
    r"(?:-\d+)*\.xhtml$"
)


def _role_aliases(before: Graph, after: Graph) -> dict[str, str]:
    """new key → old key, for documents the rebuild renamed by role.

    Deliberately narrow, so nothing real hides behind it: the spines must be
    the same length, the new name must come from the role vocabulary, and it
    must not already exist in the source — otherwise the pairing could dress
    a reorder or a loss up as a rename, and the oracle reports instead.
    """
    if len(before.spine) != len(after.spine):
        return {}
    aliases: dict[str, str] = {}
    taken = set(before.spine)
    for source, renamed in zip(before.spine, after.spine):
        if renamed == source or renamed in taken:
            continue
        name = renamed.partition(":")[2]
        if renamed.startswith("file:") and ROLE_NAMED.match(name):
            aliases[renamed] = source
    return aliases


def _dealiased(after: Graph, aliases: dict[str, str]) -> Graph:
    """The after-graph with every role-given name read as its old identity."""
    if not aliases:
        return after

    def keyed(value: str) -> str:
        return aliases.get(value, value)

    nodes: Counter = Counter()
    for node, count in after.nodes.items():
        nodes[Node(node.kind, keyed(node.subject), node.value, node.qualifiers)] += count
    edges: Counter = Counter()
    for edge, count in after.edges.items():
        edges[Edge(edge.kind, keyed(edge.source), keyed(edge.target))] += count
    return Graph(
        package=after.package,
        nodes=nodes,
        edges=edges,
        spine=tuple(keyed(item) for item in after.spine),
        collections=tuple(
            (role, tuple(keyed(member) for member in members))
            for role, members in after.collections
        ),
    )


def compare(before: Graph, after: Graph) -> list[Difference]:
    """What the rebuild lost. Additions are not differences.

    A rebuild is entitled to say *more* — it generates a navigation document,
    stamps `dcterms:modified`, asserts accessibility metadata. It is not
    entitled to say less, and this only reports less.
    """
    after = _dealiased(after, _role_aliases(before, after))
    differences: list[Difference] = []

    missing_attributes = dict(before.package).keys() - dict(after.package).keys()
    for name in sorted(missing_attributes):
        differences.append(Difference("package attribute", name))
    for name, value in sorted(before.package):
        if name in dict(after.package) and dict(after.package)[name] != value:
            differences.append(
                Difference("package attribute changed", f"{name}: {value!r} → {dict(after.package)[name]!r}")
            )

    for node, count in sorted(before.nodes.items(), key=lambda pair: str(pair[0])):
        present = after.nodes.get(node, 0)
        if present < count:
            differences.append(
                Difference("node", f"{node}" + (f" ({present} of {count} left)" if present else ""))
            )

    for edge, count in sorted(before.edges.items(), key=lambda pair: str(pair[0])):
        if after.edges.get(edge, 0) < count:
            differences.append(Difference("edge", str(edge)))

    if before.spine != after.spine:
        kept = [item for item in before.spine if item in after.spine]
        if kept != [item for item in after.spine if item in before.spine]:
            differences.append(Difference("spine order", f"{before.spine} → {after.spine}"))
        for item in before.spine:
            if item not in after.spine:
                differences.append(Difference("spine member", item))

    before_roles = Counter(role for role, _ in before.collections)
    after_roles = Counter(role for role, _ in after.collections)
    for role, count in before_roles.items():
        if after_roles[role] < count:
            differences.append(
                Difference("collection", f"{role} ({after_roles[role]} of {count} left)")
            )
    for role, members in before.collections:
        for other_role, other_members in after.collections:
            if other_role != role:
                continue
            if members != other_members and set(members) <= set(other_members):
                differences.append(
                    Difference("collection order", f"{role}: {members} → {other_members}")
                )
            break

    return differences


__all__ = ["Difference", "Edge", "Graph", "Node", "compare", "graph_of", "resource_key"]
