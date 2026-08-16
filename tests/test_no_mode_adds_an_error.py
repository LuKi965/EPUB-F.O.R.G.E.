"""The invariant the owner's own library found broken: no mode adds an error.

`test_epubcheck.py` asserts it — on one fixture. That is the difference between
a claim and a measurement, and the owner's corpus run is what made the
difference visible: across 67 books, `preserve` produced twelve error shapes
that were not in the sources, and the suite was green throughout.

So the assertion moves to where it can fail. Every book of the public corpus,
every mode, EPUBCheck on the source and on each output, and the comparison is
between *shapes* rather than counts — a rebuild that removes one error and adds
a different one leaves the count alone and is exactly the case worth catching.

Two of the three defects that run exposed are fixed and pinned here:

* the generated navigation linking to a document the source kept out of the
  spine (`RSC-011`), which EPUB 2 allows and EPUB 3 does not;
* `<col>` directly under `<table>`, which XHTML 1.1 allows and XHTML5 does not.

The third — an image renamed to match its real type while the container-only
mode promised the documents pointing at it would not be touched (`RSC-007`) —
is pinned in `test_minimal_keeps_its_promise` below, because it is a conflict
between two promises rather than a validation rule.

This file is slow: a JVM per book per mode. It is worth it, and it skips
cleanly wherever EPUBCheck is not installed rather than pretending to pass.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.validate import find_epubcheck, validate

from .public_corpus import BOOKS, build_all

MODES = ("minimal", "preserve", "strict")

pytestmark = pytest.mark.skipif(
    find_epubcheck() is None,
    reason="EPUBCheck is not installed here; this asserts nothing without it",
)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    room = tmp_path_factory.mktemp("books")
    build_all(room)
    return room


#: What the container-only mode writes itself, and is therefore answerable for.
#: Everything else it copies through byte for byte, which is its whole promise.
WRITTEN_BY_MINIMAL = ("package.opf", "content.opf", "nav.xhtml", "toc.ncx",
                      "container.xml", ".epub")


def shapes(path: str, *, only_in=None) -> set:
    """The error shapes EPUBCheck finds, without line numbers or file names.

    Shapes rather than counts, and rather than full messages: the same defect
    in two books reads as two messages and one shape, and a rebuild that moves
    a defect from line 4 to line 6 has not introduced anything.

    *only_in* narrows to errors reported against particular files, which is how
    the container-only mode is held to the right promise — see below.
    """
    result = validate(path)
    if not result.available:
        pytest.skip("EPUBCheck could not run on this file")
    if only_in is None:
        return {shape for shape, _ in (result.shapes or {}).items()}
    found = set()
    for message in result.messages or ():
        if not message.startswith("ERROR"):
            continue
        where = message.rpartition("(")[2].rstrip(")")
        if not where.endswith(tuple(only_in)):
            continue
        # Same normalisation the shapes use: the sentence without its location.
        found.add(message.split("(")[0].removeprefix("ERROR:").strip()[:90])
    return found


def rebuilt(source, destination, mode: str):
    return rebuild(
        str(source),
        str(destination),
        Policy.preset(
            mode,
            render_gate="off",
            accept_unverified_render=True,
            accept_reconstructed_metadata=True,
            validate_before_publish="off",
        ),
    )


@pytest.mark.parametrize("name", sorted(BOOKS))
@pytest.mark.parametrize("mode", MODES)
def test_no_mode_introduces_an_error_the_source_did_not_have(
    corpus, tmp_path, name, mode
):
    source = corpus / f"{name}.epub"
    if not source.exists():
        pytest.skip(f"{name} was not built")
    result = rebuilt(source, tmp_path / f"{mode}-{name}.epub", mode)
    if not result.status.wrote_a_file:
        # A mode that refuses has introduced nothing; refusing is its own
        # decision and `test_render_gate.py` and `test_epubcheck.py` own it.
        return

    # The container-only mode is judged on what it writes and nothing else, and
    # that is not a softer rule — it is the correct one. Its promise is that the
    # content documents come out byte for byte, so an EPUB 2 document carrying
    # markup XHTML5 rejects (`<col>` under `<table>`, `width` on a paragraph)
    # comes out still carrying it, and the version upgrade turns it into an
    # error nobody here wrote. Demanding otherwise would be demanding that the
    # mode break its own promise. `preserve` and `strict` rewrite the documents
    # and *are* answerable for every error in them.
    narrow = WRITTEN_BY_MINIMAL if mode == "minimal" else None
    before = shapes(str(source), only_in=narrow)
    after = shapes(result.output_path, only_in=narrow)
    introduced = after - before
    assert not introduced, (
        f"{name} in {mode} gained {len(introduced)} error shape(s) the source "
        f"did not have:\n  " + "\n  ".join(sorted(introduced))
    )


@pytest.mark.parametrize("name", sorted(BOOKS))
def test_minimal_keeps_its_promise_about_the_files_it_does_not_rewrite(
    corpus, tmp_path, name
):
    """Container-only means the documents come out byte for byte — and that
    promise reaches further than the documents themselves.

    Found on the owner's collection as `RSC-007: Referenced resource could not
    be found`: an image whose bytes were PNG and whose name said JPEG was
    renamed to match, while the document pointing at it stayed exactly as it
    was, by this mode's own promise. Two promises, one file, and only one of
    them can hold. The manifest is this program's to write, so the declared
    type is still corrected; the file keeps its name.
    """
    source = corpus / f"{name}.epub"
    if not source.exists():
        pytest.skip(f"{name} was not built")
    result = rebuilt(source, tmp_path / f"minimal-{name}.epub", "minimal")
    if not result.status.wrote_a_file:
        return
    with zipfile.ZipFile(source) as archive:
        before = {
            entry.filename.rpartition("/")[2]
            for entry in archive.infolist()
            if not entry.is_dir()
        }
    with zipfile.ZipFile(result.output_path) as archive:
        after = {
            entry.filename.rpartition("/")[2]
            for entry in archive.infolist()
            if not entry.is_dir()
        }
    # The package document, the navigation and the NCX are this mode's to write
    # and may appear or change name; nothing that a content document links to
    # may be renamed underneath it.
    ours = {"package.opf", "nav.xhtml", "toc.ncx", "content.opf", "mimetype"}
    vanished = {name for name in before - after if name not in ours}
    assert not vanished, (
        f"{name}: container-only mode renamed or dropped {sorted(vanished)}, "
        "which the documents it promised not to touch may still be pointing at"
    )
