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

import re
import string

#: id → one line saying what the finding means. English for now; this mapping is
#: the thing a translation replaces, and the reason it exists.
CATALOGUE: dict[str, str] = {
    # -- reader: what the source turned out to be ---------------------------
    "reader.remote-resource": "the manifest declares a resource hosted elsewhere",
    "reader.dangling-reference": "{attribute} names an id the manifest does not define",
    "reader.name-rewritten": "an archive entry name was not a container path and was rewritten",
    "reader.name-dropped": "an archive entry name could not be made into a container path: {reason}",
    "reader.duplicate-entry": "the archive holds the same entry name twice",
    "reader.colliding-names": "{count} entry names differ only by {kind}",
    "reader.entry-too-large": "an archive entry is implausibly large and was refused: {reason}",
    "reader.meta-inf-carried": "a reserved container file was carried through untouched: it says something about the publication that this rebuild does not change",
    "reader.meta-inf-invalidated": "a digital signature or container inventory was removed, because the rebuild makes it untrue: a signature is computed over exact bytes and cannot survive them changing, and one left in place would read as evidence of tampering rather than of a repair",
    "reader.meta-inf-unknown-carried": "a file this program does not recognise was found beside the container document and carried through unchanged rather than judged",
    "reader.manifest-id-duplicated": "two manifest items share the id {id} ({first} and {second}); the spine entries that name it could mean either, and this rebuild will not pick one for you",
    "reader.entry-unreadable": "an archive entry could not be read at all: {error}",
    "reader.rootfile-missing": "container.xml points at a package document that is not in the archive",
    "reader.container-missing": "META-INF/container.xml is missing, so the package was located by scanning",
    "reader.package-scanned": "the package document was recovered by scanning the archive",
    "reader.metadata-missing": "the package has no <metadata> element",
    "reader.manifest-missing": "the package has no <manifest>, so the archive contents were used instead",
    "reader.manifest-file-missing": "the manifest lists a file that is not in the archive",
    "package.not-readable-again": "the file was written and this program cannot read it back cleanly ({detail}); a book its own reader stumbles over is not one to hand on without a look",
    "package.refinements-carried": "{count} metadata refinement(s) this model has no field for were carried through and re-pointed at the ids the rebuilt package gives those nodes",
    "package.refinements-unanchored": "{count} metadata refinement(s) referred to a node that did not survive the rebuild and were dropped rather than written pointing at nothing",
    "package.renditions-written": "{count} renditions were rebuilt, each into its own file ({names})",
    "reader.other-rendition-skipped": "{count} file(s) belong to another rendition of this container and were left to its own output; each rendition is rebuilt into a file of its own, so nothing is missing from the set",
    "reader.renditions-offered": "this container offers {count} renditions ({names}) — separate publications of the same work, each with its own manifest and reading order; this book is one of them",
    "reader.manifest-spelling-matched": "the manifest names a file the archive does not hold under that exact name, and holds one under another spelling of it ({how}); {found} was used, because the archive settles which file was meant",
    "reader.manifest-case-matched": "a manifest entry matched a file only when case was ignored",
    "reader.manifest-type-corrected": "the manifest declared {declared}, which is not what the file is; corrected to {actual}",
    "reader.spine-missing": "the package has no <spine>",
    "reader.spine-id-unknown": "the reading order referenced a manifest id that does not exist",
    "reader.ncx-unparseable": "the legacy NCX could not be parsed",
    "reader.nav-unparseable": "the navigation document could not be parsed",
    "reader.encryption-unparseable": "META-INF/encryption.xml could not be parsed",
    "reader.drm": "the archive declares real encryption, not just font obfuscation",
    "reader.mimetype-invalid": "the mimetype entry is missing or wrong and will be regenerated",
    "reader.page-direction-carried": "the page progression direction is {direction} and was carried through",
    "reader.toc-from-ncx": "the table of contents was recovered from the legacy NCX",
    "reader.ncx-unreferenced-used": "an NCX nothing referenced was found and used for the table of contents",
    "reader.unmanifested-file": "a file is in the archive but absent from the manifest",
    "reader.spine-rebuilt": "the reading order was empty and was rebuilt from {count} content documents",
    # -- structure: where files ended up ------------------------------------
    "structure.role-named": "{count} document(s) were named by their role — cover, toc, chapter-NN with -2/-3 for a chapter split across files ({examples}); documents the evidence cannot name keep their old stem",
    "structure.relaid-out": "{count} file(s) were regrouped into a typed {directory}/ layout with portable names",
    "structure.junk-removed": "packaging leftovers were removed",
    "structure.junk-kept": "this file has the name of a packaging leftover and the book links to it, so it was kept: a name is not evidence about content, and `.bak` is a name a publisher can give a chapter",
    "structure.orphan-removed": "a file nothing in the book references was removed",
    "structure.carried-xml-repointed": "{count} reference(s) inside a file carried as-is were repointed",
    # -- navigation ---------------------------------------------------------
    "nav.regenerated": "the navigation document was regenerated, with {count} entries",
    "nav.generated": "the book had no navigation document and one was generated, with {count} entries",
    "nav.contents-page-kept": "the publisher's contents page was kept and the navigation put beside it",
    "nav.repointed": "{count} reference(s) to the replaced navigation document were repointed",
    "nav.landmarks-deduplicated": "{count} landmark(s) named the same place twice and the repeats were dropped",
    "nav.sections-carried": "{count} navigation section(s) this program does not model by name ({names}) were carried into the regenerated navigation with their entries and their epub:type intact",
    "reader.nav-sections-found": "the navigation document holds {count} section(s) beyond the contents, the landmarks and the page list ({names})",
    "nav.fragment-carried": "{count} reference(s) into the replaced navigation document kept their anchor, because the section it named has a counterpart in the regenerated one",
    "nav.kept-in-spine": "the navigation document stayed in the reading order, where the source had it",
    "nav.entries-repointed": "{count} contents entries all led to one untangled id and were repointed in document order, at a person's word",
    "nav.duplicate-target-found": "{count} contents entries lead to the same place; they were left as they were",
    "nav.entry-dropped": "{count} table-of-contents entry/entries pointed at something that is not there",
    "nav.fragment-cleared": "{count} navigation anchor(s) do not exist, so the entries now point at the document",
    "nav.toc-synthesised": "the book had no usable table of contents and one was built from {count} spine documents",
    "nav.cover-page-generated": "a cover page was generated so the artwork is the first spine item",
    "nav.ncx-written": "a legacy NCX was written alongside the navigation document",
    "nav.ncx-dropped": "the legacy NCX was not carried over",
    "nav.cover-image-missing": "the declared cover image is not in the archive",
    # -- content documents --------------------------------------------------
    "xhtml.untouched": "content documents were left as they were; only the container was rebuilt",
    "xhtml.untouched-except-doctype": "content documents were left as they were apart from the DOCTYPE; only the container was rebuilt",
    "xhtml.doctype-modernised": "a legacy DOCTYPE was replaced with the EPUB 3 one in {count} document(s)",
    "xhtml.orphaned-styling-restored": "{count} class(es) the document uses but no stylesheet it links defines were given the publisher's own rule: {classes}",
    "xhtml.empty-span-found": "{count} <span>(s) whose every rule says nothing — a conversion artefact; they are kept",
    "xhtml.empty-span-unwrapped": "{count} <span>(s) unwrapped whose every rule said nothing; the text inside is untouched",
    "xhtml.epub2-only-markup": "markup legal in EPUB 2 and not in EPUB 3 stays untouched in this mode: {what}",
    "xhtml.title-filled": "{count} empty <title> element(s) were given the document's own heading",
    "xhtml.doctype-kept": "{count} document(s) keep a legacy DOCTYPE because an entity cannot be resolved: {documents}",
    "xhtml.entities-rewritten": "undefined named entities were rewritten as numeric references",
    "xhtml.property-withdrawn": "manifest properties the document does not bear out were withdrawn: {properties}",
    "typography.ellipsis-normalised": "{count} run(s) of three dots became a single ellipsis character",
    "typography.conjunctions-bound": "{count} single-letter conjunction(s) were bound to the word after them",
    "typography.quotes-retyped": "{count} straight quote(s) were retyped into the book's own convention ({convention})",
    "typography.quotes-unsettled": "the book has not settled on a quoting convention, so its quotes were left alone",
    "typography.reverted": "{count} document(s) were put back unchanged: the typography pass could not show it kept the text",
    # -- profile -------------------------------------------------------------
    "profile.made-by": "the book carries traces of {count} tool(s): {tools}",
    "profile.body-text-found": "the body text is {shape}: {percent}% of {blocks} paragraph(s)",
    "profile.body-text-inconsistent": "no shape covers the body text; the commonest reaches {percent}% of {blocks} paragraph(s)",
    "profile.paragraphs-mixed": "paragraphs are separated both ways: {indented} by indent, {spaced} by space",
    "profile.paragraphs-consistent": "every paragraph is separated the same way: {paradigm}",
    "profile.dead-classes-found": "{count} class(es) are declared in CSS and used by nothing",
    "profile.duplicate-classes-found": "{names} class(es) in {groups} group(s) declare exactly the same thing",
    "profile.scene-separators-found": "{count} scene separator(s) were found",
    "profile.break-runs-found": "{count} run(s) of <br/> stand in for a paragraph break",
    "profile.heading-candidates-found": "{count} paragraph(s) look like headings without being marked as one",
    # -- stylesheets --------------------------------------------------------
    "css.url-unresolved": "{count} url() reference(s) could not be resolved and were left unchanged",
    "css.remote-import-removed": "{count} @import rule(s) fetching a stylesheet over the network were removed",
    "xhtml.remote-import-removed": "{count} @import rule(s) fetching a stylesheet over the network were removed from a style element",
    "css.vendor-at-rule-kept": "{count} vendor-specific at-rule(s) targeting particular readers were kept",
    "css.kindle-media-removed": "Kindle-specific @media blocks were removed",
    "xhtml.forbidden-characters-removed": "{count} control character(s) that XML cannot represent were removed from this document",
    "xhtml.mojibake-translated": "{count} punctuation mark(s) a conversion had turned into unprintable codes were restored: {what}",
    "xhtml.mojibake-found": "{count} punctuation mark(s) sit here as unprintable codes and were left alone: {what}",
    "xhtml.mojibake-reverted": "the punctuation repair was undone in this document because it did not finish: {detail}",
    "xhtml.watermark-reverted": "{count} watermark marker(s) were left in this document because taking them out did not come out right: {detail}",
    "package.forbidden-characters-removed": "control characters that XML cannot represent were removed from: {fields}",
    "xhtml.shop-notice-removed": "{count} shop notice(s) were removed from {documents} document(s), by request: {removed}",
    "css.invalid-value-corrected": "{count} declaration(s) using the invalid value 'regular' were corrected",
    "css.invalid-value-inherited": "{count} declaration(s) using the invalid value 'regular' were left alone, because this stylesheet also sets italic or bold",
    "css.absolute-units": "{count} font size(s) are given in absolute units, so the reader's own font setting cannot move them",
    "css.absolute-units-relativised": "{count} absolute font size(s) were rewritten in rem, so the reader's font setting reaches them",
    "css.absolute-units-rooted": "{count} absolute font size(s) were kept: this stylesheet sets the root font size in pixels, so rewriting the rest would not free them",
    "css.unreachable-rules-found": "{count} of {total} rule(s) — {share}% of this stylesheet — name a class or id that appears nowhere in the book",
    "css.unreachable-rules-removed": "{count} of {total} rule(s) removed — {share}% of this stylesheet — naming a class or id that appears nowhere in the book",
    "css.unreachable-rules-scripted": "{count} rule(s) match nothing today, and are kept because the book carries a script",
    "css.unreachable-rules-unverified": "{count} rule(s) look unreachable but the sheet did not survive the check, so it was left as it was",
    "css.position-kept": "{count} absolute or fixed position rule(s) were kept",
    "css.position-kept-reflowable": "{count} absolute or fixed position rule(s) were kept in a reflowable book",
    "css.position-contained": "{count} out-of-flow position rule(s) are held inside a positioned ancestor in {documents} document(s) and were kept",
    "xhtml.position-pinned-in-flow": "content pinned to the foot of the page was translated into an in-flow equivalent",
    "css.position-superseded": "out-of-flow positioning is superseded in {count} document(s) by the equivalent written into them",
    "css.position-removed": "{count} absolute or fixed position rule(s) were removed from a reflowable book",
    "css.reader-property-kept": "{count} reader-specific CSS propert(ies) were kept for the legacy reader profile ({names})",
    "css.reader-property-removed": "{count} reader-specific CSS propert(ies) were removed",
    "css.font-stack-generic-added": "{count} font stack(s) gained the generic family the embedded font declares about itself",
    "css.font-stack-generic-approved": "{count} font stack(s) naming faces the book does not carry gained the generic family common knowledge assigns ({generics}), appended on a person's word",
    "css.font-stack-generic-missing": "{count} font stack(s) end without a generic family",
    "css.unparseable": "a stylesheet could not be parsed for validation: {error}",
    "css.no-usable-rules": "a stylesheet contains no usable rules",
    "xhtml.unparseable": "a content document could not be parsed at all: {error}",
    "xhtml.recovered-with-html-parser": "this document was not well-formed XML and had to be reconstructed by an HTML parser, which is a guess at what the publisher meant rather than a repair with a known result",
    "metadata.modified-pinned-to-epoch": "this book carries no modification date and no publication date, so the reproducible build stamped the epoch rather than inventing a plausible-looking one",
    "xhtml.html-source-parsed": "the source declares this document as HTML rather than XHTML, so it was read with an HTML parser — which is the right reading of it, not a recovery — and written out as XHTML",
    "xhtml.stylesheet-pi-converted": "{count} stylesheet(s) linked by an <?xml-stylesheet?> instruction ({names}) are now linked with <link rel=\"stylesheet\">, which is how EPUB 3 says it; the instruction itself is not allowed here and used to be removed with nothing put in its place",
    "xhtml.svg-case-restored": "{count} SVG name(s) that the HTML recovery had folded to lowercase were spelled correctly again; SVG is case-sensitive, so a `linearGradient` written `lineargradient` is not that element and the shape it filled draws in flat colour or not at all",
    "xhtml.dtd-entities-resolved": "{count} entity/entities declared in the document's own DTD were resolved",
    "xhtml.dtd-entities-refused": "{count} entity/entities were left as references rather than resolved",
    "xhtml.watermark-consolidated": "{count} watermark marker(s) across {documents} document(s) became one rule",
    "xhtml.watermark-relocated": "{count} watermark marker(s) across {documents} document(s) moved out of the text into document metadata",
    "xhtml.watermark-removed": "{count} watermark marker(s) across {documents} document(s) were deleted at your request",
    "xhtml.watermark-kept": "{count} visible watermark notice(s) were left exactly as the publisher wrote them",
    "xhtml.watermark-kept-personal-data": "{count} visible watermark notice(s) carrying personal data were left exactly as the publisher wrote them",
    "xhtml.ids-renamed": "{count} id attribute(s) were not valid XML names and were renamed",
    "xhtml.document-language-kept": "the document says it is written in {document} and the publication says {publication}; the document was believed, because a book with two languages in it is a book and not a mistake",
    "package.budget-exceeded": "this book asks for more than one book is allowed: {limit} came to {found} where {allowed} is the ceiling, so nothing was written",
    "decisions.store-unusable": "the answers recorded for this book could not be used: {reason}",
    "package.metadata-corrected": "{field} was read out of a damaged package as \"{before}\" and a person corrected it to \"{after}\"",
    "render.checked": "{count} page comparison(s) in {engine}: the rebuilt book draws the same as the source",
    "render.page-lost-content": "this page has less on it after the rebuild than the source had — {detail}",
    "render.page-changed": "this page draws differently and has as much on it as before: {detail}",
    "render.cannot-run": "the appearance check did not run, because no Chromium-based browser was found. This verification is required before a rebuilt book can be called unchanged, and you may decline it knowingly: install Chrome, Chromium or Edge, point {variable} at one you already have, or turn the check off on purpose",
    "package.metadata-unconfirmed": "{fields} came out of a package document that only parsed after recovery, so each is this program's parser reading somebody else's book rather than what the publisher wrote — and nobody was there to confirm or correct them. Nothing was written: answer the questions, or set the policy to accept reconstructed metadata if that is what you want for a batch",
    "package.cancelled": "this rebuild was stopped on request. Nothing was written, and any file already at the destination is exactly as it was",
    "hyphens.class-left-alone": "{count} word(s) in the '{confidence}' class were left exactly as the file has them: this book never writes them without a hyphen, so there is no evidence either way, and that was answered for the whole class at once",
    "package.balance-unexplained": "the input→output balance does not close: {detail}. Something the source had is not in the output and nothing in the change ledger accounts for it — which is the one thing this program must never do quietly",
    "render.unverified-accepted": "the appearance check did not run — no Chromium-based browser was found — and the book was written anyway, because that was chosen rather than assumed. Nothing here has compared the rebuilt pages against the source: install a browser or point {variable} at one, and run it again to have that comparison",
    "render.evidence-unwritten": "the before/after pictures could not be saved beside the book: {error}",
    "hyphens.detected": "{confirmed} word(s) carry a hyphen this book itself spells without one, and a further {likely}+{uncertain} carry one that might be the author's; nothing was joined without being asked",
    "hyphens.joined": "{count} word(s) were joined, each one answered for individually",
    "hyphens.left-alone": "{count} word(s) with a hyphen inside them were left exactly as the file has them, because nobody was asked or nobody answered",
    "hyphens.reverted": "{count} document(s) came out of the hyphen pass with more changed than the words agreed to, so they went back exactly as they came in",
    "package.memory-refused": "this book is expected to need about {needed} of memory ({text} of it text, which costs several times its size once parsed) and the budget here is {budget}; nothing was written, because the alternative is being killed halfway with no report at all",
    "font.obfuscation-declared": "{count} font(s) could not be turned back into plain files, so the container still declares them as obfuscated: bytes no reading system can use must not go out wearing the media type of a font that works",
    "package.not-written": "the rebuilt book could not be written where it was asked to go: {error}. The source is untouched and every other book in this run is unaffected",
    "package.invariant-failed": "{count} thing(s) about the rebuilt book are not true, so nothing was written: {detail}",
    "structure.reference-bearing-kept": "a {media_type} file links to {count} other file(s) in this book ({names}) and nothing here can rewrite those links, so it was left exactly where the publisher put it rather than moved to a file that no longer exists",
    "xhtml.fragment-unresolved": "{count} link(s) name an anchor their target document does not have ({examples}); the reference was left exactly as the publisher wrote it, because nothing here knows where it was meant to lead and a footnote marker that silently arrives at the wrong footnote is worse than one a reader can see is broken",
    "xhtml.fragment-repointed": "{count} link(s) whose anchor was missing were given a new one, chosen by the person running the rebuild",
    "package.unresolved-references": "{count} link(s) name an anchor no document has ({examples}), and strict mode does not publish a book whose references it cannot honestly resolve; nothing was written",
    "xhtml.encoding-mended": "this document said it was in one encoding and its bytes were in another ({encoding}); it was read as what it is rather than parsed with the difference substituted away, which is how a character of a book disappears without anybody being told",
    "xhtml.document-language-corrected": "the document said it was written in {was} and its own text is plainly Polish, so it now says {now}; a reading system speaks this attribute to its voice and hyphenates by it",
    "xhtml.duplicate-ids-renamed": "{count} id attribute(s) appeared more than once in the same document ({names}); the first of each keeps its name and the later ones were renamed, so every existing link still lands where it did",
    "nav.unspined-target-added": "the table of contents led to {count} document(s) the reading order did not hold ({names}); each was added to it as linear=\"no\", which is reachable from the contents without page-turning ever arriving there",
    "css.direction-default-removed": "{count} declaration(s) set the text direction a style sheet already has; EPUB 3 does not allow the property there and this one said nothing, so it was removed",
    "css.direction-kept": "{count} declaration(s) set a text direction the page depends on ({declarations}); EPUB 3 says the markup should carry it instead, and they were kept rather than have the page come out mirrored",
    "xhtml.head-added": "a missing <head> element was added",
    "xhtml.body-added": "a missing <body> element was added",
    "xhtml.dead-reference-kept": "{count} reference(s) point at files not in the book and were left unchanged",
    "xhtml.dead-reference-neutralised": "{count} reference(s) to files absent from the book were neutralised",
    "xhtml.dead-fragment-dropped": "{count} link(s) pointed at an anchor no document defines and were sent to the top of the target document instead, because the person running the rebuild said that is where they belong",
    "xhtml.presentational-markup-converted": "legacy presentational markup was converted to CSS",
    "xhtml.head-flow-hidden": "{count} element(s) sat inside <head>, where an XML parser leaves them and no reader draws them; they were moved into the body and kept out of the drawing, so the page looks exactly as it did",
    "css.style-junk-removed": "{count} of {total} rule(s) in this document's <style> block — {share}% of it — were a converter's leftovers matching nothing in the book, and were removed",
    "css.sheet-junk-removed": "{count} of {total} rule(s) in this stylesheet — {share}% of it — were a converter's leftovers matching nothing in the book, and were removed",
    "footnotes.linked": "{count} bare footnote marker(s) [N] were joined to their notes with links; the text is unchanged to the character",
    "footnotes.found": "{count} bare footnote marker(s) [N] match notes in the notes section and were left as they were",
    "css.classes-renamed": "{count} converter-named class(es) were renamed to the epubforge dictionary (names in: {language}); the detail carries the full old-to-new map",
    "css.class-translation-scripted": "this book carries a script, which may hold class names in strings; no class was renamed",
    "css.class-translation-attr-selector": "this book's CSS reaches classes through attribute selectors; no class was renamed",
    "css.class-translation-unverified": "renaming left a stylesheet that no longer parses as the same sheet, so no class was renamed",
    "css.page-plumbing-removed": "{count} declaration(s) `page: …` — a converter's print plumbing, applied by no reading system to reflowing text — were removed, taking {rules} rule(s) left empty with them",
    "css.page-plumbing-found": "{count} declaration(s) `page: …` — print plumbing no reading system applies — were left as they were and only counted",
    "css.page-plumbing-unverified": "removing {count} `page: …` declaration(s) left something that no longer parses as the same stylesheet, so nothing was touched",
    "css.style-unmatched-kept": "{count} unreachable rule(s) in this document's <style> block resemble no generator's naming and were left as they were",
    "css.malformed-declaration-dropped": "{count} declaration(s) were written the way an HTML attribute is written — {names} — which no reader has ever applied, and were dropped so the file conforms",
    "css.malformed-declaration-kept": "{count} declaration(s) use = where CSS wants a colon; removing them left something that no longer parses as CSS, so they were kept",
    "css.comment-shield-removed": "{count} HTML-era comment-shield token(s) around the stylesheet's rules were removed; every CSS parser since 1997 was already ignoring them",
    "css.mend-unverified": "after all its repairs this stylesheet no longer read as CSS to the full parser, so every repair was handed back and the text is exactly the source's",
    "css.duplicate-properties-removed": "{count} declaration(s) repeating a property inside one block were removed; each was proved unable to win against the occurrence that stays",
    "css.duplicate-properties-resolved": "{count} duplicate declaration(s) with mixed !important over different values were resolved to the modern cascade's winner, on a person's word",
    "css.duplicate-properties-kept": "{count} in-block duplicate declaration(s) may be a fallback an older reader still uses, and were left exactly where they stood",
    "css.duplicate-properties-found": "{count} declaration(s) repeat a property inside one block; they were left as they were and only counted",
    "css.duplicate-properties-unverified": "removing {count} in-block duplicate declaration(s) left something that no longer parses as the same stylesheet, so nothing was touched",
    "css.reformatted": "a sheet packing {rules} rules onto {lines} line(s) was rewritten one declaration per line; every character outside whitespace is identical",
    "css.single-line-found": "a sheet packs {rules} rules onto {lines} line(s); it was left as it was and only counted",
    "css.reformat-unverified": "the readable rewrite did not hand back the same characters, so nothing was touched",
    "css.shorthand-overrides-removed": "{count} longhand declaration(s) standing before a shorthand that resets their slot were removed; the shorthand was already discarding them in every parser",
    "css.shorthand-overrides-kept": "{count} longhand-before-shorthand pair(s) could not be proved dead — the shorthand's value is one a validator may reject, or importance protects the longhand — and stand exactly where they stood",
    "css.shorthand-overrides-found": "{count} longhand declaration(s) stand before a shorthand that resets their slot; they were left as they were and only counted",
    "css.shorthand-overrides-unverified": "removing {count} overridden longhand(s) left something that no longer parses as the same stylesheet, so nothing was touched",
    "css.specificity-reordered": "{count} rule(s) standing below a more specific selector sharing their key were moved above it; every winner order could decide was proved unchanged, by element type or by this book's documents",
    "css.specificity-resolved": "{count} rule(s) held below their place by a tie the book confirms were moved past the contested road, on a person's word; the gate's count strictly fell",
    "css.specificity-kept": "{count} descending-specificity finding(s) remain where a move could not be proved harmless, and the rules stand exactly where the publisher put them",
    "css.specificity-found": "{count} selector(s) stand below a more specific selector sharing their key; they were left as they were and only counted",
    "css.specificity-unverified": "reordering {count} rule(s) did not hand back the same rules to the byte, so nothing was touched",
    "css.empty-noise-removed": "{count} empty comment(s), empty rule(s) and empty at-rule(s) were removed ({comments} comment(s), {rules} rule(s)); they said nothing and every parser was ignoring them",
    "css.empty-noise-found": "{count} empty comment(s), rule(s) or at-rule(s) were left as they were and only counted",
    "css.empty-noise-unverified": "removing {count} empty construct(s) left something that no longer parses as the same stylesheet, so nothing was touched",
    "css.duplicate-selectors-merged": "{count} rule(s) repeating an earlier selector were folded into the selector's last occurrence; every cascade winner stays the same, which is the condition the fold was proved against",
    "css.duplicate-selectors-resolved": "{count} repeated-selector rule(s) the cascade could not release were folded past the contested road, on a person's word",
    "css.duplicate-selectors-kept": "{count} rule(s) repeat a selector in a way whose merge the cascade does not provably allow, and were left exactly where they stood",
    "css.duplicate-selectors-found": "{count} rule(s) repeat an earlier selector; they were left as they were and only counted",
    "css.duplicate-selectors-unverified": "folding {count} repeated-selector rule(s) left something that no longer parses as the same stylesheet, so nothing was touched",
    "css.unknown-properties-removed": "{count} declaration(s) of properties CSS does not have ({names}) were removed, taking {rules} rule(s) left empty with them; every conforming parser was already dropping them",
    "css.unknown-properties-found": "{count} declaration(s) of properties CSS does not have were left as they were and only counted",
    "css.unknown-properties-unverified": "removing {count} declaration(s) of unknown properties left something that no longer parses as the same stylesheet, so nothing was touched",
    "css.malformed-declaration-enabled": "{count} declaration(s) written with = instead of a colon — {names} — bore no converter's signature and were enabled at a person's word: the = became a colon and the formatting now applies",
    "css.malformed-declaration-left": "{count} declaration(s) written with = instead of a colon bear no converter's signature and were left as they were — reading systems keep ignoring them",
    "xhtml.image-paragraph-centred": "{count} image-only paragraph(s) were centred and their text indent removed",
    "xhtml.image-paragraph-centred-unstyled": "{count} image-only paragraph(s) on a page that links no stylesheet were centred",
    "xhtml.cover-sized-in-pixels": "the cover image is sized in pixels by an attribute, and was left that way",
    "package.text-lost": "text from the source is missing from the rebuild, so nothing was written",
    "package.text-check-per-rendition": "the container holds more than one publication, so the text invariant was not checked across the whole of it",
    "hyphens.no-dictionary": "no {language} dictionary was available, so hyphens were judged on this book's own vocabulary alone",
    "package.text-changed-on-request": "text left the book because you asked for it ({rules}), so the character-for-character invariant no longer holds",
    "package.text-check-failed": "the text invariant could not be measured on this book",
    "xhtml.image-paragraph-unindented": "a running-text indent was removed from {count} image paragraph(s)",
    "xhtml.image-paragraph-kept": "{count} image paragraph(s) were left as the publisher styled them",
    "xhtml.cover-fitted": "the cover image was given page-fitting limits, because nothing in the book set any",
    "xhtml.inline-promoted": "{count} inline element(s) containing block-level content were promoted",
    "xhtml.cover-described": "the cover image was described with the book title",
    "xhtml.empty-alt-added": "an empty alt attribute was added to {count} image(s)",
    "xhtml.scripts-kept": "{count} script element(s) were kept and the document was declared scripted",
    "xhtml.scripts-removed": "{count} script element(s) and {handlers} inline handler(s) were removed",
    # -- metadata -----------------------------------------------------------
    "metadata.override-applied": "the caller overrode the metadata field {field}",
    "metadata.title-missing": "the source has no dc:title and a placeholder was inserted",
    "metadata.titles-collapsed": "{count} dc:title elements were collapsed to one main title",
    "metadata.language-invalid": "the language tag {was} is not valid BCP 47 and was replaced with {now}",
    "metadata.language-corrected": "the declared language {was} is contradicted by the text; corrected to {now}",
    "metadata.language-missing": "the source has no dc:language, so {now} was used",
    "metadata.identifier-minted": "the source has no dc:identifier and a UUID was minted",
    "metadata.identifier-promoted": "no unique-identifier was declared and the first one was promoted",
    "metadata.date-normalised": "dc:date was normalised to ISO 8601: {was} became {now}",
    "metadata.date-unparseable": "dc:date {was} could not be parsed and was dropped",
    "metadata.creator-missing": "the source names no dc:creator",

    # -- images -------------------------------------------------------------
    "image.pillow-unavailable": "Pillow is not installed, so images passed through unchecked",
    "image.unreadable": "an image could not be decoded and was kept as it was: {error}",
    "image.type-corrected": "a file is really {actual} though it was declared {declared}",
    "image.type-kept": "{media_type} is not a core EPUB 3 type but was kept by policy",
    "image.renamed": "a file was renamed to .{suffix}, the format it really is",
    "image.transcode-failed": "transcoding failed and the original was kept: {error}",
    "image.transcoded": "an image was transcoded from {media_type} to PNG for universal reader support",
    "image.animation-kept": "a {media_type} image holding {frames} frames was left exactly as it was: converting it would have kept the first frame and silently dropped the rest",

    # -- fonts --------------------------------------------------------------
    "font.type-corrected": "a font's media type was corrected to {actual}, from the declared {declared}",
    "font.unrecognised": "a font has no recognisable signature",
    "font.drm": "the content is DRM-encrypted and the rebuild cannot proceed safely",
    "font.obfuscation-kept": "font obfuscation was left in place by policy",
    "font.obfuscation-unkeyed": "fonts are obfuscated but the package has no identifier to key on",
    "font.deobfuscation-failed": "deobfuscation did not yield a valid font, so the file was left alone",
    "font.deobfuscated": "{count} embedded font(s) were deobfuscated and the encryption file dropped",

    # -- compatibility profiles ---------------------------------------------
    "compat.unknown-profile": "the compatibility profile {profile} does not exist and was ignored",
    "compat.applied": "compatibility profiles were applied: {profiles}",
    "compat.legacy-font-types": "{count} embedded font(s) are declared by the media type Adobe RMSDK knows, not the one EPUB 3.3 registers",
    "compat.ncx-required": "a selected profile needs the legacy NCX, which was switched off",
    "compat.stylesheet-added": "{stylesheet} was linked into {count} document(s)",
    "compat.page-break-mirrored": "{count} fragmentation declaration(s) were mirrored into page-break-*",
    "compat.specified-fonts-skipped": "the book embeds no fonts, so the Apple declaration was skipped",
    "compat.specified-fonts-added": "specified-fonts was declared for Apple Books",
    "compat.guide-skipped": "nothing in the book maps onto a legacy <guide>",
    "compat.guide-added": "the EPUB 2 <guide> element was added for readers that look for it",
    "compat.svg-cover": "the cover page wraps its image in SVG, which some converters mishandle",

    # -- accessibility ------------------------------------------------------
    "a11y.conformance-declared": "conformance with {profile} was declared because the caller asserted it",
    "a11y.metadata-added": "EPUB Accessibility 1.1 discovery metadata was added",
    "a11y.missing-alt": "{count} image(s) have no usable alt text",
    "a11y.placeholder-alt": "{count} image(s) have alt text that only repeats the file name",
    "a11y.heading-jump": "heading levels skip a rank in {count} place(s)",
    "a11y.table-without-headers": "{count} table(s) have no header cells",

    # -- package ------------------------------------------------------------
    "package.upgraded": "the package was rebuilt from EPUB {version} to 3.3",
    "package.regenerated": "the source was already EPUB {version} and the package was regenerated anyway",
    "package.layout-kept": "the package document stayed at {path}, because the files around it did not move",
    "package.version-unusable": "the package declared no usable version and was treated as EPUB 2",
    "package.unreadable-source": "the source file could not be read: {error}",
    "package.stage-broke-its-word": "the {stage} stage says it only measures the book and it changed it, so nothing was written: every other claim this run made rests on the same kind of promise",
    "package.stage-failed": "the {stage} stage raised, so nothing was written: {error}",
    "package.input-incomplete": "{count} entry(ies) of the source could not be read ({names}), so nothing was written; a rebuild that cannot see part of the book cannot promise to keep it",
    "package.layout-unusable": "the source keeps its package document at {path}, which is not a path this may write ({reason}), so the standard layout was used instead",
    "package.source-protected": "writing over the source file was refused",
    "package.spine-item-vanished": "a spine item was gone by the time the package was written",
    # -- validation ---------------------------------------------------------
    "epubcheck.reported": "EPUBCheck reported {fatal} fatal and {errors} error(s)",
    "epubcheck.clean": "EPUBCheck accepted the output, with {warnings} warning(s)",
    "epubcheck.unavailable": "EPUBCheck is not installed, so the output was not validated",
    "epubcheck.failed": "EPUBCheck could not be run at all: {error}",
    # -- the gate before publication (K.2 invariant 12) ----------------------
    "reader.xml-recovered": "this file is not well-formed XML and was read by a parser guessing at what it meant ({detail}); what came out is a reconstruction rather than what the file says",
    "package.metadata-from-a-guess": "the package document had to be reconstructed, so the book's own description of itself is a guess: check {fields} and correct them if they are wrong",
    "xhtml.reference-relocated": "{count} reference(s) named a path this book does not have, and exactly one file of that name is in it; they point at it now, because a misdirected reference is not a dead one",
    "css.dead-url-neutralised": "{count} stylesheet reference(s) to files not in the book were neutralised — a single image becomes none, a fallback candidate is dropped from its list, and an @font-face left with no source goes with it",
    "css.dead-url-kept": "{count} stylesheet reference(s) point at files not in the book and were left alone, because neutralising them produced a stylesheet that no longer parses",
    "metadata.property-superseded": "{count} metadata statement(s) from the source are not repeated in the output because this rebuild states the same property itself",
    "package.input-lost-detail": "{name} — a {kind} the archive would not give up; the book's own manifest listed it: {declared}; documents pointing at it: {referenced_by}",
    "package.gate-refused": "EPUBCheck calls the rebuilt book invalid ({count} error(s): {detail}) and this mode does not publish an invalid file; nothing was written and whatever was at that name is untouched",
    "package.gate-refused-new": "this rebuild introduced {count} EPUBCheck error(s) the source (version {source_version}) did not have ({detail}); the book was not published, because carrying a book's own defects is one thing and adding to them is another",
    "package.errors-were-already-there": "EPUBCheck calls the book invalid in {count} place(s) and called the source invalid in the same places, so it was published as it arrived; the defects are the publisher's and they are listed in the report",
    "package.gate-cannot-run": "the {gate} gate was asked for and there is no validator to run it, so the book was not published; a gate that passes what it could not check is not a gate",
    "package.gate-skipped": "there is no validator here, so nothing was compared before publication; the rebuild's own invariant gate and read-back still ran",
    # -- the window ---------------------------------------------------------
    "gui.unexpected-failure": "the rebuild failed in a way nothing anticipated: {error}",
}


#: The same catalogue in Polish. Separate mapping rather than a tuple per entry
#: so that adding a language is adding a file-sized block and not editing
#: seventy-seven lines — and `test_rules.py` holds the two to the same key set,
#: because a half-translated catalogue silently falls back to English and looks
#: like a translation that is finished.
CATALOGUE_PL: dict[str, str] = {
    'reader.remote-resource': 'manifest deklaruje zasób trzymany gdzie indziej',
    'reader.dangling-reference': '{attribute} wskazuje na identyfikator, którego manifest nie definiuje',
    'reader.name-rewritten': 'nazwa wpisu w archiwum nie była ścieżką kontenera i została przepisana',
    'reader.name-dropped': 'nazwy wpisu w archiwum nie dało się zamienić na ścieżkę kontenera: {reason}',
    'reader.duplicate-entry': 'archiwum zawiera tę samą nazwę wpisu dwa razy',
    'reader.colliding-names': '{count} {count:nazwa wpisu różni się|nazwy wpisów różnią się|nazw wpisów różni się} tylko przez {kind}',
    'reader.entry-too-large': 'wpis w archiwum jest niewiarygodnie duży i został odrzucony: {reason}',
    'reader.meta-inf-carried': 'zarezerwowany plik kontenera przeniesiono bez zmian: mówi o publikacji coś, czego ta przebudowa nie zmienia',
    'reader.meta-inf-invalidated': 'usunięto podpis cyfrowy albo spis zawartości kontenera, bo przebudowa czyni go nieprawdziwym: podpis liczy się z dokładnych bajtów i nie przetrwa ich zmiany, a zostawiony wyglądałby na dowód manipulacji zamiast na ślad naprawy',
    'reader.meta-inf-unknown-carried': 'obok dokumentu kontenera znaleziono plik, którego ten program nie rozpoznaje — przeniesiono go bez zmian, zamiast go oceniać',
    'reader.manifest-id-duplicated': 'dwie pozycje manifestu mają ten sam identyfikator {id} ({first} i {second}); wpisy spine\u2019a, które go wskazują, mogą znaczyć jedno albo drugie, a ta przebudowa nie wybierze za ciebie',
    'reader.entry-unreadable': 'wpisu w archiwum w ogóle nie dało się odczytać: {error}',
    'reader.rootfile-missing': 'container.xml wskazuje na dokument pakietu, którego nie ma w archiwum',
    'reader.container-missing': 'brakuje META-INF/container.xml, więc pakiet znaleziono przez przeszukanie archiwum',
    'reader.package-scanned': 'dokument pakietu odzyskano, przeszukując archiwum',
    'reader.metadata-missing': 'pakiet nie ma elementu <metadata>',
    'reader.manifest-missing': 'pakiet nie ma elementu <manifest>, więc użyto zawartości archiwum',
    'reader.manifest-file-missing': 'manifest wymienia plik, którego nie ma w archiwum',
    'package.not-readable-again': 'plik został zapisany, a ten program nie potrafi odczytać go z powrotem bez błędu ({detail}); książki, na której potyka się jej własny czytnik, nie podaje się dalej bez zajrzenia',
    'package.refinements-carried': 'przeniesiono {count} {count:uściślenie metadanych, dla którego|uściślenia metadanych, dla których|uściśleń metadanych, dla których} ten model nie ma własnego pola, i przepięto {count:je|je|je} na identyfikatory, które przebudowany pakiet nadaje tym węzłom',
    'package.refinements-unanchored': '{count} {count:uściślenie metadanych wskazywało|uściślenia metadanych wskazywały|uściśleń metadanych wskazywało} węzeł, który nie przetrwał przebudowy — usunięto zamiast zapisać wskazujące donikąd',
    'package.renditions-written': 'przebudowano {count} {count:wersję publikacji|wersje publikacji|wersji publikacji}, każdą do osobnego pliku ({names})',
    'reader.other-rendition-skipped': '{count} {count:plik należy|pliki należą|plików należy} do innej wersji publikacji z tego kontenera i {count:został zostawiony|zostały zostawione|zostało zostawionych} jej własnemu wynikowi; każda wersja jest przebudowywana do osobnego pliku, więc w komplecie nic nie brakuje',
    'reader.renditions-offered': 'ten kontener oferuje {count} {count:wersję|wersje|wersji} publikacji ({names}) — osobne publikacje tego samego dzieła, każda z własnym manifestem i kolejnością czytania; ta książka to jedna z nich',
    'reader.manifest-spelling-matched': 'manifest wskazuje plik, którego archiwum nie ma dokładnie pod tą nazwą, a ma pod inną jej pisownią ({how}); użyto {found}, bo o tym, który plik był wskazywany, rozstrzyga archiwum',
    'reader.manifest-case-matched': 'wpis manifestu pasował do pliku dopiero po pominięciu wielkości liter',
    'reader.manifest-type-corrected': 'manifest deklarował {declared}, czym plik nie jest; poprawiono na {actual}',
    'reader.spine-missing': 'pakiet nie ma elementu <spine>',
    'reader.spine-id-unknown': 'kolejność czytania wskazywała na nieistniejący identyfikator w manifeście',
    'reader.ncx-unparseable': 'starego NCX nie dało się sparsować',
    'reader.nav-unparseable': 'dokumentu nawigacyjnego nie dało się sparsować',
    'reader.encryption-unparseable': 'pliku META-INF/encryption.xml nie dało się sparsować',
    'reader.drm': 'archiwum deklaruje prawdziwe szyfrowanie, a nie samo zaciemnienie czcionek',
    'reader.mimetype-invalid': 'wpis mimetype jest nieobecny albo błędny i zostanie zapisany od nowa',
    'reader.page-direction-carried': 'kierunek czytania to {direction} i został przeniesiony bez zmian',
    'reader.toc-from-ncx': 'spis treści odzyskano ze starego NCX',
    'reader.ncx-unreferenced-used': 'znaleziono NCX, do którego nic się nie odwoływało, i użyto go jako spisu treści',
    'reader.unmanifested-file': 'plik jest w archiwum, ale nie ma go w manifeście',
    'reader.spine-rebuilt': 'kolejność czytania była pusta i odtworzono ją z {count} {count:dokumentu treści|dokumentów treści|dokumentów treści}',
    'structure.role-named': '{count} {count:dokument dostał nazwę|dokumenty dostały nazwy|dokumentów dostało nazwy} z roli — cover, toc, chapter-NN z -2/-3 dla rozdziału pociętego na pliki ({examples}); dokumenty bez dowodu roli zostają przy starej nazwie',
    'structure.relaid-out': '{count} {count:plik przegrupowano|pliki przegrupowano|plików przegrupowano} w układ według typów w {directory}/, z przenośnymi nazwami',
    'structure.junk-removed': 'usunięto pozostałości po pakowaniu',
    'structure.junk-kept': 'ten plik nazywa się jak pozostałość po pakowaniu, ale książka się do niego odwołuje, więc został: nazwa nie jest dowodem o treści, a `.bak` to nazwa, jaką wydawca może dać rozdziałowi',
    'structure.orphan-removed': 'usunięto plik, do którego nic w książce się nie odwołuje',
    'structure.carried-xml-repointed': 'przepięto {count} {count:odwołanie|odwołania|odwołań} wewnątrz pliku przenoszonego bez zmian',
    'nav.regenerated': 'dokument nawigacyjny wygenerowano od nowa, z {count} {count:pozycją|pozycjami|pozycjami}',
    'nav.generated': 'książka nie miała dokumentu nawigacyjnego i został utworzony, z {count} {count:pozycją|pozycjami|pozycjami}',
    'nav.contents-page-kept': 'zachowano stronę spisu treści wydawcy, a wygenerowaną nawigację umieszczono obok',
    'nav.entries-repointed': '{count} {count:pozycja spisu treści prowadziła|pozycje spisu treści prowadziły|pozycji spisu treści prowadziło} do jednego rozplątanego identyfikatora; przepięte po kolejności w dokumencie, na słowo osoby',
    'nav.duplicate-target-found': '{count} {count:pozycja spisu treści prowadzi|pozycje spisu treści prowadzą|pozycji spisu treści prowadzi} w to samo miejsce; {count:zostawiona|zostawione|zostawionych} bez zmian',
    'nav.repointed': 'przepięto {count} {count:odwołanie|odwołania|odwołań} do zastąpionego dokumentu nawigacyjnego',
    'nav.landmarks-deduplicated': '{count} {count:punkt orientacyjny wskazywał|punkty orientacyjne wskazywały|punktów orientacyjnych wskazywało} to samo miejsce po raz drugi; powtórzenia usunięto',
    'nav.sections-carried': '{count} {count:sekcję nawigacji, której|sekcje nawigacji, których|sekcji nawigacji, których} ten program nie modeluje z nazwy ({names}), przeniesiono do wygenerowanej nawigacji razem z wpisami i z ich epub:type',
    'reader.nav-sections-found': 'dokument nawigacyjny zawiera {count} {count:sekcję|sekcje|sekcji} poza spisem treści, punktami orientacyjnymi i listą stron ({names})',
    'nav.fragment-carried': '{count} {count:odwołanie do zastąpionego dokumentu nawigacyjnego zachowało|odwołania do zastąpionego dokumentu nawigacyjnego zachowały|odwołań do zastąpionego dokumentu nawigacyjnego zachowało} swoją kotwicę, bo sekcja, którą wskazywała, ma odpowiednik w dokumencie wygenerowanym',
    'nav.kept-in-spine': 'dokument nawigacyjny został w kolejności czytania, tam gdzie miało go źródło',
    'nav.entry-dropped': '{count} {count:pozycja spisu treści wskazywała|pozycje spisu treści wskazywały|pozycji spisu treści wskazywało} na coś, czego nie ma',
    'nav.fragment-cleared': '{count} {count:kotwica nawigacyjna nie istnieje|kotwice nawigacyjne nie istnieją|kotwic nawigacyjnych nie istnieje}, więc pozycje wskazują teraz na sam dokument',
    'nav.toc-synthesised': 'książka nie miała używalnego spisu treści; zbudowano go z {count} {count:dokumentu|dokumentów|dokumentów} kolejności czytania',
    'nav.cover-page-generated': 'wygenerowano stronę okładki, żeby grafika była pierwsza w kolejności czytania',
    'nav.ncx-written': 'zapisano stary plik NCX obok dokumentu nawigacyjnego, dla starszych czytników',
    'nav.ncx-dropped': 'stary plik NCX nie został przeniesiony; EPUB 3 nawiguje dokumentem nawigacyjnym',
    'nav.cover-image-missing': 'zadeklarowany obraz okładki nie znajduje się w archiwum',
    'xhtml.untouched': 'dokumenty treści zostały bez zmian; przebudowano wyłącznie kontener',
    'xhtml.untouched-except-doctype': 'dokumenty treści zostały bez zmian poza DOCTYPE; przebudowano wyłącznie kontener',
    'xhtml.doctype-modernised': 'stary DOCTYPE zastąpiono tym z EPUB 3 w {count} {count:dokumencie|dokumentach|dokumentach}',
    'xhtml.orphaned-styling-restored': '{count} {count:klasie|klasom|klasom}, których dokument używa, a nie definiuje ich żaden podpięty do niego arkusz, przywrócono własną regułę wydawcy: {classes}',
    'xhtml.empty-span-found': '{count} {count:element <span>, którego reguły nic nie mówią|elementy <span>, których reguły nic nie mówią|elementów <span>, których reguły nic nie mówią} — ślad konwersji; zostają',
    'xhtml.empty-span-unwrapped': 'rozwinięto {count} {count:element <span>|elementy <span>|elementów <span>}, których reguły nic nie mówiły; tekst w środku nietknięty',
    'xhtml.epub2-only-markup': 'znaczniki dozwolone w EPUB 2, a niedozwolone w EPUB 3, zostają w tym trybie nietknięte: {what}',
    'xhtml.title-filled': '{count} {count:pustemu elementowi|pustym elementom|pustym elementom} <title> nadano nagłówek samego dokumentu',
    'xhtml.doctype-kept': '{count} {count:dokument zachowuje|dokumenty zachowują|dokumentów zachowuje} stary DOCTYPE, bo encji nie da się rozwiązać: {documents}',
    'xhtml.entities-rewritten': 'niezadeklarowane encje nazwane przepisano na referencje numeryczne',
    'xhtml.property-withdrawn': 'wycofano właściwości manifestu, których dokument nie potwierdza: {properties}',
    # -- profile -------------------------------------------------------------
    'typography.ellipsis-normalised': '{count} {count:ciąg trzech kropek stał się|ciągi trzech kropek stały się|ciągów trzech kropek stało się} pojedynczym wielokropkiem',
    'typography.conjunctions-bound': '{count} {count:jednoliterowy spójnik związano|jednoliterowe spójniki związano|jednoliterowych spójników związano} z następującym po nim słowem',
    'typography.quotes-retyped': '{count} {count:prosty cudzysłów przepisano|proste cudzysłowy przepisano|prostych cudzysłowów przepisano} na własną konwencję książki ({convention})',
    'typography.quotes-unsettled': 'książka nie ustaliła jednej konwencji cudzysłowu, więc zostawiono je bez zmian',
    'typography.reverted': '{count} {count:dokument przywrócono|dokumenty przywrócono|dokumentów przywrócono} bez zmian: przebieg typograficzny nie potrafił wykazać, że zachował tekst',
    'profile.made-by': 'książka nosi ślady {count} {count:narzędzia|narzędzi|narzędzi}: {tools}',
    'profile.body-text-found': 'tekst główny to {shape}: {percent}% z {blocks} {blocks:akapitu|akapitów|akapitów}',
    'profile.body-text-inconsistent': 'żaden kształt nie obejmuje tekstu głównego; najczęstszy sięga {percent}% z {blocks} {blocks:akapitu|akapitów|akapitów}',
    'profile.paragraphs-mixed': 'akapity oddzielane są na oba sposoby: {indented} wcięciem, {spaced} odstępem',
    'profile.paragraphs-consistent': 'akapity oddzielane są konsekwentnie ({paradigm})',
    'profile.dead-classes-found': '{count} {count:klasa jest zadeklarowana|klasy są zadeklarowane|klas jest zadeklarowanych} w CSS i {count:nie używa jej nic|nie używa ich nic|nie używa ich nic}',
    'profile.duplicate-classes-found': '{names} {names:klasa w|klasy w|klas w} {groups} {groups:grupie deklaruje|grupach deklaruje|grupach deklaruje} dokładnie to samo',
    'profile.scene-separators-found': 'znaleziono {count} {count:separator scen|separatory scen|separatorów scen}',
    'profile.break-runs-found': '{count} {count:ciąg <br/> zastępuje|ciągi <br/> zastępują|ciągów <br/> zastępuje} przerwę akapitową',
    'profile.heading-candidates-found': '{count} {count:akapit wygląda jak nagłówek|akapity wyglądają jak nagłówki|akapitów wygląda jak nagłówki}, nie będąc nim oznaczone',
    # -- stylesheets --------------------------------------------------------
    'css.url-unresolved': '{count} {count:odwołania url() nie dało się rozwiązać|odwołań url() nie dało się rozwiązać|odwołań url() nie dało się rozwiązać} i zostały bez zmian',
    'css.remote-import-removed': 'usunięto {count} {count:regułę @import pobierającą arkusz stylów z sieci|reguły @import pobierające arkusz stylów z sieci|reguł @import pobierających arkusz stylów z sieci}',
    'xhtml.remote-import-removed': 'usunięto z elementu <style> {count} {count:regułę @import pobierającą arkusz stylów z sieci|reguły @import pobierające arkusz stylów z sieci|reguł @import pobierających arkusz stylów z sieci}',
    'css.vendor-at-rule-kept': 'zachowano {count} {count:regułę @|reguły @|reguł @} charakterystyczną dla konkretnych czytników',
    'css.kindle-media-removed': 'usunięto bloki @media przeznaczone dla Kindle',
    'xhtml.forbidden-characters-removed': 'usunięto z tego dokumentu {count} {count:znak sterujący, którego|znaki sterujące, których|znaków sterujących, których} XML nie potrafi zapisać',
    'xhtml.mojibake-translated': 'przywrócono {count} {count:znak przestankowy zamieniony|znaki przestankowe zamienione|znaków przestankowych zamienionych} przez konwersję w kod bez kształtu: {what}',
    'xhtml.mojibake-found': '{count} {count:znak przestankowy siedzi|znaki przestankowe siedzą|znaków przestankowych siedzi} tu jako kod bez kształtu i {count:został|zostały|zostało} nietknięte: {what}',
    'xhtml.mojibake-reverted': 'naprawa interpunkcji została w tym dokumencie zdjęta, bo nie doszła do końca: {detail}',
    'xhtml.watermark-reverted': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} zostawiono w tym dokumencie, bo wyjęcie ich nie wyszło: {detail}',
    'package.forbidden-characters-removed': 'usunięto znaki sterujące, których XML nie potrafi zapisać, z pól: {fields}',
    'xhtml.shop-notice-removed': 'usunięto na życzenie {count} {count:zdanie księgarni|zdania księgarni|zdań księgarni} z {documents} {documents:dokumentu|dokumentów|dokumentów}: {removed}',
    'css.invalid-value-corrected': 'poprawiono {count} {count:deklarację|deklaracje|deklaracji} z niepoprawną wartością „regular”',
    'css.invalid-value-inherited': 'zostawiono {count} {count:deklarację|deklaracje|deklaracji} z niepoprawną wartością „regular”, bo ten arkusz ustawia też kursywę albo pogrubienie',
    'css.absolute-units': '{count} {count:rozmiar czcionki jest podany|rozmiary czcionek są podane|rozmiarów czcionek jest podanych} w jednostkach absolutnych, więc ustawienie czcionki w czytniku ich nie ruszy',
    'css.absolute-units-relativised': 'przepisano {count} {count:absolutny rozmiar czcionki|absolutne rozmiary czcionek|absolutnych rozmiarów czcionek} na rem, więc ustawienie czcionki w czytniku do nich sięga',
    'css.absolute-units-rooted': 'zachowano {count} {count:absolutny rozmiar czcionki|absolutne rozmiary czcionek|absolutnych rozmiarów czcionek}: ten arkusz ustawia w pikselach rozmiar elementu głównego, więc przepisanie reszty niczego by nie uwolniło',
    'css.unreachable-rules-found': '{count} z {total} {count:reguła nazywa|reguły nazywają|reguł nazywa} klasę lub id, których nie ma nigdzie w książce — {share}% tego arkusza',
    'css.unreachable-rules-removed': 'usunięto {count} z {total} {count:regułę|reguły|reguł} nazywającą klasę lub id, których nie ma nigdzie w książce — {share}% tego arkusza',
    'css.unreachable-rules-scripted': '{count} {count:reguła nie pasuje|reguły nie pasują|reguł nie pasuje} dziś do niczego i zostaje, bo książka niesie skrypt',
    'css.unreachable-rules-unverified': '{count} {count:reguła wygląda|reguły wyglądają|reguł wygląda} na nieosiągalne, ale arkusz nie przeszedł kontroli, więc został bez zmian',
    'css.position-kept': 'zachowano {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego',
    'css.position-kept-reflowable': 'zachowano {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego w książce przepływalnej',
    'css.position-contained': '{count} {count:reguła pozycjonowania poza przepływem jest trzymana|reguły pozycjonowania poza przepływem są trzymane|reguł pozycjonowania poza przepływem jest trzymanych} wewnątrz pozycjonowanego przodka w {documents} {documents:dokumencie|dokumentach|dokumentach} i zostały zachowane',
    'xhtml.position-pinned-in-flow': 'treść przypiętą do stopki strony przetłumaczono na odpowiednik działający w przepływie',
    'css.position-superseded': 'pozycjonowanie poza przepływem jest zastąpione w {count} {count:dokumencie|dokumentach|dokumentach} odpowiednikiem wpisanym do nich',
    'css.position-removed': 'usunięto {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego z książki przepływalnej',
    'css.reader-property-kept': 'zachowano {count} {count:właściwość CSS|właściwości CSS|właściwości CSS} charakterystyczną dla czytników — profil zgodności legacy mówi, że ta książka ma działać na czytnikach RMSDK ({names})',
    'css.reader-property-removed': 'usunięto {count} {count:właściwość CSS|właściwości CSS|właściwości CSS} charakterystyczną dla czytników',
    'css.font-stack-generic-added': '{count} {count:stos czcionek dostał|stosy czcionek dostały|stosów czcionek dostało} generyczną rodzinę, którą osadzona czcionka deklaruje o sobie sama',
    'css.font-stack-generic-approved': '{count} {count:stos fontów wskazujący|stosy fontów wskazujące|stosów fontów wskazujących} kroje spoza paczki {count:dostał|dostały|dostało} rodzinę zapasową z powszechnej wiedzy ({generics}) — dopisaną na słowo człowieka',
    'css.font-stack-generic-missing': '{count} {count:lista krojów kończy się|listy krojów kończą się|list krojów kończy się} bez rodziny generycznej',
    'css.unparseable': 'arkusza stylów nie dało się sparsować do sprawdzenia: {error}',
    'css.no-usable-rules': 'arkusz stylów nie zawiera żadnych używalnych reguł',
    'xhtml.unparseable': 'dokumentu treści w ogóle nie dało się sparsować: {error}',
    'xhtml.recovered-with-html-parser': 'ten dokument nie był poprawnym XML-em i musiał zostać zrekonstruowany parserem HTML, co jest zgadywaniem, o co wydawcy chodziło, a nie naprawą o znanym wyniku',
    'metadata.modified-pinned-to-epoch': 'ta książka nie niesie ani daty modyfikacji, ani daty wydania, więc budowanie reprodukowalne wstawiło epokę, zamiast wymyślać datę wyglądającą wiarygodnie',
    'xhtml.html-source-parsed': 'źródło deklaruje ten dokument jako HTML, a nie XHTML, więc odczytano go parserem HTML — co jest właściwym odczytem, a nie odzyskiwaniem — i zapisano jako XHTML',
    'xhtml.stylesheet-pi-converted': '{count} {count:arkusz stylów podpięty|arkusze stylów podpięte|arkuszy stylów podpiętych} instrukcją <?xml-stylesheet?> ({names}) {count:jest teraz podpięty|są teraz podpięte|jest teraz podpiętych} przez <link rel="stylesheet">, czyli tak, jak mówi EPUB 3; sama instrukcja jest tu niedozwolona i wcześniej znikała, a w jej miejsce nie wchodziło nic',
    'xhtml.svg-case-restored': '{count} {count:nazwie SVG|nazwom SVG|nazwom SVG}, {count:którą|które|które} odzyskiwanie parserem HTML sprowadziło do małych liter, przywrócono poprawną pisownię; SVG rozróżnia wielkość liter, więc `linearGradient` zapisany jako `lineargradient` nie jest tym elementem, a kształt, który nim wypełniono, rysuje się płaskim kolorem albo wcale',
    'xhtml.dtd-entities-resolved': 'rozwiązano {count} {count:encję|encje|encji} zadeklarowaną w DTD samego dokumentu',
    'xhtml.dtd-entities-refused': '{count} {count:encję pozostawiono|encje pozostawiono|encji pozostawiono} jako odwołania zamiast je rozwiązać',
    'xhtml.watermark-consolidated': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} sprowadzono do jednej reguły',
    'xhtml.watermark-relocated': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} przeniesiono z treści do metadanych dokumentu',
    'xhtml.watermark-removed': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} usunięto na Twoje życzenie',
    'xhtml.watermark-kept': '{count} {count:widoczną adnotację|widoczne adnotacje|widocznych adnotacji} znaku wodnego zostawiono dokładnie tak, jak napisał je wydawca',
    'xhtml.watermark-kept-personal-data': '{count} {count:widoczną adnotację|widoczne adnotacje|widocznych adnotacji} znaku wodnego z danymi osobowymi zostawiono dokładnie tak, jak napisał je wydawca',
    'xhtml.ids-renamed': '{count} {count:atrybut id nie był poprawną nazwą XML|atrybuty id nie były poprawnymi nazwami XML|atrybutów id nie było poprawnymi nazwami XML} i zostały przemianowane',
    'xhtml.document-language-kept': 'dokument mówi, że jest napisany w {document}, a publikacja mówi {publication}; uwierzono dokumentowi, bo książka z dwoma językami jest książką, a nie pomyłką',
    'package.budget-exceeded': 'ta książka prosi o więcej, niż wolno jednej książce: {limit} wyszło {found}, a sufit to {allowed} — nic nie zapisano',
    'decisions.store-unusable': 'zapisane odpowiedzi dla tej książki nie nadały się do użycia: {reason}',
    'package.metadata-corrected': '{field} odczytany z uszkodzonego pakietu jako „{before}” i poprawiony przez człowieka na „{after}”',
    'render.checked': '{count} {count:porównanie strony|porównania stron|porównań stron} w {engine}: przebudowana książka rysuje się tak samo jak źródło',
    'render.page-lost-content': 'na tej stronie jest po przebudowie mniej niż było w źródle — {detail}',
    'render.page-changed': 'ta strona rysuje się inaczej, a treści ma tyle samo albo więcej: {detail}',
    'render.cannot-run': 'kontrola wyglądu nie została wykonana, bo nie znalazłem przeglądarki opartej na Chromium. Ta weryfikacja jest obowiązkowa, zanim przebudowaną książkę można nazwać nieuszkodzoną — i możesz z niej świadomie zrezygnować: zainstaluj Chrome, Chromium albo Edge, wskaż zmienną {variable} na tę, którą już masz, albo wyłącz tę kontrolę celowo',
    'package.metadata-unconfirmed': 'pola {fields} pochodzą z pakietu, który dał się sparsować dopiero po odzysku, więc każde z nich jest odczytem parsera z cudzej książki, a nie tym, co napisał wydawca — i nie było komu ich potwierdzić ani poprawić. Nic nie zapisano: odpowiedz na pytania albo ustaw politykę na przyjmowanie odtworzonych metadanych, jeżeli o to chodzi przy wsadzie',
    'package.cancelled': 'ta przebudowa została przerwana na życzenie. Nic nie zapisano, a plik, który już leżał pod tą nazwą, jest dokładnie taki, jaki był',
    'hyphens.class-left-alone': '{count} słowo/słów z klasy „{confidence}” zostało dokładnie tak, jak w pliku: ta książka nigdzie nie pisze ich bez łącznika, więc dowodu nie ma w żadną stronę, a odpowiedź padła raz dla całej klasy',
    'package.balance-unexplained': 'bilans wejście→wyjście się nie zamyka: {detail}. Coś, co było w źródle, nie ma go w wyniku, a żaden wpis w bilansie zmian tego nie tłumaczy — czyli dokładnie to, czego ten program nie ma prawa zrobić po cichu',
    'render.unverified-accepted': 'kontrola wyglądu nie została wykonana — nie znalazłem przeglądarki opartej na Chromium — a książka i tak została zapisana, bo tak zostało wybrane, a nie założone. Nic tutaj nie porównało przebudowanych stron ze źródłem: zainstaluj przeglądarkę albo wskaż ją zmienną {variable} i uruchom jeszcze raz, żeby to porównanie mieć',
    'render.evidence-unwritten': 'nie udało się zapisać obrazów przed/po obok książki: {error}',
    'hyphens.detected': '{confirmed} {confirmed:słowo ma|słowa mają|słów ma} łącznik w środku, choć ta sama książka pisze je bez łącznika; kolejne {likely}+{uncertain} mogą być złożeniami autora — nic nie zostało złączone bez pytania',
    'hyphens.joined': '{count} {count:słowo złączono|słowa złączono|słów złączono}, każde z osobna potwierdzone',
    'hyphens.left-alone': '{count} {count:słowo z łącznikiem zostało|słowa z łącznikiem zostały|słów z łącznikiem zostało} dokładnie tak, jak w pliku — nie było kogo zapytać albo nikt nie odpowiedział',
    'hyphens.reverted': '{count} {count:dokument wyszedł|dokumenty wyszły|dokumentów wyszło} z przebiegu łączników ze zmianą większą niż uzgodniona, więc {count:wrócił|wróciły|wróciło} dokładnie w takiej postaci, w jakiej {count:przyszedł|przyszły|przyszło}',
    'package.memory-refused': 'ta książka będzie potrzebowała około {needed} pamięci ({text} z tego to tekst, a tekst po sparsowaniu kosztuje kilka razy swój rozmiar), a budżet tutaj to {budget} — nic nie zapisano, bo alternatywą jest zabicie procesu w połowie i brak jakiegokolwiek raportu',
    'font.obfuscation-declared': '{count} {count:fontu nie udało się|fontów nie udało się|fontów nie udało się} zamienić z powrotem w zwykłe pliki, więc kontener nadal deklaruje je jako zaciemnione: bajty, których żaden czytnik nie użyje, nie mogą wyjść z etykietą działającego fontu',
    'package.not-written': 'przebudowanej książki nie dało się zapisać tam, gdzie miała trafić: {error}. Źródło jest nietknięte, a pozostałe książki w tym przebiegu to nie dotyczy',
    'package.invariant-failed': '{count} {count:rzecz w przebudowanej książce nie jest prawdą|rzeczy w przebudowanej książce nie są prawdą|rzeczy w przebudowanej książce nie jest prawdą}, więc nic nie zapisano: {detail}',
    'structure.reference-bearing-kept': 'plik {media_type} odwołuje się do {count} {count:innego pliku|innych plików|innych plików} tej książki ({names}), a nic tutaj nie umie przepisać tych odwołań — został więc dokładnie tam, gdzie umieścił go wydawca, zamiast wskazywać plik, którego już nie ma',
    'xhtml.fragment-unresolved': '{count} {count:odnośnik wskazuje|odnośniki wskazują|odnośników wskazuje} kotwicę, której docelowy dokument nie ma ({examples}); odwołanie zostawiono dokładnie tak, jak napisał je wydawca — nic tutaj nie wie, dokąd miało prowadzić, a znacznik przypisu, który po cichu trafia do niewłaściwego przypisu, jest gorszy od takiego, o którym czytelnik widzi, że jest zepsuty',
    'xhtml.fragment-repointed': '{count} {count:odnośnik z brakującą kotwicą dostał|odnośniki z brakującą kotwicą dostały|odnośników z brakującą kotwicą dostało} nową, wskazaną przez osobę prowadzącą przebudowę',
    'package.unresolved-references': '{count} {count:odnośnik wskazuje|odnośniki wskazują|odnośników wskazuje} kotwicę, której nie ma w żadnym dokumencie ({examples}), a tryb ścisły nie wydaje książki z odwołaniami, których nie potrafi uczciwie rozwiązać; nic nie zapisano',
    'xhtml.encoding-mended': 'ten dokument twierdził, że jest w jednym kodowaniu, a jego bajty były w innym ({encoding}); odczytano go jako to, czym jest, zamiast sparsować z podmianą różnicy — bo tak właśnie znika znak książki i nikt się o tym nie dowiaduje',
    'xhtml.document-language-corrected': 'dokument twierdził, że jest w {was}, a jego własny tekst jest ewidentnie polski, więc mówi teraz {now}; czytnik podaje ten atrybut syntezatorowi mowy i dzieli po nim wyrazy',
    'xhtml.duplicate-ids-renamed': '{count} {count:atrybut id powtarzał się|atrybuty id powtarzały się|atrybutów id powtarzało się} w tym samym dokumencie ({names}); pierwszy z każdej pary zachowuje nazwę, późniejsze przemianowano — każdy istniejący odnośnik trafia tam, gdzie trafiał',
    'nav.unspined-target-added': 'spis treści prowadził do {count} {count:dokumentu, którego|dokumentów, których|dokumentów, których} nie było w kolejności czytania ({names}); dodano je do niej jako linear="no", czyli osiągalne ze spisu, ale przewracanie stron nigdy tam nie trafi',
    'css.direction-default-removed': '{count} {count:deklaracja ustawiała|deklaracje ustawiały|deklaracji ustawiało} kierunek tekstu, który arkusz i tak ma; EPUB 3 nie pozwala na tę własność w arkuszu, a ta nic nie wnosiła — usunięto',
    'css.direction-kept': '{count} {count:deklaracja ustawia|deklaracje ustawiają|deklaracji ustawia} kierunek tekstu, od którego zależy wygląd strony ({declarations}); EPUB 3 chce tego w znacznikach, ale zostawiono — inaczej strona wyszłaby odbita',
    'xhtml.head-added': 'dodano brakujący element <head>',
    'xhtml.body-added': 'dodano brakujący element <body>',
    'xhtml.dead-reference-kept': '{count} {count:odwołanie wskazuje|odwołania wskazują|odwołań wskazuje} na pliki, których w książce nie ma; zostawiono je bez zmian',
    'xhtml.dead-reference-neutralised': 'unieszkodliwiono {count} {count:odwołanie|odwołania|odwołań} do plików nieobecnych w książce',
    'xhtml.dead-fragment-dropped': '{count} {count:odnośnik wskazywał|odnośniki wskazywały|odnośników wskazywało} na kotwicę, której żaden dokument nie definiuje, i {count:prowadzi teraz|prowadzą teraz|prowadzi teraz} na początek dokumentu docelowego — bo tak zdecydowała osoba prowadząca przebudowę',
    'xhtml.presentational-markup-converted': 'stare znaczniki prezentacyjne zamieniono na CSS',
    'xhtml.head-flow-hidden': '{count} {count:element siedział|elementy siedziały|elementów siedziało} w <head>, gdzie parser XML je zostawia i żaden czytnik ich nie rysuje; {count:został przeniesiony|zostały przeniesione|zostało przeniesionych} do treści i wyłączony z rysowania, więc strona wygląda dokładnie tak samo',
    'css.style-junk-removed': '{count} z {total} {total:reguły|reguł|reguł} w bloku <style> tego dokumentu — {share}% bloku — to pozostałości konwertera nietrafiające w nic w książce; usunięte',
    'css.sheet-junk-removed': '{count} z {total} {total:reguły|reguł|reguł} w tym arkuszu stylów — {share}% arkusza — to pozostałości konwertera nietrafiające w nic w książce; usunięte',
    'footnotes.linked': '{count} {count:goły znacznik przypisu|gołe znaczniki przypisów|gołych znaczników przypisów} [N] {count:połączony|połączone|połączonych} odnośnikami ze swoimi notami; tekst co do znaku bez zmian',
    'footnotes.found': '{count} {count:goły znacznik przypisu|gołe znaczniki przypisów|gołych znaczników przypisów} [N] pasuje do not w sekcji przypisów; zostawione bez zmian',
    'css.classes-renamed': '{count} {count:klasa nazwana|klasy nazwane|klas nazwanych} przez konwerter {count:dostała|dostały|dostało} nazwy ze słownika epubforge (nazwy w języku: {language}); szczegół niesie pełną mapę starych nazw na nowe',
    'css.class-translation-scripted': 'ta książka niesie skrypt, który może trzymać nazwy klas w tekście; żadna klasa nie została przemianowana',
    'css.class-translation-attr-selector': 'CSS tej książki sięga po klasy selektorami atrybutów; żadna klasa nie została przemianowana',
    'css.class-translation-unverified': 'po przemianowaniu arkusz nie parsował się jak ten sam arkusz, więc żadna klasa nie została przemianowana',
    'css.page-plumbing-removed': '{count} {count:deklaracja|deklaracje|deklaracji} `page: …` — hydraulika wydruku konwertera, której żaden czytnik nie stosuje do tekstu płynącego — {count:usunięta|usunięte|usuniętych}, wraz z {rules} {rules:opróżnioną regułą|opróżnionymi regułami|opróżnionymi regułami}',
    'css.page-plumbing-found': '{count} {count:deklaracja|deklaracje|deklaracji} `page: …` — hydraulika wydruku, której żaden czytnik nie stosuje — {count:zostawiona i policzona|zostawione i policzone|zostawionych i policzonych}',
    'css.page-plumbing-unverified': 'po usunięciu {count} {count:deklaracji|deklaracji|deklaracji} `page: …` wynik nie parsował się jak ten sam arkusz, więc nic nie zostało ruszone',
    'css.style-unmatched-kept': '{count} {count:nieosiągalna reguła|nieosiągalne reguły|nieosiągalnych reguł} w bloku <style> tego dokumentu nie przypomina nazewnictwa żadnego generatora; zostawione bez zmian',
    'css.malformed-declaration-dropped': '{count} {count:deklaracja została zapisana|deklaracje zostały zapisane|deklaracji zostało zapisanych} tak, jak zapisuje się atrybut HTML — {names} — czego żaden czytnik nigdy nie zastosował; {count:usunięta|usunięte|usuniętych}, żeby plik był zgodny',
    'css.malformed-declaration-kept': '{count} {count:deklaracja używa|deklaracje używają|deklaracji używa} znaku = tam, gdzie CSS wymaga dwukropka; po ich usunięciu zostawało coś, co nie parsuje się już jako CSS, więc zostały',
    'css.comment-shield-removed': 'zdjęto {count} {count:token|tokeny|tokenów} osłony komentarza HTML sprzed ery CSS wokół reguł arkusza; każdy parser CSS od 1997 roku i tak {count:go|je|je} ignorował',
    'css.mend-unverified': 'po wszystkich naprawach ten arkusz przestał czytać się pełnemu parserowi jako CSS, więc wszystkie naprawy zostały cofnięte i tekst jest dokładnie źródłowy',
    'css.duplicate-properties-removed': 'usunięto {count} {count:deklarację powtarzającą|deklaracje powtarzające|deklaracji powtarzających} właściwość w obrębie jednego bloku; o każdej dowiedziono, że nie może wygrać z wystąpieniem, które zostaje',
    'css.duplicate-properties-resolved': '{count} {count:powtórzoną deklarację|powtórzone deklaracje|powtórzonych deklaracji} z mieszaną ważnością i różnymi wartościami rozstrzygnięto na zwycięzcę współczesnej kaskady — na słowo człowieka',
    'css.duplicate-properties-kept': '{count} {count:powtórzona deklaracja|powtórzone deklaracje|powtórzonych deklaracji} w bloku może być zabezpieczeniem, którego starszy czytnik wciąż używa — {count:została|zostały|zostało} dokładnie tam, gdzie {count:stała|stały|stały}',
    'css.duplicate-properties-found': '{count} {count:deklaracja powtarza|deklaracje powtarzają|deklaracji powtarza} właściwość w obrębie jednego bloku; {count:zostawiona i policzona|zostawione i policzone|zostawionych i policzonych}',
    'css.duplicate-properties-unverified': 'po usunięciu {count} {count:powtórzonej deklaracji|powtórzonych deklaracji|powtórzonych deklaracji} wynik nie parsował się jak ten sam arkusz, więc nic nie zostało ruszone',
    'css.reformatted': 'arkusz upychający {rules} {rules:regułę|reguły|reguł} w {lines} {lines:linii|liniach|liniach} przepisano po jednej deklaracji na linię; każdy znak poza białymi jest identyczny',
    'css.single-line-found': 'arkusz upycha {rules} {rules:regułę|reguły|reguł} w {lines} {lines:linii|liniach|liniach}; zostawiony i policzony',
    'css.reformat-unverified': 'czytelne przepisanie nie oddało tych samych znaków, więc nic nie zostało ruszone',
    'css.shorthand-overrides-removed': 'usunięto {count} {count:deklarację składową stojącą|deklaracje składowe stojące|deklaracji składowych stojących} przed skrótem, który resetuje jej miejsce; skrót i tak odrzucał je w każdym parserze',
    'css.shorthand-overrides-kept': '{count} {count:pary składowa-przed-skrótem nie dało się dowieść|par składowa-przed-skrótem nie dało się dowieść|par składowa-przed-skrótem nie dało się dowieść} — wartość skrótu bywa odrzucana przez walidator albo ważność chroni składową — {count:stoi|stoją|stoi} dokładnie tam, gdzie {count:stała|stały|stały}',
    'css.shorthand-overrides-found': '{count} {count:deklaracja składowa stoi|deklaracje składowe stoją|deklaracji składowych stoi} przed skrótem, który resetuje ich miejsce; {count:zostawiona i policzona|zostawione i policzone|zostawionych i policzonych}',
    'css.shorthand-overrides-unverified': 'po usunięciu {count} {count:nadpisanej składowej|nadpisanych składowych|nadpisanych składowych} wynik nie parsował się jak ten sam arkusz, więc nic nie zostało ruszone',
    'css.specificity-reordered': '{count} {count:regułę stojącą|reguły stojące|reguł stojących} poniżej bardziej specyficznego selektora o wspólnym kluczu przeniesiono nad niego; o każdym zwycięzcy, którego mogłaby wybrać kolejność, dowiedziono, że zostaje ten sam — typem elementu albo dokumentami tej książki',
    'css.specificity-resolved': '{count} {count:regułę trzymaną|reguły trzymane|reguł trzymanych} poniżej swojego miejsca przez remis potwierdzony książką przestawiono mimo sporu — na słowo człowieka; suma lintu ściśle spadła',
    'css.specificity-kept': '{count} {count:znalezisko malejącej specyficzności zostaje|znaleziska malejącej specyficzności zostają|znalezisk malejącej specyficzności zostaje} tam, gdzie ruchu nie dało się dowieść — reguły stoją dokładnie tam, gdzie postawił je wydawca',
    'css.specificity-found': '{count} {count:selektor stoi|selektory stoją|selektorów stoi} poniżej bardziej specyficznego selektora o wspólnym kluczu; {count:zostawiony i policzony|zostawione i policzone|zostawionych i policzonych}',
    'css.specificity-unverified': 'po przestawieniu {count} {count:reguły|reguł|reguł} wynik nie oddał tych samych reguł co do bajtu, więc nic nie zostało ruszone',
    'css.empty-noise-removed': 'usunięto {count} {count:pusty twór|puste twory|pustych tworów} — {comments} {comments:komentarz|komentarze|komentarzy} i {rules} {rules:regułę|reguły|reguł} bez treści; nie mówiły nic i każdy parser je pomijał',
    'css.empty-noise-found': '{count} {count:pusty komentarz, reguła albo at-reguła|puste komentarze, reguły albo at-reguły|pustych komentarzy, reguł albo at-reguł} — {count:zostawiony i policzony|zostawione i policzone|zostawionych i policzonych}',
    'css.empty-noise-unverified': 'po usunięciu {count} {count:pustego tworu|pustych tworów|pustych tworów} wynik nie parsował się jak ten sam arkusz, więc nic nie zostało ruszone',
    'css.duplicate-selectors-merged': '{count} {count:regułę powtarzającą|reguły powtarzające|reguł powtarzających} wcześniejszy selektor złożono w jego ostatnie wystąpienie; każdy zwycięzca kaskady zostaje ten sam — i to jest warunek, wobec którego złożenie zostało dowiedzione',
    'css.duplicate-selectors-resolved': '{count} {count:regułę powtarzającą|reguły powtarzające|reguł powtarzających} selektor, których kaskada nie chciała puścić, złożono mimo spornej drogi — na słowo człowieka',
    'css.duplicate-selectors-kept': '{count} {count:reguła powtarza|reguły powtarzają|reguł powtarza} selektor w sposób, którego złożenia kaskada dowodnie nie pozwala — {count:zostawiona|zostawione|zostawionych} dokładnie tam, gdzie {count:stała|stały|stały}',
    'css.duplicate-selectors-found': '{count} {count:reguła powtarza|reguły powtarzają|reguł powtarza} wcześniejszy selektor; {count:zostawiona i policzona|zostawione i policzone|zostawionych i policzonych}',
    'css.duplicate-selectors-unverified': 'po złożeniu {count} {count:reguły|reguł|reguł} z powtórzonym selektorem wynik nie parsował się jak ten sam arkusz, więc nic nie zostało ruszone',
    'css.unknown-properties-removed': 'usunięto {count} {count:deklarację właściwości, której|deklaracje właściwości, których|deklaracji właściwości, których} CSS nie zna ({names}), wraz z {rules} {rules:opróżnioną regułą|opróżnionymi regułami|opróżnionymi regułami}; każdy poprawny parser i tak je odrzucał',
    'css.unknown-properties-found': '{count} {count:deklaracja właściwości, której|deklaracje właściwości, których|deklaracji właściwości, których} CSS nie zna — {count:zostawiona i policzona|zostawione i policzone|zostawionych i policzonych}',
    'css.unknown-properties-unverified': 'po usunięciu {count} {count:deklaracji|deklaracji|deklaracji} nieznanych właściwości wynik nie parsował się jak ten sam arkusz, więc nic nie zostało ruszone',
    'css.malformed-declaration-enabled': '{count} {count:deklaracja zapisana|deklaracje zapisane|deklaracji zapisanych} ze znakiem = zamiast dwukropka — {names} — nie {count:nosiła|nosiły|nosiło} podpisu żadnego konwertera i na słowo osoby {count:została włączona|zostały włączone|zostało włączonych}: = stał się dwukropkiem i formatowanie obowiązuje',
    'css.malformed-declaration-left': '{count} {count:deklaracja zapisana|deklaracje zapisane|deklaracji zapisanych} ze znakiem = zamiast dwukropka nie {count:nosi|noszą|nosi} podpisu żadnego konwertera; {count:zostawiona|zostawione|zostawionych} bez zmian — czytniki dalej je ignorują',
    'xhtml.image-paragraph-centred': 'wyśrodkowano {count} {count:akapit zawierający sam obraz|akapity zawierające sam obraz|akapitów zawierających sam obraz} i usunięto z nich wcięcie',
    'xhtml.image-paragraph-centred-unstyled': 'wyśrodkowano {count} {count:akapit zawierający sam obraz|akapity zawierające sam obraz|akapitów zawierających sam obraz} na stronie, która nie linkuje żadnego arkusza',
    'xhtml.cover-sized-in-pixels': 'obraz okładki ma rozmiar podany w pikselach atrybutem i został tak zostawiony',
    'package.text-lost': 'w wyniku brakuje tekstu ze źródła, więc nic nie zostało zapisane',
    'package.text-check-per-rendition': 'kontener zawiera więcej niż jedną publikację, więc niezmiennik tekstu nie był sprawdzany na całości',
    'hyphens.no-dictionary': 'nie było słownika {language}, więc łączniki oceniono wyłącznie na podstawie słownictwa tej książki',
    'package.text-changed-on-request': 'tekst ubył z książki, bo o to poprosiłeś ({rules}), więc niezmiennik znak w znak już nie obowiązuje',
    'package.text-check-failed': 'nie udało się zmierzyć niezmiennika tekstu na tej książce',
    'xhtml.image-paragraph-unindented': 'usunięto wcięcie tekstu bieżącego z {count} {count:akapitu z obrazem|akapitów z obrazem|akapitów z obrazem}',
    'xhtml.image-paragraph-kept': '{count} {count:akapit z obrazem zostawiono|akapity z obrazem zostawiono|akapitów z obrazem zostawiono} tak, jak {count:ostylował go|ostylował je|ostylował je} wydawca',
    'xhtml.cover-fitted': 'obrazowi okładki nadano ograniczenia dopasowujące go do strony, bo nic w książce ich nie ustawiało',
    'xhtml.inline-promoted': '{count} {count:element liniowy zawierający treść blokową|elementy liniowe zawierające treść blokową|elementów liniowych zawierających treść blokową} zamieniono na blokowe',
    'xhtml.cover-described': 'obraz okładki opisano tytułem książki',
    'xhtml.empty-alt-added': 'dodano pusty atrybut alt do {count} {count:obrazu|obrazów|obrazów}',
    'xhtml.scripts-kept': '{count} {count:element skryptu zachowano|elementy skryptu zachowano|elementów skryptu zachowano}, a dokument zadeklarowano jako skryptowany',
    'xhtml.scripts-removed': 'usunięto {count} {count:element skryptu|elementy skryptu|elementów skryptu} i {handlers} {handlers:liniową obsługę zdarzeń|liniowe obsługi zdarzeń|liniowych obsług zdarzeń}',
    'metadata.override-applied': 'wywołujący nadpisał pole metadanych {field}',
    'metadata.title-missing': 'źródło nie ma dc:title; wstawiono zastępczy',
    'metadata.titles-collapsed': '{count} {count:element dc:title sprowadzono|elementy dc:title sprowadzono|elementów dc:title sprowadzono} do jednego tytułu głównego',
    'metadata.language-invalid': 'znacznik języka {was} nie jest poprawnym BCP 47 i został zastąpiony przez {now}',
    'metadata.language-corrected': 'zadeklarowany język {was} jest sprzeczny z tekstem; poprawiono na {now}',
    'metadata.language-missing': 'źródło nie ma dc:language, więc użyto {now}',
    'metadata.identifier-minted': 'źródło nie ma dc:identifier; wygenerowano UUID',
    'metadata.identifier-promoted': 'nie zadeklarowano unique-identifier; awansowano pierwszy',
    'metadata.date-normalised': 'dc:date sprowadzono do ISO 8601: {was} stało się {now}',
    'metadata.date-unparseable': 'dc:date {was} nie dało się odczytać i zostało pominięte',
    'metadata.creator-missing': 'źródło nie podaje dc:creator',
    'image.pillow-unavailable': 'Pillow nie jest zainstalowany, więc obrazy przeszły niesprawdzone',
    'image.unreadable': 'obrazu nie dało się odczytać i został bez zmian: {error}',
    'image.type-corrected': 'plik jest w rzeczywistości {actual}, choć zadeklarowano {declared}',
    'image.type-kept': '{media_type} nie jest typem rdzenia EPUB 3, ale zachowano go zgodnie z polityką',
    'image.renamed': 'plik przemianowano na .{suffix} — taki format naprawdę ma',
    'image.transcode-failed': 'transkodowanie się nie powiodło; zachowano oryginał: {error}',
    'image.transcoded': 'obraz przekodowano z {media_type} na PNG dla zgodności z czytnikami',
    'image.animation-kept': 'obraz {media_type} z {frames} {frames:klatką|klatkami|klatkami} zostawiono dokładnie takim, jaki był: konwersja zachowałaby pierwszą klatkę i po cichu wyrzuciła resztę',
    'font.type-corrected': 'typ MIME czcionki poprawiono na {actual}; zadeklarowany był {declared}',
    'font.unrecognised': 'czcionka nie ma rozpoznawalnej sygnatury',
    'font.drm': 'treść jest zabezpieczona DRM; przebudowa nie może przebiec bezpiecznie',
    'font.obfuscation-kept': 'zaciemnienie czcionek zostawione zgodnie z polityką',
    'font.obfuscation-unkeyed': 'czcionki są zaciemnione, ale pakiet nie ma identyfikatora, na którym można je oprzeć',
    'font.deobfuscation-failed': 'odciemnianie nie dało poprawnej czcionki; plik został bez zmian',
    'font.deobfuscated': 'odciemniono {count} {count:osadzoną czcionkę|osadzone czcionki|osadzonych czcionek} i usunięto plik szyfrowania',
    'compat.unknown-profile': 'profil zgodności {profile} nie istnieje i został pominięty',
    'compat.applied': 'zastosowano profile zgodności: {profiles}',
    'compat.legacy-font-types': '{count} {count:osadzona czcionka jest zadeklarowana|osadzone czcionki są zadeklarowane|osadzonych czcionek jest zadeklarowanych} typem, który zna Adobe RMSDK, a nie tym, który rejestruje EPUB 3.3',
    'compat.ncx-required': 'wybrany profil wymaga starego NCX, który był wyłączony',
    'compat.stylesheet-added': '{stylesheet} podlinkowano do {count} {count:dokumentu|dokumentów|dokumentów}',
    'compat.page-break-mirrored': '{count} {count:deklarację łamania odwzorowano|deklaracje łamania odwzorowano|deklaracji łamania odwzorowano} na page-break-*',
    'compat.specified-fonts-skipped': 'książka nie osadza czcionek, więc pominięto deklarację dla Apple',
    'compat.specified-fonts-added': 'zadeklarowano specified-fonts dla Apple Books',
    'compat.guide-skipped': 'nic w książce nie odwzorowuje się na stary <guide>',
    'compat.guide-added': 'dodano element <guide> z EPUB 2 dla czytników, które go szukają',
    'compat.svg-cover': 'strona okładki opakowuje grafikę w SVG, co część konwerterów obsługuje źle',
    'a11y.conformance-declared': 'zadeklarowano zgodność z {profile}, bo wywołujący to stwierdził',
    'a11y.metadata-added': 'dodano metadane dostępności EPUB Accessibility 1.1',
    'a11y.missing-alt': '{count} {count:obraz nie ma|obrazy nie mają|obrazów nie ma} używalnego tekstu alternatywnego',
    'a11y.placeholder-alt': '{count} {count:obraz ma|obrazy mają|obrazów ma} tekst alternatywny powtarzający tylko nazwę pliku',
    'a11y.heading-jump': 'poziomy nagłówków przeskakują stopień w {count} {count:miejscu|miejscach|miejscach}',
    'a11y.table-without-headers': '{count} {count:tabela nie ma|tabele nie mają|tabel nie ma} komórek nagłówkowych',
    'package.upgraded': 'pakiet przebudowano z EPUB {version} na 3.3',
    'package.regenerated': 'źródło było już EPUB {version}, a pakiet i tak wygenerowano od nowa',
    'package.layout-kept': 'dokument pakietu został w {path}, bo pliki wokół niego się nie przesunęły',
    'package.version-unusable': 'pakiet nie deklarował używalnej wersji; potraktowano go jak EPUB 2',
    'package.unreadable-source': 'pliku źródłowego nie dało się odczytać: {error}',
    'package.stage-broke-its-word': 'etap {stage} twierdzi, że tylko mierzy książkę, a ją zmienił — nic nie zapisano: każde inne zapewnienie z tego przebiegu opiera się na obietnicy tego samego rodzaju',
    'package.stage-failed': 'etap {stage} zgłosił wyjątek, więc nic nie zostało zapisane: {error}',
    'package.input-incomplete': 'nie udało się odczytać {count} {count:wpisu|wpisów|wpisów} źródła ({names}), więc nic nie zapisano; przebudowa, która nie widzi części książki, nie może obiecać, że ją zachowa',
    'package.layout-unusable': 'źródło trzyma dokument pakietu w {path}, a to nie jest ścieżka, którą wolno tu zapisać ({reason}), więc użyto układu standardowego',
    'package.source-protected': 'odmówiono nadpisania pliku źródłowego',
    'package.spine-item-vanished': 'pozycja kolejności czytania zniknęła, zanim pakiet został zapisany',
    'epubcheck.reported': 'EPUBCheck zgłosił {fatal} błędów krytycznych i {errors} błędów',
    'epubcheck.clean': 'EPUBCheck przyjął wynik, z {warnings} ostrzeżeniem/ami',
    'epubcheck.unavailable': 'EPUBCheck nie jest zainstalowany, więc wynik nie został zweryfikowany',
    'epubcheck.failed': 'EPUBCheck w ogóle nie dał się uruchomić: {error}',
    # -- the gate before publication (K.2 invariant 12) ----------------------
    'reader.xml-recovered': 'ten plik nie jest poprawnym XML-em i został odczytany przez parser zgadujący, co autor miał na myśli ({detail}); to, co z niego wyszło, jest rekonstrukcją, a nie treścią pliku',
    'package.metadata-from-a-guess': 'dokument pakietu trzeba było zrekonstruować, więc opis książki o samej sobie jest domysłem: sprawdź {fields} i popraw, jeżeli się nie zgadzają',
    'xhtml.reference-relocated': '{count} {count:odwołanie wskazywało|odwołania wskazywały|odwołań wskazywało} ścieżkę, której w tej książce nie ma, a plik o tej nazwie jest w niej dokładnie jeden; wskazują teraz na niego, bo odwołanie źle zaadresowane to nie odwołanie martwe',
    'css.dead-url-neutralised': '{count} {count:odwołanie w arkuszu wskazywało|odwołania w arkuszu wskazywały|odwołań w arkuszu wskazywało} na pliki, których w książce nie ma — unieszkodliwione: pojedynczy obrazek staje się none, kandydat z listy zapasowej wypada z niej, a @font-face bez żadnego źródła znika razem z nim',
    'css.dead-url-kept': '{count} {count:odwołanie w arkuszu wskazuje|odwołania w arkuszu wskazują|odwołań w arkuszu wskazuje} na pliki, których w książce nie ma, i zostało bez zmian — bo po unieszkodliwieniu arkusz przestawał się parsować',
    'metadata.property-superseded': '{count} {count:zdanie metadanych ze źródła nie zostało powtórzone|zdania metadanych ze źródła nie zostały powtórzone|zdań metadanych ze źródła nie zostało powtórzonych} w wyniku, bo ta przebudowa sama zapisuje tę własność',
    'package.input-lost-detail': '{name} — {kind}, którego archiwum nie oddało; spis książki go wymieniał: {declared}; dokumentów wskazujących na to: {referenced_by}',
    'package.gate-refused': 'EPUBCheck uznaje przebudowaną książkę za niepoprawną ({count} {count:błąd|błędy|błędów}: {detail}), a ten tryb nie wydaje niepoprawnego pliku; nic nie zapisano, a to, co leżało pod tą nazwą, jest nietknięte',
    'package.gate-refused-new': 'ta przebudowa dołożyła {count} {count:błąd EPUBCheck, którego|błędy EPUBCheck, których|błędów EPUBCheck, których} nie było w źródle (wersja {source_version}) ({detail}); książki nie wydano, bo przenieść cudzy defekt to jedno, a dołożyć własny to drugie',
    'package.errors-were-already-there': 'EPUBCheck uznaje książkę za niepoprawną w {count} {count:miejscu|miejscach|miejscach} i uznawał źródło za niepoprawne w tych samych miejscach, więc wydano ją taką, jaka przyszła; te defekty są wydawcy i są wypisane w raporcie',
    'package.gate-cannot-run': 'poproszono o bramkę {gate}, a nie ma czym jej uruchomić, więc książki nie wydano; bramka, która przepuszcza to, czego nie sprawdziła, nie jest bramką',
    'package.gate-skipped': 'nie ma tu walidatora, więc przed wydaniem nic nie porównano; własna bramka inwariantów i odczyt zwrotny i tak się wykonały',
    # -- the window ---------------------------------------------------------
    'gui.unexpected-failure': 'przebudowa zawiodła w sposób, którego nic nie przewidziało: {error}',
}

#: The paragraph beneath a finding, in English, keyed by the same identifier.
#:
#: It used to be written at the call site, where it lived beside the sentence it
#: explains and nowhere near the Polish version of itself. Two homes for one
#: fact is one home too many: they drifted, and nothing could see them drift.
#:
#: A rule missing from here has a paragraph that is data rather than prose — a
#: list of names, a generated identifier, EPUBCheck's own output — and passes it
#: at the call site instead. `test_rules.py` names those and their reason.
DETAILS: dict[str, str] = {
    "a11y.conformance-declared":
        "EPUB-Forge did not verify this; it is the publisher's assertion.",
    "a11y.missing-alt":
        "Either the attribute is absent or it is empty. An empty alt asserts the image is decorative, and that cannot be checked mechanically — only role=\"presentation\" or aria-hidden=\"true\" says it outright. So alternativeText is not claimed. If any of these images carry meaning, only a human can write the description.",
    "a11y.placeholder-alt":
        "{examples} — this passes validation but tells a screen-reader user nothing, so alternativeText is not claimed.",
    "a11y.table-without-headers":
        "Screen readers cannot announce what a cell relates to without <th>.",
    "compat.guide-added":
        "EPUB 3.3 no longer defines this element, though EPUBCheck still accepts it: the output stays valid, but it carries something the current specification dropped. Amazon's converter and RMSDK readers find the cover and the start-reading position here and nowhere else.",
    "compat.ncx-required":
        "Readers predating EPUB 3 build their chapter list from the NCX and ignore the navigation document. Drop --no-ncx to restore it.",
    "compat.page-break-mirrored":
        "The modern break-* properties are left exactly as they are; the legacy spelling is added beside them for renderers that only know that one.",
    "compat.specified-fonts-added":
        "Without this file Apple Books ignores every embedded face and substitutes its own.",
    "compat.specified-fonts-skipped":
        "Declaring it anyway would state something the book does not do.",
    "compat.stylesheet-added":
        "Declares the HTML5 sectioning elements as blocks. It is linked ahead of the book's own stylesheets, so every rule the publisher wrote still overrides it.",
    "compat.svg-cover":
        "The wrapper is what scales the artwork to the page, so removing it would change the layout on every other reader. Left as it is; replace it with a plain <img> by hand if the Kindle cover comes out wrong.",
    "compat.unknown-profile":
        "Known profiles: {known}.",
    "css.font-stack-generic-missing":
        "e.g. {examples} — inherited from the source and left as-is, since guessing serif vs sans-serif could change how the book looks.",
    "xhtml.forbidden-characters-removed":
        "The worse half of the same defect: a control character in a title spoils the package, one in a chapter spoils the text of the book. It arrives from the source — a damaged file recovered by the parser keeps it — and was written back out into a document nothing can open. Only the impossible characters go; every letter, digit and mark of punctuation stays, so no character of the book's own text is lost.",
    "xhtml.mojibake-translated":
        "Windows-1252 keeps punctuation on the byte positions Unicode reserves for control codes, so a converter reading Windows text as Latin-1 turns every quotation mark and dash into a code no font draws. The damage is in the file rather than in this program's reading: the documents this was found on declare UTF-8 and are valid UTF-8. The mapping back is one-to-one over twenty-seven defined positions and nothing about it is guessed, which is why it is offered as a repair rather than as a heuristic — but it changes characters of the text, so it happens only when somebody says so.",
    "xhtml.mojibake-found":
        "The same damage, left alone because that is what was chosen. Said out loud rather than passed over, because these characters are invisible in a reading system: the book is missing its quotation marks on the page whether or not anybody notices in the file.",
    "package.forbidden-characters-removed":
        "Not a matter of escaping: XML 1.0 has no representation for these characters at all, so a package document carrying one does not parse and the book does not open. Measured before this existed: a title carrying 0x0B produced a written, unopenable book in the default mode. Only the offending characters go; every other character of the field is kept.",
    "xhtml.shop-notice-removed":
        "Listed word for word rather than counted, because this is the only setting in the program that deletes text a reader can see. Only sentences naming the sale are taken — an order, a purchase, a licence, a buyer. A publisher's colophon names the publisher rather than the transaction and is never touched, and no page is ever removed: an element left empty stays, and the balance reports it.",
    "css.invalid-value-corrected":
        "font-style/font-weight have no 'regular' keyword, so parsers dropped these rules entirely. Replaced with 'normal', which is what was meant — and only because nothing in this stylesheet sets italic or bold, so inheriting and overriding come to the same page.",
    "css.invalid-value-inherited":
        "'regular' is dropped by every parser, so the element inherits; 'normal' would override. Those agree only while the inherited value is already normal, and this stylesheet sets italic or bold somewhere, so correcting the value could turn an italic passage upright. It was already being ignored, so leaving it changes nothing.",
    "css.absolute-units":
        "Sizes in px or pt do not respond to the font-size control on a reading device, which is usually the first thing somebody changes. Left as the publisher wrote them; use --relative-units to rewrite them in rem.",
    "css.absolute-units-relativised":
        "rem and not em: em resolves against the parent, so a nested rule would compound and the same value would mean different sizes in different places. rem resolves against the root, so every size comes out at exactly size/16 — the same pixels as before at the default setting, and scaling together with it away from the default.",
    "css.absolute-units-rooted":
        "rem is measured from the root element, and this stylesheet fixes the root in pixels. Converting the rest would rewrite the sheet without freeing a single size.",
    "css.unreachable-rules-found":
        "Shops ship one house stylesheet into every title they sell, and most of it is for markup the particular book has not got — `td.proc4` in a novel with no tables. It changes no pixel either way. Use --strict to remove it; this mode reports and keeps, because a selector matching nothing in the documents we parsed is not the same claim as a selector matching nothing.",
    "css.unreachable-rules-removed":
        "Only rules whose every branch names a class or id absent from the whole book. A bare tag selector, an attribute selector, a pseudo-class and anything inside @media are never touched. The cut is then checked by re-parsing the sheet and comparing the survivors; a sheet that does not match is put back untouched.",
    "css.unreachable-rules-scripted":
        "A script can add a class while the book is being read, so 'this matches nothing' would be a statement about the file rather than about the reading.",
    "css.unreachable-rules-unverified":
        "The rules stay. A removal that cannot be shown to have taken exactly what it meant to is not one this tool makes.",
    "css.position-kept":
        "This is a fixed-layout book, where out-of-flow positioning is how it works.",
    "xhtml.position-pinned-in-flow":
        "`margin-top: auto` inside a flex column puts a block at the foot of the page exactly as `bottom: 0` was meant to, and keeps it in the flow, so pagination cannot lose it. Written into the one document that needs it, never into the shared stylesheet — flexing every body in a book would stop adjacent margins collapsing on every page of it. Only where the page is that one block: with siblings there is no faithful translation, so the rule is left alone and reported instead.",
    "css.position-contained":
        "An absolutely positioned element resolves against its nearest positioned ancestor, not against the page — a caption over a picture, a badge on a cover. It travels with the box that holds it, so pagination cannot lose it and the argument for removing out-of-flow positioning does not reach it. Kept even under --strict, which used to delete it and drop the caption below the image on every reader.",
    "css.position-superseded":
        "The declaration is still in the stylesheet and no longer decides anything: the document carries an equivalent that outranks it. Left in place because deleting from a shared sheet would reach documents nobody examined.",
    "css.position-removed":
        "The affected blocks now flow with the page instead of being pinned to it. Kept out of fixed-layout books, where out-of-flow positioning is how the format works. On a real reader a dedication pinned this way came out as a blank page — the block left the flow and pagination went round it.",
    "css.reader-property-kept":
        "{names} — validators flag these as unknown. Use --strict to remove them.",
    "css.vendor-at-rule-kept":
        "Use --strict to remove them.",
    "epubcheck.unavailable":
        "Install it and set {variable}, or put epubcheck on PATH.",
    "font.deobfuscated":
        "Fonts render identically and the container no longer depends on the identifier.",
    "font.deobfuscation-failed":
        "The source identifier likely differs from the one used to obfuscate it.",
    "font.drm":
        "Remove DRM with a tool you are licensed to use before running EPUB-Forge.",
    "image.transcoded":
        "was {was}",
    "metadata.title-missing":
        "Pass --title to set the real one.",
    "nav.contents-page-kept":
        "The page is in the reading order, so it is something the reader turns to. Replacing it with generated markup would lose whatever the publisher wrote there.",
    "nav.fragment-cleared":
        "The entry now points at the document, which is where the reader would land anyway.",
    "nav.generated":
        "The source had none; its table of contents came from the NCX.",
    "nav.kept-in-spine":
        "A nav document in the spine is a page the reader can turn to. Regenerating it used to remove that page.",
    "nav.repointed":
        "{in_tables} in the navigation tables, {in_documents} inside content documents. The source's own contents page is replaced, and a reference left pointing at it makes the book invalid, not merely inconsistent.",
    "package.layout-kept":
        "This rebuild does not move content files, so moving the package document away from them would leave every manifest href pointing back out of its own directory with `../`.",
    "package.source-protected":
        "Nothing was written. Choose a different destination.",
    "package.stage-failed":
        "Nothing was written. The model was left half-modified by the failure, so anything built from it would be a book only in shape.",
    "package.upgraded":
        "Package document, navigation and container structure were regenerated.",
    "reader.colliding-names":
        "They are separate files inside the archive and one file on a filesystem that folds case or Unicode normalisation — which is most of them outside Linux. Anyone unpacking this book loses one.",
    "reader.dangling-reference":
        "{reference} — the reference is dropped rather than guessed at",
    "reader.drm":
        "EPUB-Forge will not attempt to decrypt DRM-protected content.",
    "reader.entry-too-large":
        "No real book contains this; the archive is broken or hostile.",
    "reader.name-dropped":
        "Nothing in a conforming EPUB is named this way. It is not carried into the output, where it would be somebody else's problem to unpack safely.",
    "reader.remote-resource":
        "Nothing here fetches it. It is not stored in the container either.",
    "structure.carried-xml-repointed":
        "The pipeline does not model this file type, but it does move the files it points at. Leaving the references alone would have produced an invalid book rather than a poorer one.",
    "structure.orphan-removed":
        "{bytes} bytes reclaimed",
    "structure.relaid-out":
        "{renamed} file(s) needed a new name; every reference was rewritten to match",
    "xhtml.cover-fitted":
        "No stylesheet rule and no attribute sized this image, so a reader would show it at its own pixel dimensions.",
    "profile.paragraphs-mixed":
        "A book from one source does not mix the two. When it does, somebody glued two files together or ran one through two tools — which is worth knowing before any rule tries to normalise the paragraphs.",
    "profile.body-text-inconsistent":
        "Rules that ask whether a construction is this book's norm have no norm to compare against here. The percentage is kept rather than rounded away, because how far off a book was is what a rule declining to fire will want to say.",
    "xhtml.dead-reference-kept":
        "These are source defects and remain conformance errors. Use --strict to neutralise them.",
    "xhtml.dead-fragment-dropped":
        "The file each link names is present; the anchor inside it is not. The link now lands at the top of that document. This is the only route from a missing anchor to no anchor, and it runs through a person who looked at the book: the program will not take it on its own, because a link that quietly arrives somewhere plausible cannot be told apart from one that works.",
    "xhtml.fragment-unresolved":
        "The target document exists and the anchor in it does not, so where the link was meant to lead is not knowable from the file. It is a defect inherited from the source, and it is reported rather than repaired: removing the fragment would silence the validator by sending the reader to the top of the document — for a footnote marker, to the wrong footnote — and nothing here can tell that apart from a repair. Strict mode refuses to publish a book carrying these; in the window each one can be answered by hand.",
    "nav.sections-carried":
        "A list of tables, of illustrations, of anything the publisher named. This program regenerates the document they lived in, so not writing them back would delete them — and it has no rule for reading them, which is a reason to carry them unchanged rather than a reason to drop them.",
    "xhtml.fragment-repointed":
        "A person chose the anchor, which is evidence this program does not have. Counted separately from anything it worked out for itself.",
    "package.unresolved-references":
        "Every one of them is listed in the report with the document holding it. Rebuild in preserve mode to get the file with the publisher's own broken references intact, or open the book in the window, where each of these can be answered one at a time.",
    "css.remote-import-removed":
        "EPUB 3 allows one kind of remote resource — a font declared on its manifest item — and a stylesheet is not one. The font-family declarations are untouched, so the book falls back exactly as it would have.",
    "xhtml.remote-import-removed":
        "EPUB 3 allows one kind of remote resource — a font declared on its manifest item — and a stylesheet is not one. The font-family declarations are untouched, so the book falls back exactly as it would have.",
    "xhtml.dead-reference-neutralised":
        "{unlinked} link(s) unlinked, {removed} element(s) removed",
    "xhtml.doctype-kept":
        "The output stays an invalid EPUB 3 in those documents, and that is the lesser harm: replacing the declaration would strand the reference and the book would no longer open at all. Rebuild this book in a mode that rewrites content.",
    "xhtml.orphaned-styling-restored":
        "The rule exists in this book, in a stylesheet this document does not link, and exactly one stylesheet has it — so there is nothing to choose between. Copied into the document verbatim rather than linking the whole sheet, which would import every other decision in it into a page it was not written for. Not applied when two sheets disagree, nor to rules that fetch something with url().",
    "xhtml.empty-span-found":
        "Measured over 12 475 spans in thirty-two books: 97% do something, and the ones that do not are all PDF conversion — `.reset { margin: 0; padding: 0 }` on an inline box where those are the defaults, and `.black { color: #010000 }`, black moved by one part in 255. A span nothing styles at all is left alone: the largest such class in the corpus was 219 drop caps whose stylesheet had come unlinked.",
    "xhtml.empty-span-unwrapped":
        "Unwrapped, not deleted — the text inside stays exactly where it was. Only spans with no id, lang, epub:type, role, dir, title or style, and only where a rule reaches them and every declaration in it is the default for an inline box.",
    "xhtml.epub2-only-markup":
        "Container-only mode edits the head and nothing else, so this stays and the output is an invalid EPUB 3 through no fault of the content. Rebuild in \"preserve\" for a conformant file — that mode rewrites each of these into what EPUB 3 accepts, without changing what the page shows. Named as found rather than claimed complete: anything not listed still shows up in a validator.",
    "xhtml.title-filled":
        "EPUB 2 allowed an empty <title>; EPUB 3 does not, and this rebuild produces EPUB 3. The text is not rendered in the body, so nothing on the page moves. In container-only mode this is the second and last edit made inside a document.",
    "xhtml.doctype-modernised":
        "The only change this mode makes inside a document. A DOCTYPE says nothing about rendering, and a legacy one makes the book invalid. A DOCTYPE that declares its own entities is left alone, because the document uses them.",
    "xhtml.dtd-entities-refused":
        "{names}. Either they point outside the file, which this tool will not fetch, or expanding them would have grown the document past any plausible size.",
    "xhtml.dtd-entities-resolved":
        "{names}. The declarations lived in the DOCTYPE, which EPUB 3 replaces with one that declares nothing — so without this the references would have appeared on the page as literal text.",
    "xhtml.empty-alt-added":
        "Required for valid markup. It is not treated as a description: the accessibility stage still counts these images as undescribed, so nothing is claimed on their behalf.",
    "xhtml.image-paragraph-centred":
        "Running-text rules were shifting the artwork; no rule targeted these paragraphs specifically, so the layout was inherited rather than chosen.",
    "xhtml.image-paragraph-centred-unstyled":
        "This page links no stylesheet at all, so there was no indent to remove and no publisher's rule to override — the reader's own default was left-aligning the artwork. Said separately from the paragraph above because the two are different facts about the book, and a message that describes the wrong one is a message somebody learns to skip.",
    "package.text-lost":
        "K1, the rule above every other one in this program: every character of the source's reading order appears in the output, in the same order. Measured at word level, because a rebuild legitimately changes spacing. The file was built, checked and refused before it took its name, so whatever was already there is untouched.",
    "hyphens.no-dictionary":
        "The detector has two sources of evidence: whether this book itself writes the word without a hyphen, and whether the word's first half is a word at all. Only the first was available here, and it is the one that says nothing about a word the book uses once — so some broken words will have gone unnoticed. Nothing was joined that should not have been; the run simply saw less.",
    "package.text-changed-on-request":
        "K1 is a statement about losses nobody asked for. Removing a watermark and joining a word a conversion cut in half both take characters out, both happen only after you say so, and both are in the change ledger — so they are named here rather than refused. What the gate still refuses is text going missing with nothing accounting for it.",
    "package.text-check-failed":
        "The comparison itself raised. A check that cannot run is not a book that failed, so the rebuild continued — but nothing verified the text, and that is worth knowing before trusting the result.",
    "xhtml.cover-sized-in-pixels":
        "A width or height attribute in pixels fixes the cover at one size whatever the screen is. It is the publisher's instruction, so it is reported and not overwritten: changing it is a decision about how the book looks, and this program does not make those on its own.",
    "xhtml.image-paragraph-kept":
        "A rule aimed at these paragraphs, or at an element containing them, sets their alignment or indent.",
    "xhtml.image-paragraph-unindented":
        "A rule aimed at these paragraphs or their container decides where the image sits; the indent reached them from a rule about body text.",
    "xhtml.inline-promoted":
        "A block box inside an inline box splits the line and makes margins and centring behave unpredictably; inline-block is a legal container that keeps the element where it was.",
    "xhtml.property-withdrawn":
        "Declaring one of these without the markup to match is a conformance error in its own right, and EPUBCheck reports it against the source.",
    "xhtml.untouched":
        "Every XHTML file comes out byte for byte as it went in.",
    "xhtml.untouched-except-doctype":
        "Every XHTML file comes out byte for byte as it went in, apart from the DOCTYPE where it had to be modernised.",
    "xhtml.watermark-consolidated":
        "{tokens} distinct token(s), text unchanged. The repeated inline !important style became one rule, and the markers are hidden from screen readers instead of being spelled out each chapter.",
    "xhtml.watermark-relocated":
        "{tokens} distinct token(s), text unchanged, now carried as <meta name=\"{name}\"> in the head of the document each one came from. Still in the file and still traceable, but no longer laid out, paginated or read aloud — which a token at font-size zero still was.",
    "xhtml.watermark-removed":
        "{tokens} distinct token(s), gone. The book no longer carries the mark that ties this copy to its buyer.",
    "metadata.language-corrected":
        "{rate} Polish-only letters per 1000 characters of the book's own text. A reading system speaks dc:language to its text-to-speech engine and hyphenates by it, so a wrong declaration is read aloud in the wrong voice and broken across lines by the wrong rules — neither of which any validator mentions. --language overrides this.",
    "css.font-stack-generic-added":
        "Read from the font's OS/2 table — PANOSE, ten bytes the designer filled in — not inferred from its name. A stack with no generic family falls back to whatever the reader likes when the embedded font fails to load, which on an e-reader it often does.",
    "xhtml.watermark-kept":
        "Meant to be read, so left exactly as the publisher wrote it.",
    "xhtml.watermark-kept-personal-data":
        "Carries personal data ({data}). Meant to be read, so left exactly as the publisher wrote it.",
}

#: The paragraph beneath a finding, in Polish, keyed by the same identifier.
#:
#: Kept apart from `CATALOGUE_PL` because it is a different kind of text and
#: has a different completion state: the headline is one sentence and every one
#: of them is translated, while a detail is prose and some of them are not text
#: at all — a list of names, a byte count, an example the reader is meant to
#: read verbatim. Those have nothing to translate and are marked by their
#: absence here rather than by a copied English line, which is what a stalled
#: translation looks like.
#:
#: The English detail stays exactly where it was written, at the call site.
#: Nothing here replaces it: this is what a Polish reader gets instead.
DETAILS_PL: dict[str, str] = {
    "reader.dangling-reference":
        "{reference} — odwołanie jest pomijane, a nie zgadywane.",
    "a11y.placeholder-alt":
        "{examples} — to przechodzi walidację, ale użytkownikowi czytnika ekranu nie mówi nic, więc alternativeText nie jest deklarowane.",
    "compat.unknown-profile":
        "Znane profile: {known}.",
    "xhtml.dead-reference-neutralised":
        "{unlinked} {unlinked:odnośnik odlinkowano|odnośniki odlinkowano|odnośników odlinkowano}, {removed} {removed:element usunięto|elementy usunięto|elementów usunięto}.",
    "css.font-stack-generic-missing":
        "np. {examples} — odziedziczone ze źródła i zostawione bez zmian, bo zgadywanie między szeryfową a bezszeryfową mogłoby zmienić wygląd książki.",
    "xhtml.untouched":
        "Każdy plik XHTML wychodzi bajt w bajt taki, jaki wszedł.",
    "xhtml.untouched-except-doctype":
        "Każdy plik XHTML wychodzi bajt w bajt taki, jaki wszedł, poza DOCTYPE, który trzeba było unowocześnić.",
    "xhtml.dtd-entities-resolved":
        "{names}. Deklaracje mieszkały w DOCTYPE, który EPUB 3 zastępuje takim, co nie deklaruje niczego — więc bez tego odwołania pojawiłyby się na stronie jako dosłowny tekst.",
    "xhtml.dtd-entities-refused":
        "{names}. Albo wskazują poza plik, czego to narzędzie nie pobiera, albo ich rozwinięcie rozdęłoby dokument ponad bezpieczną granicę.",
    "xhtml.watermark-consolidated":
        "{tokens} {tokens:odrębny token|odrębne tokeny|odrębnych tokenów}, tekst bez zmian. Powtarzany styl liniowy z !important stał się jedną regułą, a znaczniki są ukryte przed czytnikami ekranu, zamiast być wypowiadane w każdym rozdziale.",
    "xhtml.watermark-relocated":
        "{tokens} {tokens:odrębny token|odrębne tokeny|odrębnych tokenów}, tekst bez zmian, teraz jako <meta name=\"{name}\"> w nagłówku tego dokumentu, z którego pochodzi. Wciąż w pliku i wciąż do odczytania, ale już nie na stronie: nic go nie składa, nie łamie i nie czyta na głos — a token o zerowym stopniu pisma wciąż tam był.",
    "xhtml.watermark-removed":
        "{tokens} {tokens:odrębny token|odrębne tokeny|odrębnych tokenów} — nie ma. Książka nie niesie już znaku, który wiąże ten egzemplarz z kupującym.",
    "metadata.language-corrected":
        "{rate} liter wyłącznie polskich na 1000 znaków własnego tekstu książki. Czytnik podaje dc:language syntezatorowi mowy i po nim dzieli wyrazy, więc zła deklaracja to czytanie niewłaściwym głosem i łamanie niewłaściwymi regułami — o żadnym z tych dwóch nie powie ci walidator. --language to nadpisuje.",
    "css.font-stack-generic-added":
        "Odczytane z tablicy OS/2 samej czcionki — PANOSE, dziesięć bajtów wpisanych przez projektanta — a nie wywnioskowane z nazwy. Stos bez rodziny generycznej spada na cokolwiek, co czytnik uzna za stosowne, gdy osadzona czcionka się nie wczyta, a na czytniku zdarza się to często.",
    "xhtml.watermark-kept":
        "Ma być czytane, więc zostawione dokładnie tak, jak napisał to wydawca.",
    "xhtml.watermark-kept-personal-data":
        "Zawiera dane osobowe ({data}). Ma być czytane, więc zostawione dokładnie tak, jak napisał to wydawca.",
    "css.reader-property-kept":
        "{names} — walidatory zgłaszają je jako nieznane. Użyj --strict, żeby je usunąć.",
    "image.transcoded":
        "było {was}",
    "nav.repointed":
        "{in_tables} w tablicach nawigacyjnych, {in_documents} wewnątrz dokumentów treści. Własna strona spisu treści źródła zostaje zastąpiona, a odwołanie zostawione na nią czyni książkę niepoprawną, nie tylko niespójną.",
    "structure.orphan-removed":
        "odzyskano {bytes} {bytes:bajt|bajty|bajtów}",
    "structure.relaid-out":
        "{renamed} {renamed:plik potrzebował|pliki potrzebowały|plików potrzebowało} nowej nazwy; każde odwołanie zostało przepisane, żeby się zgadzało",
    "epubcheck.unavailable":
        "Zainstaluj go i ustaw {variable}, albo umieść epubcheck w PATH.",
    "package.layout-kept":
        "Ta przebudowa nie przesuwa plików treści, więc odsunięcie od nich dokumentu pakietu zostawiłoby każdy odnośnik manifestu wskazujący z powrotem poza własny katalog, przez „../”.",
    "package.upgraded":
        "Dokument pakietu, nawigacja i struktura kontenera zostały wygenerowane od nowa.",
    "package.source-protected":
        "Nic nie zostało zapisane. Wybierz inne miejsce docelowe.",
    "package.stage-failed":
        "Nic nie zostało zapisane. Awaria zostawiła model w połowie zmieniony, więc cokolwiek by z niego zbudowano, byłoby książką tylko z kształtu.",
    "reader.entry-too-large":
        "Żadna prawdziwa książka tego nie zawiera; archiwum jest uszkodzone albo wrogie.",
    "reader.colliding-names":
        "W archiwum to osobne pliki, a na systemie plików zwijającym wielkość liter albo Unicode — jeden. Który z nich przetrwa, zależy od kolejności rozpakowania.",
    "reader.drm":
        "EPUB F.O.R.G.E. nie próbuje odszyfrowywać treści chronionej DRM.",
    "reader.remote-resource":
        "Nic tutaj tego nie pobiera. Nie jest to też przechowywane w kontenerze.",
    "reader.name-dropped":
        "Nic w poprawnym EPUB-ie nie nazywa się w ten sposób. Wpis nie trafia do wyniku, gdzie i tak byłby nieosiągalny.",
    "a11y.conformance-declared":
        "EPUB F.O.R.G.E. tego nie zweryfikował; to oświadczenie wydawcy.",
    "a11y.missing-alt":
        "Albo atrybutu nie ma, albo jest pusty. Pusty alt oświadcza, że obraz jest dekoracyjny, a tego nie da się sprawdzić maszynowo — mówi to wprost dopiero role=\"presentation\" albo aria-hidden=\"true\". Dlatego alternativeText nie jest deklarowane. Jeśli któryś z tych obrazów niesie treść, opis może napisać tylko człowiek.",
    "a11y.table-without-headers":
        "Bez <th> czytnik ekranu nie ma jak ogłosić, do czego odnosi się komórka.",
    "compat.ncx-required":
        "Czytniki starsze niż EPUB 3 budują listę rozdziałów z NCX i ignorują dokument nawigacyjny.",
    "compat.stylesheet-added":
        "Deklaruje elementy sekcjonujące HTML5 jako blokowe. Jest podlinkowany przed arkuszem samej książki, więc jej własne reguły nadal wygrywają.",
    "compat.page-break-mirrored":
        "Nowoczesne właściwości break-* zostają dokładnie takie, jakie były; stary zapis dochodzi obok nich, a nie zamiast nich.",
    "compat.specified-fonts-added":
        "Bez tego pliku Apple Books ignoruje każdy osadzony krój i podstawia własny.",
    "compat.guide-added":
        "EPUB 3.3 już nie definiuje tego elementu, choć EPUBCheck wciąż go przyjmuje: wynik pozostaje poprawny.",
    "compat.svg-cover":
        "To opakowanie skaluje grafikę do strony, więc jego usunięcie zmieniłoby układ na każdym czytniku, który radzi sobie z SVG.",
    "compat.specified-fonts-skipped":
        "Zadeklarowanie tego mimo wszystko stwierdzałoby coś, czego książka nie robi.",
    "profile.paragraphs-mixed":
        "Książka z jednego źródła nie miesza obu sposobów. Kiedy miesza, ktoś skleił dwa pliki albo przepuścił jeden przez dwa narzędzia — a to warto wiedzieć, zanim jakakolwiek reguła spróbuje ujednolicić akapity.",
    "profile.body-text-inconsistent":
        "Reguły pytające, czy dana konstrukcja jest w tej książce normą, nie mają się tu do czego odnieść. Procent zostaje zamiast zostać zaokrąglonym do „brak”, bo to, jak bardzo książce brakowało, jest tym, co powie reguła, która odmówi zadziałania.",
    "xhtml.dead-reference-kept":
        "To są defekty źródła i pozostają błędami zgodności. Użyj --strict, żeby je unieszkodliwić.",
    "xhtml.dead-fragment-dropped":
        "Plik, który wskazuje każdy z tych odnośników, jest na miejscu; kotwicy w nim nie ma. Odnośnik prowadzi teraz na początek tego dokumentu. To jedyna droga od brakującej kotwicy do jej braku i prowadzi przez człowieka, który zajrzał do książki: program sam tego nie zrobi, bo odnośnika, który po cichu trafia w miejsce prawdopodobne, nie da się odróżnić od działającego.",
    "xhtml.fragment-unresolved":
        "Dokument docelowy istnieje, kotwicy w nim nie ma — więc z samego pliku nie da się odczytać, dokąd odnośnik miał prowadzić. To defekt odziedziczony ze źródła i jest zgłaszany, a nie naprawiany: usunięcie fragmentu uciszyłoby walidator, wysyłając czytelnika na początek dokumentu, a przy znaczniku przypisu — do niewłaściwego przypisu, i nic tutaj nie odróżni tego od naprawy. Tryb ścisły nie wyda książki, która je niesie; w oknie aplikacji można odpowiedzieć na każde z osobna.",
    "nav.sections-carried":
        "Spis tabel, spis ilustracji, spis czegokolwiek, co wydawca nazwał po swojemu. Ten program regeneruje dokument, w którym mieszkały, więc niezapisanie ich z powrotem byłoby ich skasowaniem — a to, że nie ma reguły, jak je czytać, jest powodem, żeby przenieść je bez zmian, a nie powodem, żeby je wyrzucić.",
    "xhtml.fragment-repointed":
        "Kotwicę wskazał człowiek, czyli dowód, którego program nie ma. Liczone osobno od wszystkiego, co ustalił sam.",
    "package.unresolved-references":
        "Każde z nich jest w raporcie razem z dokumentem, który je zawiera. Przebuduj w trybie zachowawczym, żeby dostać plik z nienaruszonymi zepsutymi odwołaniami wydawcy, albo otwórz książkę w oknie aplikacji, gdzie można odpowiedzieć na każde po kolei.",
    "css.remote-import-removed":
        "EPUB 3 dopuszcza jeden rodzaj zasobu zdalnego — font zadeklarowany przy pozycji manifestu — a arkusz stylów nim nie jest. Deklaracje font-family zostają nietknięte, więc książka podstawia kroje dokładnie tak, jak podstawiłaby wcześniej.",
    "xhtml.remote-import-removed":
        "EPUB 3 dopuszcza jeden rodzaj zasobu zdalnego — font zadeklarowany przy pozycji manifestu — a arkusz stylów nim nie jest. Deklaracje font-family zostają nietknięte, więc książka podstawia kroje dokładnie tak, jak podstawiłaby wcześniej.",
    "xhtml.image-paragraph-centred":
        "Reguły tekstu bieżącego przesuwały grafikę; żadna reguła nie celowała w te akapity z osobna, więc nic, co wybrał wydawca, nie zostało nadpisane.",
    "xhtml.image-paragraph-centred-unstyled":
        "Ta strona nie linkuje żadnego arkusza, więc nie było wcięcia do usunięcia ani reguły wydawcy do nadpisania — grafikę dosuwało do lewej domyślne ustawienie czytnika. Mówione osobno, bo to inny fakt o książce, a komunikat opisujący nie ten fakt uczy przeskakiwać nad komunikatami.",
    "package.text-lost":
        "K1, reguła nadrzędna wobec wszystkich innych w tym programie: każdy znak kolejności czytania źródła jest w wyniku, w tej samej kolejności. Mierzone na poziomie słów, bo przebudowa świadomie zmienia odstępy. Plik został zbudowany, sprawdzony i odrzucony, zanim wziął swoją nazwę — więc to, co leżało pod tą nazwą, jest nietknięte.",
    "hyphens.no-dictionary":
        "Detektor ma dwa źródła dowodu: czy ta książka sama pisze to słowo bez łącznika, i czy pierwsza połówka słowa w ogóle jest słowem. Dostępne było tylko pierwsze, a ono milczy akurat przy słowie, które w książce występuje raz — więc część przeciętych słów mogła zostać niezauważona. Nic nie zostało złączone bez podstaw; ten przebieg po prostu widział mniej.",
    "package.text-changed-on-request":
        "K1 mówi o stratach, o które nikt nie prosił. Usunięcie znaku wodnego i złączenie słowa przeciętego przez konwersję zabierają znaki, oba dzieją się dopiero za zgodą czytelnika i oba są w rejestrze zmian — więc są tutaj nazwane, a nie odrzucone. Brama nadal odmawia, gdy tekst znika i nic tego nie tłumaczy.",
    "package.text-check-failed":
        "Samo porównanie rzuciło wyjątkiem. Kontrola, która nie umiała się wykonać, to nie jest książka, która padła, więc przebudowa poszła dalej — ale nikt nie sprawdził tekstu i warto o tym wiedzieć, zanim się temu wynikowi zaufa.",
    "xhtml.cover-sized-in-pixels":
        "Atrybut width albo height w pikselach ustala okładkę na jednym rozmiarze niezależnie od ekranu. To instrukcja wydawcy, więc jest raportowana, a nie nadpisywana: zmiana jest decyzją o wyglądzie książki, a takich program nie podejmuje sam.",
    "xhtml.image-paragraph-unindented":
        "O położeniu obrazu decyduje reguła celująca w te akapity albo w ich kontener; wcięcie dotyczy tekstu bieżącego, którego tu nie ma.",
    "xhtml.image-paragraph-kept":
        "Reguła celująca w te akapity — albo w element, który je zawiera — ustawia ich wyrównanie lub wcięcie.",
    "xhtml.cover-fitted":
        "Żadna reguła arkusza ani żaden atrybut nie nadał temu obrazowi rozmiaru, więc czytnik pokazałby go w jego własnych pikselach.",
    "xhtml.inline-promoted":
        "Pudełko blokowe wewnątrz liniowego łamie wiersz i sprawia, że marginesy oraz środkowanie zachowują się nieprzewidywalnie — różnie na różnych czytnikach.",
    "xhtml.empty-alt-added":
        "Wymagany przez poprawną składnię. Nie jest traktowany jako opis: etap dostępności nadal liczy te obrazy jako pozbawione tekstu alternatywnego.",
    "xhtml.property-withdrawn":
        "Zadeklarowanie którejś z nich bez odpowiadających jej znaczników jest samo w sobie błędem zgodności i EPUBCheck zgłasza to wobec źródła.",
    "css.vendor-at-rule-kept":
        "Użyj --strict, żeby je usunąć.",
    "xhtml.forbidden-characters-removed":
        "Gorsza połowa tej samej usterki: znak sterujący w tytule psuje pakiet, a w rozdziale psuje tekst książki. Przychodzi ze źródła — uszkodzony plik odzyskany przez parser go zachowuje — i był zapisywany z powrotem do dokumentu, którego nic nie otworzy. Znika wyłącznie znak niemożliwy do zapisania; każda litera, cyfra i znak przestankowy zostają, więc żaden znak własnego tekstu książki nie ginie.",
    "xhtml.mojibake-translated":
        "Windows-1252 trzyma znaki przestankowe na pozycjach, które Unikod rezerwuje dla kodów sterujących — więc konwerter czytający tekst z Windowsa jak Latin-1 zamienia każdy cudzysłów i myślnik w kod, którego żadna czcionka nie rysuje. Uszkodzenie jest w pliku, a nie w naszym odczycie: dokumenty, na których to znaleziono, deklarują UTF-8 i są poprawnym UTF-8. Droga powrotna jest jeden do jednego po dwudziestu siedmiu zdefiniowanych pozycjach i nic w niej nie jest zgadywane — dlatego jest naprawą, a nie heurystyką. Zmienia jednak znaki tekstu, więc dzieje się wyłącznie wtedy, gdy ktoś tak zdecyduje.",
    "xhtml.mojibake-found":
        "To samo uszkodzenie, zostawione, bo tak wybrano. Powiedziane głośno, a nie przemilczane, bo te znaki są w czytniku niewidoczne: książka nie ma na stronie swoich cudzysłowów niezależnie od tego, czy ktoś to zauważy w pliku.",
    "package.forbidden-characters-removed":
        "To nie jest kwestia escapowania: XML 1.0 w ogóle nie ma zapisu dla tych znaków, więc dokument pakietu, który je niesie, nie parsuje się i książka się nie otwiera. Zmierzone, zanim to powstało: tytuł ze znakiem 0x0B dawał zapisaną, nieotwieralną książkę w trybie domyślnym. Znika wyłącznie znak sterujący; każdy inny znak pola zostaje.",
    "xhtml.shop-notice-removed":
        "Wypisane co do słowa, a nie policzone, bo to jedyne ustawienie w programie, które kasuje tekst widoczny dla czytelnika. Zabierane są wyłącznie zdania nazywające sprzedaż — zamówienie, zakup, licencję, kupującego. Stopka redakcyjna wydawcy nazywa wydawcę, a nie transakcję, i nie jest ruszana; żadna strona nie jest usuwana — element, który zostanie pusty, zostaje, a bilans to zgłasza.",
    "css.invalid-value-corrected":
        "font-style ani font-weight nie mają słowa kluczowego „regular”, więc parsery odrzucały te reguły w całości. Zastąpione przez „normal” — i tylko dlatego, że nic w tym arkuszu nie ustawia kursywy ani pogrubienia, więc dziedziczenie i nadpisanie dają tę samą stronę.",
    "css.invalid-value-inherited":
        "„regular” odrzuca każdy parser, więc element dziedziczy; „normal” by nadpisało. Te dwie rzeczy zgadzają się tylko dopóki dziedziczona wartość i tak jest normalna, a ten arkusz gdzieś ustawia kursywę albo pogrubienie — więc poprawka mogłaby wyprostować pochyły fragment. Deklaracja i tak była ignorowana, więc zostawienie jej niczego nie zmienia.",
    "css.absolute-units":
        "Rozmiary w px albo pt nie reagują na ustawienie wielkości czcionki w czytniku, a to zwykle pierwsza rzecz, którą się zmienia. Zostawione tak, jak napisał je wydawca; użyj --relative-units, żeby przepisać je na rem.",
    "css.absolute-units-relativised":
        "rem, a nie em: em liczy się względem rodzica, więc zagnieżdżona reguła kumulowałaby się i ta sama wartość znaczyłaby w różnych miejscach różny rozmiar. rem liczy się względem elementu głównego, więc każdy rozmiar wychodzi dokładnie jako rozmiar/16 — te same piksele co dotąd przy ustawieniu domyślnym i skalowanie razem z nim poza domyślnym.",
    "css.absolute-units-rooted":
        "rem mierzy się od elementu głównego, a ten arkusz ustala go w pikselach. Przepisanie reszty przerobiłoby arkusz, nie uwalniając ani jednego rozmiaru.",
    "css.unreachable-rules-found":
        "Księgarnie wgrywają jeden firmowy arkusz do każdego sprzedawanego tytułu i większość z niego dotyczy znaczników, których dana książka nie ma — `td.proc4` w powieści bez tabel. Tak czy inaczej nie zmienia to ani piksela. Użyj --strict, żeby to usunąć; ten tryb raportuje i zostawia, bo selektor niepasujący do niczego w sparsowanych przez nas dokumentach to nie to samo, co selektor niepasujący do niczego.",
    "css.unreachable-rules-removed":
        "Tylko reguły, których każda gałąź nazywa klasę lub id nieobecne w całej książce. Goły selektor znacznika, selektor atrybutu, pseudoklasa i wszystko wewnątrz @media pozostają nietknięte. Cięcie jest następnie sprawdzane przez ponowne sparsowanie arkusza i porównanie tego, co zostało; arkusz, który się nie zgadza, wraca bez zmian.",
    "css.unreachable-rules-scripted":
        "Skrypt może dodać klasę w trakcie czytania, więc „nie pasuje do niczego” byłoby zdaniem o pliku, a nie o lekturze.",
    "css.unreachable-rules-unverified":
        "Reguły zostają. Usunięcia, o którym nie da się wykazać, że zabrało dokładnie to, co miało, to narzędzie nie robi.",
    "css.position-kept":
        "To książka o stałym układzie, w której pozycjonowanie poza przepływem jest sposobem działania.",
    "xhtml.position-pinned-in-flow":
        "`margin-top: auto` w kolumnie flex ustawia blok przy stopce strony dokładnie tak, jak miało to robić `bottom: 0`, i zostawia go w przepływie, więc paginacja nie ma jak go zgubić. Wpisane do tego jednego dokumentu, który tego potrzebuje, nigdy do wspólnego arkusza — zrobienie z każdego `body` w książce kolumny flex zatrzymałoby scalanie sąsiadujących marginesów na każdej jej stronie. Tylko wtedy, gdy strona jest tym jednym blokiem: przy rodzeństwie nie ma wiernego tłumaczenia, więc reguła zostaje i jest raportowana.",
    "css.position-contained":
        "Element pozycjonowany absolutnie liczy się względem najbliższego pozycjonowanego przodka, a nie względem strony — podpis na obrazku, plakietka na okładce. Jedzie razem z pudełkiem, które go trzyma, więc paginacja nie ma jak go zgubić, a argument za usuwaniem pozycjonowania poza przepływem w ogóle go nie dotyczy. Zachowane również pod --strict, który wcześniej to kasował i zrzucał podpis pod obrazek na każdym czytniku.",
    "css.position-superseded":
        "Deklaracja nadal jest w arkuszu i już o niczym nie decyduje: dokument niesie odpowiednik, który ją przebija. Zostawiona, bo usuwanie ze wspólnego arkusza sięgnęłoby dokumentów, których nikt nie oglądał.",
    "css.position-kept-reflowable":
        "Nie każdy czytnik paginuje treść wyjętą z przepływu, ale to układ wybrany przez wydawcę i nie ma dla niego wiernego odpowiednika. Użyj --strict, żeby go usunąć.",
    "css.position-removed":
        "Te bloki płyną teraz razem ze stroną, zamiast być do niej przypięte. Nie dotyczy książek o stałym układzie, gdzie pozycjonowanie poza przepływem jest sposobem działania formatu. Na prawdziwym czytniku dedykacja przypięta w ten sposób wyszła jako pusta strona — blok wypadł z przepływu, a paginacja go ominęła.",
    "xhtml.orphaned-styling-restored":
        "Reguła jest w tej książce, w arkuszu, którego ten dokument nie podpina, i ma ją dokładnie jeden arkusz — więc nie ma między czym wybierać. Skopiowana do dokumentu dosłownie, zamiast podpinania całego arkusza, co wniosłoby na tę stronę wszystkie pozostałe decyzje z niego. Nie stosowane, gdy dwa arkusze się różnią, ani do reguł pobierających coś przez url().",
    "xhtml.empty-span-found":
        "Zmierzone na 12 475 spanach w 32 książkach: 97% coś robi, a te, które nie robią nic, to w całości konwersja z PDF-u — `.reset { margin: 0; padding: 0 }` na elemencie liniowym, gdzie to są wartości domyślne, i `.black { color: #010000 }`, czyli czerń przesunięta o jedną część na 255. Span, którego nie styluje nic, zostaje nietknięty: największą taką klasą w korpusie było 219 inicjałów z odpiętym arkuszem.",
    "xhtml.empty-span-unwrapped":
        "Rozwinięte, nie skasowane — tekst w środku zostaje dokładnie tam, gdzie był. Tylko spany bez id, lang, epub:type, role, dir, title i style, i tylko tam, gdzie reguła ich dosięga, a każda jej deklaracja jest wartością domyślną dla elementu liniowego.",
    "xhtml.epub2-only-markup":
        "Tryb kontenerowy zmienia tylko głowę dokumentu, więc to zostaje, a wynik jest niepoprawnym EPUB-em 3 nie z winy treści. Przebuduj w trybie „Zachowaj wygląd” — tam każde z nich zostaje przepisane na to, co EPUB 3 przyjmuje, bez zmiany tego, co widać na stronie. Wypisane jest to, co znaleziono, a nie cała klasa: czego tu nie ma, i tak pokaże walidator.",
    "xhtml.title-filled":
        "EPUB 2 dopuszczał pusty <title>, EPUB 3 już nie, a ta przebudowa daje EPUB-a 3. Tekst nie jest wyświetlany w treści, więc nic na stronie się nie przesuwa. W trybie kontenerowym to druga i ostatnia zmiana wewnątrz dokumentu.",
    "xhtml.doctype-modernised":
        "Jedyna zmiana, jaką ten tryb wprowadza wewnątrz dokumentu. DOCTYPE nie mówi nic o sposobie wyświetlania, a stary czyni książkę niepoprawną. DOCTYPE deklarujący własne encje zostaje nietknięty, bo dokument z nich korzysta.",
    "xhtml.doctype-kept":
        "W tych dokumentach wynik pozostaje niepoprawnym EPUB-em 3 i jest to mniejsza szkoda: zastąpienie DOCTYPE osierociłoby encję, a książka z osieroconą encją w ogóle się nie otwiera.",
    "font.drm":
        "Usuń DRM narzędziem, do którego masz licencję, zanim uruchomisz EPUB F.O.R.G.E.",
    "font.deobfuscated":
        "Czcionki wyglądają identycznie, a kontener nie zależy już od identyfikatora.",
    "font.deobfuscation-failed":
        "Identyfikator źródła prawdopodobnie różni się od tego, którym je zaciemniono.",
    "metadata.title-missing":
        "Podaj --title, żeby ustawić prawdziwy.",
    "nav.fragment-cleared":
        "Pozycja wskazuje teraz na sam dokument, czyli tam, gdzie czytelnik i tak by trafił.",
    "nav.kept-in-spine":
        "Dokument nawigacyjny w kolejności czytania to strona, na którą czytelnik może przejść. Generowanie go od nowa usuwało tę stronę — czyli usuwało z książki coś, co czytelnik widział.",
    "nav.generated":
        "Źródło nie miało żadnego; jego spis treści pochodził z NCX.",
    "nav.contents-page-kept":
        "Ta strona jest w kolejności czytania, więc czytelnik na nią przechodzi. Zastąpienie jej wygenerowaną nawigacją usuwałoby stronę, którą złożył wydawca.",
    "structure.carried-xml-repointed":
        "Ten typ pliku nie jest modelowany przez potok, ale pliki, na które wskazuje, potok przesuwa. Zostawienie odwołań w spokoju dałoby książkę niepoprawną, a nie tylko uboższą.",
}

#: The fixed phrases this program passes *into* a finding as data.
#:
#: `reader.name-dropped` says "…could not be made into a container path: {reason}",
#: and the reason is one of a handful of sentences written in `ocf.py`. Left
#: alone it produced a Polish sentence with an English clause inside it — a
#: translation that looks finished and reads like neither language.
#:
#: This is a vocabulary, not prose: every entry is one of a closed set the
#: program itself chose. A value that is not in it — a file name, a number, a
#: media type — passes through untouched, which is why the mapping can be
#: applied to every value without asking which ones are words.
VOCABULARY_PL: dict[str, str] = {
    # ocf.py — why an archive entry name was rejected
    "the name climbs out of the container with '..'":
        "nazwa wychodzi poza kontener przez „..”",
    "the name is empty once normalised": "nazwa jest pusta po normalizacji",
    # ocf.py — what had to be changed in a name
    "null byte": "bajt zerowy",
    "backslash separators": "separatory w postaci lewych ukośników",
    "leading slash": "ukośnik na początku",
    "drive letter": "litera dysku",
    "percent-encoding": "kodowanie procentowe",
    "empty or current-directory segments": "puste segmenty albo segmenty bieżącego katalogu",
    "parent-directory segments": "segmenty katalogu nadrzędnego",
    # profile.py — the paragraph paradigm, which goes into a sentence
    "indented": "wcięciem",
    "spaced": "odstępem",
    "both": "wcięciem i odstępem naraz",
    # ocf.py — how two entry names collide
    "identical": "identyczność",
    "case": "wielkość liter",
    "normalisation": "normalizację Unicode",
}

VOCABULARIES: dict[str, dict[str, str]] = {"pl": VOCABULARY_PL}


def translate_values(values: dict | None, language: str) -> dict:
    """Replace values that are this program's own fixed phrases.

    Everything else — names, counts, media types — is data and passes through.
    """
    vocabulary = VOCABULARIES.get(language)
    if not values or not vocabulary:
        return values or {}
    return {
        key: vocabulary.get(value, value) if isinstance(value, str) else value
        for key, value in values.items()
    }


#: Language code → catalogue. `describe` falls back to English for a language
#: nobody has written, which is the right failure: a report in the wrong
#: language is still a report, and one that refuses to print is not.
CATALOGUES: dict[str, dict[str, str]] = {"en": CATALOGUE, "pl": CATALOGUE_PL}


def known(rule: str) -> bool:
    return rule in CATALOGUE


#: Placeholders in a catalogue entry: `{name}`, optionally with a plural spec.
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)(?::[^}]*)?\}")


class _Plural(string.Formatter):
    """`{count:plik|pliki|plików}` — the noun agreeing with the number.

    English gets away with "(s)" and Polish does not: it has three forms, and
    which one a number takes is not a matter of taste. "1 plików" is not a
    clumsy phrasing, it is a mistake, and a translation full of them is the
    kind that gets switched off.

    The rule is the standard one: one for exactly 1, the *few* form for numbers
    ending 2–4 except the teens, the *many* form for everything else.
    """

    def format_field(self, value, format_spec: str) -> str:
        if "|" not in format_spec:
            return super().format_field(value, format_spec)
        forms = format_spec.split("|")
        if len(forms) != 3:
            return super().format_field(value, "")
        one, few, many = forms
        try:
            number = abs(int(value))
        except (TypeError, ValueError):
            return many
        if number == 1:
            return one
        if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
            return few
        return many


_FORMATTER = _Plural()


def fill(text: str, values: dict | None = None) -> str:
    """Fill one template, plural forms and all, without raising over a gap.

    Exposed because the window needs the same agreement the report has. The
    string tables held a second, plainer formatter, so a count in the interface
    could only say "4 plik" or hedge with a parenthesis — in the one place a
    Polish reader is looking at Polish.
    """
    if not values:
        return text
    try:
        return _FORMATTER.vformat(text, (), values)
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def placeholders(rule: str, language: str = "en") -> set[str]:
    """The names a catalogue entry expects to be given."""
    catalogue = CATALOGUES.get(language, CATALOGUE)
    return set(_PLACEHOLDER.findall(catalogue.get(rule) or CATALOGUE.get(rule, "")))


def describe(rule: str, language: str = "en", values: dict | None = None) -> str:
    """What the id means, in the language asked for.

    Falls back to English, then to the id itself. Returning the id rather than
    raising is deliberate: a report missing an explanation is still a report,
    and one that refuses to print because of a missing dictionary entry helps
    nobody.

    An entry with placeholders is a template, and *values* fills it. A template
    given nothing to fill it with comes back with its braces intact rather than
    raising — the caller can see that for itself, through `renders_fully`, and
    the alternative is a report that dies over a missing number.
    """
    catalogue = CATALOGUES.get(language, CATALOGUE)
    text = catalogue.get(rule) or CATALOGUE.get(rule, rule)
    if not values:
        return text
    try:
        return _FORMATTER.vformat(text, (), translate_values(values, language))
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def detail_placeholders(rule: str, language: str = "en") -> set[str]:
    """The names the paragraph beneath a finding expects to be given."""
    catalogue = DETAILS_PL if language == "pl" else DETAILS
    return set(_PLACEHOLDER.findall(catalogue.get(rule, "")))


def describe_detail_en(rule: str, values: dict | None = None) -> str | None:
    """The English paragraph for a rule, or `None` where there is none to give."""
    if rule not in DETAILS:
        return None
    return describe_from(DETAILS, rule, values)


def describe_detail(rule: str, language: str = "en", values: dict | None = None) -> str | None:
    """The paragraph beneath a finding, in the language asked for.

    Returns `None` when there is nothing to put there — English asks for the
    original, and a detail nobody has translated yet has to fall back to it
    rather than be dropped. Losing the paragraph would be a worse translation
    than an untranslated one: it is where the file names and the reasons live.
    """
    if language == "en" or rule not in DETAILS_PL:
        return None
    return describe_from(DETAILS_PL, rule, values, language)


def describe_from(
    catalogue: dict[str, str], rule: str, values: dict | None, language: str = "en"
) -> str:
    """Fill one catalogue entry, leaving its braces alone rather than raising."""
    text = catalogue.get(rule, rule)
    if not values:
        return text
    try:
        return _FORMATTER.vformat(text, (), translate_values(values, language))
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def renders_fully(rule: str, language: str, values: dict | None) -> bool:
    """Whether the description says everything the message says.

    This is what decides if the original English sentence still has to appear
    underneath a translated one. A finding's specifics — how many entries,
    which file, which media type — are exactly what it carries in `values`, so
    the description is complete when it states all of them. A finding carrying
    none has no specifics to lose, and its description stands alone.

    The other direction is not a failure: a template may name a value the
    finding did not supply, and then the placeholder would print at the reader.
    That is what makes it incomplete.
    """
    supplied = set(values or {})
    # A finding's specifics may be stated by either line. `a11y.placeholder-alt`
    # counts the images in its headline and lists them in its paragraph, and
    # judging the headline alone declared the finding incomplete and put the
    # English sentence back underneath a perfectly complete Polish one.
    expected = placeholders(rule, language)
    consumed = expected | detail_placeholders(rule, language)
    return supplied <= consumed and expected <= supplied


__all__ = [
    "CATALOGUE",
    "CATALOGUES",
    "CATALOGUE_PL",
    "DETAILS",
    "DETAILS_PL",
    "describe_detail_en",
    "VOCABULARY_PL",
    "translate_values",
    "describe",
    "describe_detail",
    "describe_from",
    "known",
    "placeholders",
    "detail_placeholders",
    "renders_fully",
]
