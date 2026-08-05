"""Every finding this program can report, by a name that does not change.

The identity of a finding used to be its English sentence. Three things follow
from that, and all three had already happened:

* tests assert fragments of sentences, so rewording a message breaks a test
  that was never about the wording — it did, during 0.8.0;
* `survey.py` has to strip numbers and quoted fragments with regular
  expressions before it can count anything, which is a symptom rather than a
  solution;
* the report cannot be translated. A sentence that *is* the identity cannot be
  replaced by its Polish equivalent without changing what it identifies, which
  is why the interface is bilingual and the report is not.

So a finding carries a `rule` — `nav.repointed`, `xhtml.doctype-modernised` —
and the sentence becomes what it should have been all along: the human-readable
rendering of something else.

The catalogue below is the list of what exists. It is not documentation that
happens to sit near the code: `test_rules.py` fails if a finding is reported
under an id that is not here, and fails if an id here is reported by nothing.
Both directions, because a catalogue that drifts is worse than none — it is
consulted and believed.

Identifiers are `<area>.<what>`, lower case, hyphen-separated. The area is the
part of the program the reader would blame, not necessarily the module that
raised it.
"""

from __future__ import annotations

#: id → one line saying what the finding means. English for now; this mapping is
#: the thing a translation replaces, and the reason it exists.
CATALOGUE: dict[str, str] = {
    # -- reader: what the source turned out to be ---------------------------
    "reader.remote-resource": "the manifest declares a resource hosted elsewhere",
    "reader.dangling-reference": "a fallback or media-overlay names an id the manifest does not define",
    "reader.name-rewritten": "an archive entry name was not a container path and was rewritten",
    "reader.name-dropped": "an archive entry name could not be made into a container path",
    "reader.duplicate-entry": "the archive holds the same entry name twice",
    "reader.colliding-names": "two entry names differ only by case or by Unicode normalisation",
    # -- structure: where files ended up ------------------------------------
    "structure.relaid-out": "files were regrouped into a typed layout with portable names",
    "structure.junk-removed": "packaging leftovers were removed",
    "structure.orphan-removed": "a file nothing in the book references was removed",
    "structure.carried-xml-repointed": "references inside a file carried as-is were repointed",
    # -- navigation ---------------------------------------------------------
    "nav.regenerated": "the navigation document was regenerated",
    "nav.generated": "the book had none and one was generated",
    "nav.contents-page-kept": "the publisher's contents page was kept and the navigation put beside it",
    "nav.repointed": "references to the replaced navigation document were repointed",
    "nav.kept-in-spine": "the navigation document stayed in the reading order, where the source had it",
    "nav.entry-dropped": "a table-of-contents entry pointed at something that is not there",
    "nav.fragment-cleared": "a navigation anchor does not exist and the entry now points at the document",
    "nav.toc-synthesised": "the book had no usable table of contents and one was built from the spine",
    "nav.cover-page-generated": "a cover page was generated so the artwork is the first spine item",
    "nav.ncx-written": "a legacy NCX was written alongside the navigation document",
    "nav.ncx-dropped": "the legacy NCX was not carried over",
    # -- content documents --------------------------------------------------
    "xhtml.untouched": "content documents were left as they were; only the container was rebuilt",
    "xhtml.doctype-modernised": "a legacy DOCTYPE was replaced with the EPUB 3 one",
    "xhtml.doctype-kept": "a legacy DOCTYPE stayed because an entity in the document cannot be resolved",
    "xhtml.entities-rewritten": "undefined named entities were rewritten as numeric references",
    "xhtml.property-withdrawn": "a manifest property the document does not bear out was withdrawn",
    # -- package ------------------------------------------------------------
    "package.regenerated": "the package document was regenerated",
    # -- validation ---------------------------------------------------------
    "epubcheck.reported": "EPUBCheck reported problems with the output",
    "epubcheck.clean": "EPUBCheck accepted the output",
    "epubcheck.unavailable": "EPUBCheck is not installed, so the output was not validated",
}


def known(rule: str) -> bool:
    return rule in CATALOGUE


def describe(rule: str) -> str:
    """What the id means, or the id itself when it is not in the catalogue.

    Returning the id rather than raising is deliberate: a report that is missing
    an explanation is still a report, and a program that refuses to print one
    because of a missing dictionary entry helps nobody.
    """
    return CATALOGUE.get(rule, rule)


__all__ = ["CATALOGUE", "describe", "known"]
